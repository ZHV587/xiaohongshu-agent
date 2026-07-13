from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
import hashlib
import json
import logging
import re
import threading
import time
import uuid
from typing import Annotated, Any

from langchain_core.tools import InjectedToolCallId
from pydantic import create_model


SENSITIVE_KEY_MARKERS = (
    "token",
    "credential",
    "api_key",
    "apikey",
    "client_secret",
    "clientsecret",
    "private_key",
    "privatekey",
    "secret_key",
    "secretkey",
    "authorization",
    "secret",
    "password",
    "dsn",
    "uat",
    "payload",
    # 用户正文、反馈、画像与 Skill 指令不得进入持久化 trace safe_args/safe_result。
    "content",
    "body",
    "feedback",
    "instruction",
    "profile",
    "preference",
    "metadata",
    "hook",
    "cta",
    "structure",
    "success_factor",
    "style_tag",
)

# 这些字段本身就是未经约束的原始输出。即使当前值看起来无害，也不能进入 trace；
# 上游 CLI/HTTP 错误很可能把命令、响应体或凭据原样塞进来。
SENSITIVE_EXACT_KEYS = frozenset(
    {
        "raw",
        "exception",
        "traceback",
        "stack",
        "stacktrace",
        "stderr",
        "stdout",
    }
)

REDACTED_VALUE = "[REDACTED]"
REDACTED_URL = "[REDACTED_URL]"

# URL 的 path/query 也可能承载 app_token（飞书 Base redirect_url 就是这种形态），
# 不能只清 query 参数；trace 并不需要可点击链接，因此整段 URL 一律替换。
_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(?<![\w])[\"']?("
    r"(?:access|refresh|app)[_-]?tokens?|tokens?|authorization|uat|credentials?|"
    r"client[_-]?secret|api[_-]?keys?|private[_-]?key|secret[_-]?key|"
    r"secret|password|dsn"
    r")[\"']?\s*[:=]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;&}\]]+)"
)

TRACE_OPTIONAL_FIELDS = frozenset(
    {
        "thread_id",
        "stage_id",
        "tool_call_id",
        "tool_name",
        "attempt",
        "parent_id",
        "status",
        "summary",
        "metrics",
        "safe_args",
        "error",
        "started_at",
        "ended_at",
        "duration_ms",
    }
)

TERMINAL_EVENT_TYPES = {
    "xhs.trace.run.completed",
    "xhs.trace.run.failed",
    "xhs.trace.stage.completed",
    "xhs.trace.stage.failed",
    "xhs.trace.tool.completed",
    "xhs.trace.tool.failed",
}


class TraceLifecycleError(ValueError):
    pass


@dataclass
class TraceSequencer:
    _next_by_trace: dict[str, int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def next(self, trace_id: str) -> int:
        with self._lock:
            value = self._next_by_trace.get(trace_id, 0) + 1
            self._next_by_trace[trace_id] = value
            return value


_GLOBAL_SEQUENCER = TraceSequencer()
logger = logging.getLogger(__name__)
_TRACE_TOOL_CALL_ID_ARG = "xhs_trace_tool_call_id"


def _sensitive_key(key: Any) -> bool:
    lowered = str(key).strip().lower()
    normalized = lowered.replace("-", "_")
    return normalized in SENSITIVE_EXACT_KEYS or any(
        marker in normalized for marker in SENSITIVE_KEY_MARKERS
    )


def _sanitize_string(value: str) -> str:
    value = _URL_RE.sub(REDACTED_URL, value)
    value = _BEARER_RE.sub(f"Bearer {REDACTED_VALUE}", value)
    return _SECRET_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}={REDACTED_VALUE}", value
    )


def _sanitize_identifier(value: Any, *, prefix: str) -> str:
    """Keep ordinary correlation ids stable but never persist a secret-bearing id."""

    raw = str(value)
    clean = _sanitize_string(raw)
    if clean != raw or any(character.isspace() for character in raw) or len(raw) > 256:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
        return f"{prefix}-{digest}"
    return clean


