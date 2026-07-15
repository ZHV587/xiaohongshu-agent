"""DeepAgents 原生 middleware：每轮自动为创作上下文做统一知识检索。

这里不创建新的 Agent 循环。middleware 只在 DeepAgents 的 ``before_agent`` 扩展点
调用既有 ``retrieve_knowledge`` 工具，并把结果写入私有 state；模型看到的是同一份结果
的只读提示片段，持久化工具则通过 ``InjectedState`` 取得权威副本。
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import copy
import json
import logging
import re
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, Annotated, Any, NotRequired

from deepagents.middleware._utils import append_to_system_message
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import PrivateStateAttr
from data_foundation.writing_context import WritingContext, context_from_state
from data_foundation.retrieval_policy import infer_retrieval_task

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
    writing_profile_grounding: NotRequired[
        Annotated[dict[str, Any], PrivateStateAttr]
    ]


class GroundingCache:
    """同一 DeepAgents run 内共享检索/画像，避免主控与子代理重复 I/O。"""

    def __init__(self, *, ttl_seconds: float = 60.0, max_entries: int = 1024) -> None:
        self.ttl_seconds = max(float(ttl_seconds), 1.0)
        self.max_entries = max(int(max_entries), 16)
        self._items: OrderedDict[tuple[Any, ...], tuple[float, Any]] = OrderedDict()
        self._lock = Lock()

    def get(self, key: tuple[Any, ...]) -> Any | None:
        now = monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return copy.deepcopy(value)

    def put(self, key: tuple[Any, ...], value: Any) -> None:
        with self._lock:
            self._items[key] = (monotonic() + self.ttl_seconds, copy.deepcopy(value))
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)


_SHARED_GROUNDING_CACHE = GroundingCache()


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


def _default_retriever(
    query: str,
    limit: int,
    config: RunnableConfig,
    context: WritingContext,
    task_type: str,
) -> dict[str, Any]:
    # 懒导入避免工具模块装配时形成循环；调用的是公开统一工具，而非旁路召回引擎。
    from data_foundation.tools import retrieve_knowledge

    result = retrieve_knowledge.invoke(
        {
            "query": query,
            "limit": limit,
            "account_id": context.account_id,
            "niche": context.niche,
            "task_type": task_type,
        },
        config=config,
    )
    return dict(result) if isinstance(result, dict) else {"error": "INVALID_RETRIEVAL_RESULT"}


def _default_profile_loader(
    config: RunnableConfig, context: WritingContext
) -> dict[str, Any]:
    from data_foundation.tools import get_writing_profile

    result = get_writing_profile.invoke(
        {"account_id": context.account_id, "niche": context.niche},
        config=config,
    )
    return dict(result) if isinstance(result, dict) else {"error": "INVALID_PROFILE_RESULT"}


def _turn_id(config: RunnableConfig) -> str | None:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    value = configurable.get("turn_id") if isinstance(configurable, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


def _cache_identity(config: RunnableConfig) -> tuple[str, str, str] | None:
    try:
        from data_foundation.permissions import actor_from_config, default_tenant_id

        actor = actor_from_config(config)
    except Exception:  # noqa: BLE001 - 无权威身份就禁用缓存，绝不跨用户复用
        return None
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    run = ""
    if isinstance(configurable, dict):
        run = str(
            configurable.get("run_id")
            or configurable.get("turn_id")
            or configurable.get("thread_id")
            or ""
        ).strip()
    if not run:
        return None
    return default_tenant_id(), actor, run


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


def _profile_payload(
    *, result: dict[str, Any], context: WritingContext
) -> dict[str, Any]:
    if result.get("ok") is not True:
        return {
            "status": "error",
            "writing_context": context.payload(),
            "error": "WRITING_PROFILE_LOAD_FAILED",
        }
    raw_profile = result.get("profile")
    if raw_profile is not None and not isinstance(raw_profile, dict):
        return {
            "status": "error",
            "writing_context": context.payload(),
            "error": "INVALID_PROFILE_RESULT",
        }
    profile = None
    if isinstance(raw_profile, dict):
        content = raw_profile.get("content")
        if not isinstance(content, dict):
            return {
                "status": "error",
                "writing_context": context.payload(),
                "error": "INVALID_PROFILE_RESULT",
            }
        allowed_content = {
            key: copy.deepcopy(content[key])
            for key in (
                "preferred_ranges",
                "preferences",
                "revision_tendencies",
                "explicit_feedback_traits",
                "avoid_preferences",
                "outcome_summary",
                "writing_context",
            )
            if key in content
        }
        profile = {
            "resource_id": raw_profile.get("resource_id"),
            "resource_version": raw_profile.get("resource_version"),
            "observation_count": raw_profile.get("observation_count"),
            "requested_scope": raw_profile.get("requested_scope"),
            "resolved_scope": raw_profile.get("resolved_scope"),
            "content": allowed_content,
        }
    return {
        "status": "ready",
        "writing_context": context.payload(),
        "profile": profile,
    }


def _prompt_fragment(
    grounding: dict[str, Any], profile_grounding: dict[str, Any] | None = None
) -> str:
    status = grounding.get("status")
    if status != "ready":
        knowledge_fragment = (
            "<automatic_knowledge_grounding>\n"
            "自动知识检索本轮不可用。不得编造历史案例，也不得保存新生成文案；"
            "可以说明暂时无法完成有依据的生成。\n"
            "</automatic_knowledge_grounding>"
        )
    else:
        public = {
            "retrieval_mode": grounding.get("retrieval_mode"),
            "evidence": grounding.get("evidence") or [],
            "engines_used": grounding.get("engines_used") or [],
            "degraded_engines": grounding.get("degraded_engines") or [],
            "gaps": grounding.get("gaps"),
            "writing_context": grounding.get("writing_context"),
        }
        knowledge_fragment = (
            "<automatic_knowledge_grounding>\n"
            "这是运行时在模型调用前自动执行 retrieve_knowledge 得到的权威结果。"
            "创作、诊断、选题和拆解应优先使用这些精确版本；需要正文时再调用 get_resource。"
            "不要改写或猜测 resource_id/resource_version。insufficient_relevance 表示可以创作，"
            "但必须明确没有可复用案例，禁止伪造依据。\n"
            f"{json.dumps(public, ensure_ascii=False, separators=(',', ':'))}\n"
            "</automatic_knowledge_grounding>"
        )
    profile = profile_grounding if isinstance(profile_grounding, dict) else {}
    if profile.get("status") == "ready" and isinstance(profile.get("profile"), dict):
        scoped_profile = profile["profile"]
        profile_public = {
            "requested_scope": scoped_profile.get("requested_scope"),
            "resolved_scope": scoped_profile.get("resolved_scope"),
            **dict(scoped_profile.get("content") or {}),
        }
        profile_instruction = (
            "以下画像由运行时按当前账号/垂类自动加载。优先遵守 preferences，"
            "同时规避 avoid_preferences；不得把画像来源或私有内容泄露给用户。"
        )
    else:
        profile_public = None
        profile_instruction = "当前范围没有可用画像，按通用小红书写作规范执行，不得猜测用户偏好。"
    return (
        knowledge_fragment
        + "\n<automatic_writing_profile>\n"
        + profile_instruction
        + "\n"
        + json.dumps(profile_public, ensure_ascii=False, separators=(",", ":"))
        + "\n</automatic_writing_profile>"
    )


class KnowledgeGroundingMiddleware(AgentMiddleware):
    """每轮自动检索并把权威结果同时提供给模型和持久化工具。"""

    state_schema = KnowledgeGroundingState

    def __init__(
        self,
        *,
        retriever: Callable[
            [str, int, RunnableConfig, WritingContext, str], dict[str, Any]
        ] = _default_retriever,
        profile_loader: Callable[
            [RunnableConfig, WritingContext], dict[str, Any]
        ] = _default_profile_loader,
        limit: int = 10,
        io_timeout_seconds: float = 20.0,
        cache: GroundingCache = _SHARED_GROUNDING_CACHE,
    ) -> None:
        self._retriever = retriever
        self._profile_loader = profile_loader
        self._limit = min(max(int(limit), 1), 20)
        self._io_timeout_seconds = max(float(io_timeout_seconds), 1.0)
        self._cache = cache

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
        context = context_from_state(state)
        task_type = infer_retrieval_task(query)
        identity = _cache_identity(config)
        retrieval_cache_key = (
            "retrieval",
            *(identity or ()),
            query,
            context.scope_key,
            task_type,
            self._limit,
        )
        profile_cache_key = (
            "profile",
            *(identity or ()),
            context.scope_key,
        )
        try:
            result = self._cache.get(retrieval_cache_key) if identity else None
            if result is None:
                result = self._retriever(
                    query, self._limit, config, context, task_type
                )
                if identity and result.get("retrieval_mode") in _VALID_MODES:
                    self._cache.put(retrieval_cache_key, result)
        except Exception as exc:  # noqa: BLE001 - 日志不得含查询正文或底层密钥
            logger.warning("automatic_knowledge_grounding_failed type=%s", type(exc).__name__)
            result = {"error": "KNOWLEDGE_RETRIEVAL_FAILED"}
        try:
            profile_result = self._cache.get(profile_cache_key) if identity else None
            if profile_result is None:
                profile_result = self._profile_loader(config, context)
                if identity and profile_result.get("ok") is True:
                    self._cache.put(profile_cache_key, profile_result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("automatic_writing_profile_failed type=%s", type(exc).__name__)
            profile_result = {"error": "WRITING_PROFILE_LOAD_FAILED"}
        return {
            "knowledge_grounding": {
                **_grounding_payload(
                query=query,
                result=result,
                turn_id=_turn_id(config),
                ),
                "writing_context": context.payload(),
                "task_type": task_type,
            },
            "latest_user_request": latest_request,
            "writing_profile_grounding": _profile_payload(
                result=profile_result,
                context=context,
            ),
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
        profile_grounding = request.state.get("writing_profile_grounding")
        modified = request.override(
            system_message=append_to_system_message(
                request.system_message, _prompt_fragment(grounding, profile_grounding)
            )
        )
        return handler(modified)

    async def awrap_model_call(self, request, handler):
        grounding = request.state.get("knowledge_grounding")
        if not isinstance(grounding, dict):
            grounding = {"status": "error"}
        profile_grounding = request.state.get("writing_profile_grounding")
        modified = request.override(
            system_message=append_to_system_message(
                request.system_message, _prompt_fragment(grounding, profile_grounding)
            )
        )
        return await handler(modified)


__all__ = [
    "GroundingCache",
    "KnowledgeGroundingMiddleware",
    "KnowledgeGroundingState",
    "latest_human_text",
    "retrieval_query",
]
