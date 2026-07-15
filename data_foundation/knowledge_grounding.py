"""DeepAgents 原生 middleware：每轮自动为创作上下文做统一知识检索。

这里不创建新的 Agent 循环。middleware 只在 DeepAgents 的 ``before_agent`` 扩展点
调用既有 ``retrieve_knowledge`` 工具，并把结果写入私有 state；模型看到的是同一份结果
的只读提示片段，持久化工具则通过 ``InjectedState`` 取得权威副本。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Annotated, Any, NotRequired

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import PrivateStateAttr

if TYPE_CHECKING:
    from collections.abc import Callable

    from langchain_core.runnables import RunnableConfig
    from langgraph.runtime import Runtime


logger = logging.getLogger(__name__)

_VALID_MODES = {
    "hybrid",
    "semantic_only",
    "keyword_only",
    "insufficient_relevance",
}
_FOLLOW_UP_RE = re.compile(
    r"(?:再|继续|接着|沿用|这个|这篇|上面|刚才|上一版|前一版|"
    r"改|修改|调整|优化|润色|缩短|精简|扩写|重写|换一版|another|revise|shorter)",
    re.IGNORECASE,
)


class KnowledgeGroundingState(AgentState):
    """工具可注入、模型不可改写的每轮知识检索状态。"""

    knowledge_grounding: NotRequired[Annotated[dict[str, Any], PrivateStateAttr]]
    latest_user_request: NotRequired[Annotated[str, PrivateStateAttr]]


def _message_text(message: Any) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(part.strip() for part in parts if part.strip()).strip()
    return ""


def latest_human_text(state: dict[str, Any]) -> str:
    """读取最后一条真实用户消息，不把工具结果或模型回复当成检索词。"""

    messages = state.get("messages")
    if not isinstance(messages, list):
        return ""
    for message in reversed(messages):
        role = getattr(message, "type", None) or getattr(message, "role", None)
        if role in {"human", "user"}:
            return _message_text(message)
        if isinstance(message, dict) and message.get("role") in {"human", "user"}:
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
    return ""


def retrieval_query(state: dict[str, Any], latest: str) -> str:
    """续写/润色短指令要带上最近主题，但不能把历史模型输出混进检索词。"""

    latest = latest.strip()
    if not latest or not _FOLLOW_UP_RE.search(latest):
        return latest
    messages = state.get("messages")
    if not isinstance(messages, list):
        return latest
    human_texts: list[str] = []
    for message in messages:
        role = getattr(message, "type", None) or getattr(message, "role", None)
        is_human = role in {"human", "user"}
        if isinstance(message, dict):
            is_human = message.get("role") in {"human", "user"}
        if not is_human:
            continue
        text = _message_text(message)
        if not text and isinstance(message, dict):
            content = message.get("content")
            text = content.strip() if isinstance(content, str) else ""
        if text:
            human_texts.append(text)
    if len(human_texts) < 2:
        return latest
    previous = human_texts[-2][-1200:]
    return f"{previous}\n当前修改要求：{latest}"[-2000:]


def _default_retriever(query: str, limit: int, config: RunnableConfig) -> dict[str, Any]:
    # 懒导入避免工具模块装配时形成循环；调用的是公开统一工具，而非旁路召回引擎。
    from data_foundation.tools import retrieve_knowledge

    result = retrieve_knowledge.invoke({"query": query, "limit": limit}, config=config)
    return dict(result) if isinstance(result, dict) else {"error": "INVALID_RETRIEVAL_RESULT"}


def _turn_id(config: RunnableConfig) -> str | None:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    value = configurable.get("turn_id") if isinstance(configurable, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _grounding_payload(
    *, query: str, result: dict[str, Any], turn_id: str | None
) -> dict[str, Any]:
    mode = result.get("retrieval_mode")
    evidence = result.get("evidence")
    if mode not in _VALID_MODES or not isinstance(evidence, list):
        error = result.get("error")
        return {
            "status": "error",
            "query": query,
            "turn_id": turn_id,
            "error": error if isinstance(error, str) else "KNOWLEDGE_RETRIEVAL_FAILED",
        }
    if mode == "insufficient_relevance" and evidence:
        return {
            "status": "error",
            "query": query,
            "turn_id": turn_id,
            "error": "INVALID_RETRIEVAL_RESULT",
        }
    if mode != "insufficient_relevance" and not evidence:
        return {
            "status": "error",
            "query": query,
            "turn_id": turn_id,
            "error": "INVALID_RETRIEVAL_RESULT",
        }
    return {
        "status": "ready",
        "query": query,
        "turn_id": turn_id,
        "retrieval_mode": mode,
        "evidence": evidence,
        "engines_used": result.get("engines_used") or [],
        "degraded_engines": result.get("degraded_engines") or [],
        "gaps": result.get("gaps"),
    }


def _prompt_fragment(grounding: dict[str, Any]) -> str:
    status = grounding.get("status")
    if status != "ready":
        return (
            "<automatic_knowledge_grounding>\n"
            "自动知识检索本轮不可用。不得编造历史案例，也不得保存新生成文案；"
            "可以说明暂时无法完成有依据的生成。\n"
            "</automatic_knowledge_grounding>"
        )
    public = {
        "retrieval_mode": grounding.get("retrieval_mode"),
        "evidence": grounding.get("evidence") or [],
        "engines_used": grounding.get("engines_used") or [],
        "degraded_engines": grounding.get("degraded_engines") or [],
        "gaps": grounding.get("gaps"),
    }
    return (
        "<automatic_knowledge_grounding>\n"
        "这是运行时在模型调用前自动执行 retrieve_knowledge 得到的权威结果。"
        "创作、诊断、选题和拆解应优先使用这些精确版本；需要正文时再调用 get_resource。"
        "不要改写或猜测 resource_id/resource_version。insufficient_relevance 表示可以创作，"
        "但必须明确没有可复用案例，禁止伪造依据。\n"
        f"{json.dumps(public, ensure_ascii=False, separators=(',', ':'))}\n"
        "</automatic_knowledge_grounding>"
    )


class KnowledgeGroundingMiddleware(AgentMiddleware):
    """每轮自动检索并把权威结果同时提供给模型和持久化工具。"""

    state_schema = KnowledgeGroundingState

    def __init__(
        self,
        *,
        retriever: Callable[[str, int, RunnableConfig], dict[str, Any]] = _default_retriever,
        limit: int = 10,
        io_timeout_seconds: float = 20.0,
    ) -> None:
        self._retriever = retriever
        self._limit = min(max(int(limit), 1), 20)
        self._io_timeout_seconds = max(float(io_timeout_seconds), 1.0)

    def _load(self, state: dict[str, Any], config: RunnableConfig) -> dict[str, Any]:
        latest_request = latest_human_text(state)
        if not latest_request:
            return {
                "knowledge_grounding": {
                    "status": "error",
                    "query": "",
                    "turn_id": _turn_id(config),
                    "error": "MISSING_USER_QUERY",
                },
                "latest_user_request": "",
            }
        query = retrieval_query(state, latest_request)
        try:
            result = self._retriever(query, self._limit, config)
        except Exception as exc:  # noqa: BLE001 - 日志不得含查询正文或底层密钥
            logger.warning("automatic_knowledge_grounding_failed type=%s", type(exc).__name__)
            result = {"error": "KNOWLEDGE_RETRIEVAL_FAILED"}
        return {
            "knowledge_grounding": _grounding_payload(
                query=query,
                result=result,
                turn_id=_turn_id(config),
            ),
            "latest_user_request": latest_request,
        }

    def before_agent(
        self,
        state: KnowledgeGroundingState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        del runtime
        return self._load(dict(state), config)

    async def abefore_agent(
        self,
        state: KnowledgeGroundingState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        del runtime
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._load, dict(state), config),
                timeout=self._io_timeout_seconds,
            )
        except TimeoutError:
            query = latest_human_text(dict(state))
            return {
                "knowledge_grounding": {
                    "status": "error",
                    "query": query,
                    "turn_id": _turn_id(config),
                    "error": "KNOWLEDGE_RETRIEVAL_TIMEOUT",
                },
                "latest_user_request": query,
            }

    def wrap_model_call(self, request, handler):
        grounding = request.state.get("knowledge_grounding")
        if not isinstance(grounding, dict):
            grounding = {"status": "error"}
        modified = request.override(
            system_message=append_to_system_message(
                request.system_message, _prompt_fragment(grounding)
            )
        )
        return handler(modified)

    async def awrap_model_call(self, request, handler):
        grounding = request.state.get("knowledge_grounding")
        if not isinstance(grounding, dict):
            grounding = {"status": "error"}
        modified = request.override(
            system_message=append_to_system_message(
                request.system_message, _prompt_fragment(grounding)
            )
        )
        return await handler(modified)


__all__ = [
    "KnowledgeGroundingMiddleware",
    "KnowledgeGroundingState",
    "latest_human_text",
    "retrieval_query",
]