def sanitize_exception(exc: BaseException) -> dict[str, str]:
    """Return a stable failure shape without persisting the exception message.

    Exception text is an untrusted raw channel: database drivers, HTTP clients and CLIs
    can echo URLs, request bodies or credentials.  The class name is enough for admin
    classification; users already receive the tool's generic failure presentation.
    """

    return {
        "code": exc.__class__.__name__,
        "message": "tool execution failed",
    }


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, BaseException):
        return sanitize_exception(value)
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if _sensitive_key(key):
                continue
            clean[key] = sanitize_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value[:20]]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value[:20]]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def build_trace_event(
    *,
    type: str,
    trace_id: str,
    run_id: str,
    turn_id: str,
    label: str,
    visibility: str,
    sequencer: TraceSequencer | None = None,
    seq: int | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    if not trace_id or not run_id or not turn_id:
        raise ValueError("trace_id, run_id and turn_id are required")
    safe_trace_id = _sanitize_identifier(trace_id, prefix="trace")
    safe_run_id = _sanitize_identifier(run_id, prefix="run")
    safe_turn_id = _sanitize_identifier(turn_id, prefix="turn")
    if seq is None:
        if sequencer is None:
            raise ValueError("seq or sequencer is required")
        seq = sequencer.next(safe_trace_id)
    if seq <= 0:
        raise ValueError("seq must be positive")
    event = {
        "type": _sanitize_string(str(type)),
        "schema_version": 1,
        "event_id": _sanitize_identifier(
            kwargs.pop("event_id", f"xhs-trace-{uuid.uuid4().hex}"),
            prefix="event",
        ),
        "trace_id": safe_trace_id,
        "run_id": safe_run_id,
        "turn_id": safe_turn_id,
        "seq": seq,
        "label": _sanitize_string(str(label)),
        "visibility": _sanitize_string(str(visibility)),
        "ts": datetime.now(UTC).isoformat(),
    }
    for key, value in kwargs.items():
        if key in TRACE_OPTIONAL_FIELDS and not _sensitive_key(key) and value is not None:
            event[key] = sanitize_payload(value)
    return event


def fold_lifecycle(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen_runs: set[str] = set()
    seen_stages: set[tuple[str, str]] = set()
    seen_tools: set[tuple[str, str]] = set()
    for event in sorted(events, key=lambda item: item["seq"]):
        event_type = event["type"]
        trace_id = event["trace_id"]

        if event_type == "xhs.trace.run.started":
            seen_runs.add(trace_id)
            continue

        if event_type in {"xhs.trace.run.completed", "xhs.trace.run.failed"}:
            if trace_id not in seen_runs:
                raise TraceLifecycleError("run.started missing before terminal")
            continue

        if event_type.startswith("xhs.trace.stage.") and event.get("stage_id"):
            key = (trace_id, str(event["stage_id"]))
            if event_type == "xhs.trace.stage.started":
                seen_stages.add(key)
            elif event_type in TERMINAL_EVENT_TYPES and key not in seen_stages:
                raise TraceLifecycleError("stage.started missing before terminal")
            continue

        if event_type.startswith("xhs.trace.tool.") and event.get("tool_call_id"):
            key = (trace_id, str(event["tool_call_id"]))
            if event_type == "xhs.trace.tool.started":
                seen_tools.add(key)
            elif event_type in TERMINAL_EVENT_TYPES and key not in seen_tools:
                raise TraceLifecycleError("tool.started missing before terminal")
    return events


class TraceRepository:
    def __init__(self, conn: Any) -> None:
        self.conn = conn

    def append(self, tenant_id: str, event: dict[str, Any]) -> None:
        self.conn.execute(
            """
            insert into agent_trace_events (
              event_id, tenant_id, thread_id, run_id, turn_id, trace_id, seq,
              event_type, schema_version, stage_id, tool_call_id, tool_name,
              attempt, parent_id, label, visibility, status, summary, metrics,
              safe_args, safe_result, error_code, error_message, started_at,
              ended_at, duration_ms
            ) values (
              %s, %s, %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s,
              %s, %s, %s, %s, %s, %s, %s::jsonb,
              %s::jsonb, %s::jsonb, %s, %s, %s,
              %s, %s
            )
            """,
            (
                event["event_id"],
                tenant_id,
                event.get("thread_id"),
                event["run_id"],
                event["turn_id"],
                event["trace_id"],
                event["seq"],
                event["type"],
                event.get("schema_version", 1),
                event.get("stage_id"),
                event.get("tool_call_id"),
                event.get("tool_name"),
                event.get("attempt"),
                event.get("parent_id"),
                event["label"],
                event["visibility"],
                event.get("status"),
                event.get("summary"),
                json.dumps(event.get("metrics", {}), ensure_ascii=False),
                json.dumps(event.get("safe_args", {}), ensure_ascii=False),
                json.dumps(event.get("safe_result", {}), ensure_ascii=False),
                (event.get("error") or {}).get("code"),
                (event.get("error") or {}).get("message"),
                event.get("started_at"),
                event.get("ended_at"),
                event.get("duration_ms"),
            ),
        )


def get_stream_writer() -> Any:
    from langgraph.config import get_stream_writer as langgraph_get_stream_writer

    return langgraph_get_stream_writer()


def emit_trace(
    event: dict[str, Any],
    *,
    persist: bool = True,
    repository: TraceRepository | None = None,
    tenant_id: str = "default",
) -> None:
    if persist and repository is not None:
        repository.append(tenant_id, event)
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    try:
        writer(event)
    except Exception as exc:  # noqa: BLE001 - trace streaming is best effort
        logger.warning("trace stream emit failed: %s", type(exc).__name__)


def _configurable_of(config: Any) -> dict[str, Any]:
    """从一个 config-like 对象里取 configurable dict(dict 或带属性的对象都兼容)。"""
    if isinstance(config, dict):
        raw = config.get("configurable")
        return raw if isinstance(raw, dict) else {}
    raw = getattr(config, "configurable", None)
    return raw if isinstance(raw, dict) else {}


def _resolve_config(config: Any) -> Any:
    """解析本轮真实 config。

    根因(历史踩坑):被 trace 包装的工具曾把 config 标成 Optional RunnableConfig,
    而 langchain 的 `_get_runnable_config_param` 只认**裸** `RunnableConfig`,Optional(Union)一律
    检测不到 → `StructuredTool._run` 根本不注入 config → 传进包装器的 config 恒为 None →
    `_config_identity(None)` 每次伪造一套新 `run_id/trace_id/turn_id`,turn_id 永远 ≠ 前端写入的
    human 消息 id → 官方 trace 轨道在前端永远匹配不上,只能退兜底轨道。

    修法:优先用 langgraph 的 `get_config()` contextvar 拿本轮真实 configurable(前端 submit 时写入的
    turn_id 在这里),它不依赖工具签名注入,子图(子代理)里同样继承同一 configurable;
    仅当 contextvar 不可用(非 langgraph 运行上下文,如单测直调)时才回退到显式传入的 config。
    """
    try:
        from langgraph.config import get_config

        runtime_config = get_config()
    except RuntimeError:
        return config
    return runtime_config


def _config_identity(config: Any) -> dict[str, str | None]:
    configurable = _configurable_of(config)

    thread_id = configurable.get("thread_id")
    run_id = str(configurable.get("run_id") or thread_id or f"run-{uuid.uuid4().hex}")
    trace_id = str(configurable.get("trace_id") or run_id)
    turn_id = str(configurable.get("turn_id") or thread_id or run_id)
    return {
        "trace_id": trace_id,
        "run_id": run_id,
        "turn_id": turn_id,
        "thread_id": str(thread_id) if thread_id else None,
    }


def _metrics_from_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    metrics: dict[str, Any] = {}
    results = result.get("results")
    if isinstance(results, list):
        metrics["found_count"] = len(results)
    evidence = result.get("evidence")
    if isinstance(evidence, list):
        metrics["found_count"] = len(evidence)
    retrieval_mode = result.get("retrieval_mode")
    if retrieval_mode in {
        "hybrid",
        "semantic_only",
        "keyword_only",
        "insufficient_relevance",
    }:
        metrics["retrieval_mode"] = retrieval_mode
    engines_used = result.get("engines_used")
    if isinstance(engines_used, list):
        metrics["engine_count"] = len(engines_used)
    degraded_engines = result.get("degraded_engines")
    if isinstance(degraded_engines, list):
        metrics["degraded_engine_count"] = len(degraded_engines)
    for key in ("used_count", "excluded_count"):
        value = result.get(key)
        if isinstance(value, int):
            metrics[key] = value
    return metrics


def _inject_trace_tool_call_id(tool_obj: Any) -> None:
    """Extend the validation schema with one runtime-only ToolCall identity field."""

    args_schema = tool_obj.args_schema
    if not isinstance(args_schema, type):
        raise TypeError(f"traced tool {tool_obj.name!r} requires a Pydantic args schema")
    fields = getattr(args_schema, "model_fields", {})
    if _TRACE_TOOL_CALL_ID_ARG in fields:
        raise ValueError(
            f"traced tool {tool_obj.name!r} reserves {_TRACE_TOOL_CALL_ID_ARG!r}"
        )
    tool_obj.args_schema = create_model(
        f"{args_schema.__name__}WithTraceToolCallId",
        __base__=args_schema,
        **{
            _TRACE_TOOL_CALL_ID_ARG: (
                Annotated[str, InjectedToolCallId],
                "",
            )
        },
    )


def trace_tool(tool_obj: Any, *, stage_id: str, label: str) -> Any:
    if getattr(tool_obj, "_xhs_trace_wrapped", False):
        return tool_obj

    original = tool_obj.func
    _inject_trace_tool_call_id(tool_obj)

    @wraps(original)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        injected_tool_call_id = kwargs.pop(_TRACE_TOOL_CALL_ID_ARG, None)
        resolved_config = _resolve_config(kwargs.get("config"))
        identity = _config_identity(resolved_config)
        # Runtime context is server-owned.  Always pass it to the business tool so an
        # explicitly supplied config cannot split trace identity from tenant/actor ACL.
        if resolved_config is not None:
            kwargs = {**kwargs, "config": resolved_config}
        tool_call_id = (
            injected_tool_call_id.strip()
            if isinstance(injected_tool_call_id, str)
            and injected_tool_call_id.strip()
            else f"xhs-direct-{uuid.uuid4().hex}"
        )
        started = build_trace_event(
            type="xhs.trace.tool.started",
            stage_id=stage_id,
            tool_call_id=tool_call_id,
            tool_name=tool_obj.name,
            label=label,
            visibility="user",
            sequencer=_GLOBAL_SEQUENCER,
            # 参数值不是 trace 的业务事实。无论位置/关键字调用都只记录结构，不保存
            # 标题、正文、查询词、CLI 命令或未来新增字段里的任意用户值。
            safe_args={
                "positional_arg_count": len(args),
                "keyword_arg_names": sorted(
                    str(key) for key in kwargs if not _sensitive_key(key)
                ),
            },
            **identity,
        )
        emit_trace(started)
        monotonic_started = time.perf_counter()
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            duration_ms = max(
                0, round((time.perf_counter() - monotonic_started) * 1000)
            )
            failed = build_trace_event(
                type="xhs.trace.tool.failed",
                stage_id=stage_id,
                tool_call_id=tool_call_id,
                tool_name=tool_obj.name,
                label=label,
                visibility="user",
                sequencer=_GLOBAL_SEQUENCER,
                parent_id=started["event_id"],
                duration_ms=duration_ms,
                error=sanitize_exception(exc),
                **identity,
            )
            emit_trace(failed)
            if tool_obj.name == "retrieve_knowledge":
                try:
                    from data_foundation.retrieval_metrics import (
                        prepare_retrieval_error,
                        submit_retrieval_metric,
                    )

                    prepared = prepare_retrieval_error(
                        config=resolved_config,
                        trace_identity=identity,
                        tool_call_id=tool_call_id,
                        latency_ms=duration_ms,
                    )
                    if prepared is not None:
                        submit_retrieval_metric(prepared)
                except Exception as metric_exc:  # noqa: BLE001
                    logger.warning(
                        "retrieval metric capture failed: %s",
                        type(metric_exc).__name__,
                    )
            raise

        duration_ms = max(0, round((time.perf_counter() - monotonic_started) * 1000))

        completed = build_trace_event(
            type="xhs.trace.tool.completed",
            stage_id=stage_id,
            tool_call_id=tool_call_id,
            tool_name=tool_obj.name,
            label=label,
            visibility="user",
            sequencer=_GLOBAL_SEQUENCER,
            parent_id=started["event_id"],
            duration_ms=duration_ms,
            metrics=_metrics_from_result(result),
            # 工具返回结构不受统一契约约束，无法证明未来嵌套字段和值都安全。前端只需
            # 结构化 metrics 呈现结果，因此 trace 不记录任意 raw safe_result。
            **identity,
        )
        emit_trace(completed)
        if tool_obj.name == "retrieve_knowledge":
            try:
                from data_foundation.retrieval_metrics import (
                    prepare_retrieval_result,
                    submit_retrieval_metric,
                )

                prepared = prepare_retrieval_result(
                    config=resolved_config,
                    trace_identity=identity,
                    tool_call_id=tool_call_id,
                    latency_ms=duration_ms,
                    result=result,
                )
                if prepared is not None:
                    submit_retrieval_metric(prepared)
            except Exception as exc:  # noqa: BLE001 - metrics must not break retrieval
                # Only the exception class is operationally useful.  Database/provider
                # messages can contain DSNs, request payloads or credentials.
                logger.warning(
                    "retrieval metric capture failed: %s", type(exc).__name__
                )
        return result

    tool_obj.func = wrapped
    setattr(tool_obj, "_xhs_trace_wrapped", True)
    setattr(tool_obj, "_xhs_trace_stage_id", stage_id)
    return tool_obj


# 工具名 → (stage_id, 中文 label)。主 agent 与执行型子代理共用同一份映射,避免两处漂移。
# stage_id 归类 retrieve/persist,供前端把同类步骤折叠;label 是链上显示的"用了哪个工具"。
TRACE_TOOL_STAGES: dict[str, tuple[str, str]] = {
    "retrieve_knowledge": ("retrieve", "检索知识库"),
    "search_local_note_cards": ("retrieve", "检索本地笔记卡"),
    "get_resource": ("retrieve", "打开原文细看"),
    "get_operations_data": ("retrieve", "读取运营数据"),
    "get_resource_performance": ("retrieve", "读取效果表现"),
    "get_data_foundation_status": ("retrieve", "读取数据底座状态"),
    "get_generated_copy_lifecycle": ("retrieve", "读取文案生命周期"),
    "get_writing_profile": ("retrieve", "加载写作偏好"),
    "get_session_snapshots": ("retrieve", "恢复会话快照"),
    "save_generated_topic": ("persist", "保存选题"),
    "save_generated_copy": ("persist", "保存文案"),
    "save_user_feedback": ("persist", "沉淀反馈"),
    "save_writing_teardown": ("persist", "归档写作拆解"),
    "save_performance_metric": ("persist", "沉淀效果指标"),
    "save_session_snapshot": ("persist", "保存会话快照"),
    "confirm_session_snapshot": ("persist", "确认长期知识"),
    "sync_feishu_resources": ("persist", "同步飞书资源"),
    "sync_copy_to_feishu": ("persist", "同步文案到飞书"),
    "sync_topic_to_feishu": ("persist", "同步选题到飞书"),
    "sync_diagnosis_to_feishu": ("persist", "同步诊断到飞书"),
    "send_review_notification": ("persist", "发送审阅通知"),
    "adopt_online_notes": ("persist", "采纳线上笔记"),
    "search_xhs_online": ("retrieve", "搜索小红书线上"),
    "lark_cli": ("persist", "执行飞书操作"),
}


def with_trace(tools: list[Any]) -> list[Any]:
    """对一组工具按 TRACE_TOOL_STAGES 逐个包 trace;未登记的工具原样返回。

    主 agent 与所有执行型子代理都过这一层,子代理内部的检索/精读因此也会 emit trace 事件,
    并继承父上下文的同一 turn_id → 委派出去的重活真实显示在同一条工具调用链上(根治链条稀疏)。
    """
    wrapped: list[Any] = []
    for tool_obj in tools:
        stage = TRACE_TOOL_STAGES.get(getattr(tool_obj, "name", ""))
        wrapped.append(trace_tool(tool_obj, stage_id=stage[0], label=stage[1]) if stage else tool_obj)
    return wrapped
