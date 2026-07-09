from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import threading
import uuid
from typing import Any


SENSITIVE_KEY_MARKERS = (
    "token",
    "credential",
    "authorization",
    "secret",
    "password",
    "dsn",
    "uat",
    "payload",
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


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            if any(marker in key.lower() for marker in SENSITIVE_KEY_MARKERS):
                continue
            clean[key] = sanitize_payload(item)
        return clean
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value[:20]]
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
    if seq is None:
        if sequencer is None:
            raise ValueError("seq or sequencer is required")
        seq = sequencer.next(trace_id)
    if seq <= 0:
        raise ValueError("seq must be positive")
    event = {
        "type": type,
        "schema_version": 1,
        "event_id": kwargs.pop("event_id", f"xhs-trace-{uuid.uuid4().hex}"),
        "trace_id": trace_id,
        "run_id": run_id,
        "turn_id": turn_id,
        "seq": seq,
        "label": label,
        "visibility": visibility,
        "ts": datetime.now(UTC).isoformat(),
    }
    for key, value in kwargs.items():
        if value is not None:
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
    writer(event)


def _configurable_of(config: Any) -> dict[str, Any]:
    """从一个 config-like 对象里取 configurable dict(dict 或带属性的对象都兼容)。"""
    if isinstance(config, dict):
        raw = config.get("configurable")
        return raw if isinstance(raw, dict) else {}
    raw = getattr(config, "configurable", None)
    return raw if isinstance(raw, dict) else {}


def _resolve_config(config: Any) -> Any:
    """解析本轮真实 config。

    根因(历史踩坑):被 trace 包装的工具签名是 `config: RunnableConfig | None = None`,
    而 langchain 的 `_get_runnable_config_param` 只认**裸** `RunnableConfig`,Optional(Union)一律
    检测不到 → `StructuredTool._run` 根本不注入 config → 传进包装器的 config 恒为 None →
    `_config_identity(None)` 每次伪造一套新 `run_id/trace_id/turn_id`,turn_id 永远 ≠ 前端写入的
    human 消息 id → 官方 trace 轨道在前端永远匹配不上,只能退兜底轨道。

    修法:优先用 langgraph 的 `get_config()` contextvar 拿本轮真实 configurable(前端 submit 时写入的
    turn_id 在这里),它不依赖工具签名注入,子图(子代理)里同样继承同一 configurable;
    仅当 contextvar 不可用(非 langgraph 运行上下文,如单测直调)时才回退到显式传入的 config。
    """
    explicit_conf = _configurable_of(config)
    if explicit_conf.get("turn_id") or explicit_conf.get("thread_id"):
        return config
    try:
        from langgraph.config import get_config

        runtime_config = get_config()
    except Exception:
        return config
    if _configurable_of(runtime_config):
        return runtime_config
    return config


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


# 工具入参里"这步在搜什么"的命名参数名。只认命名参数(不认位置参数),避免把 get_resource
# 的 resource_id 等非查询词误当检索词。搜索类工具统一用 keyword / query 两个名字。
_QUERY_ARG_KEYS = ("keyword", "query")


def _extract_query(kwargs: dict[str, Any]) -> str | None:
    """从工具 kwargs 里取真实检索词(keyword/query),供思考链每步显示"搜的是什么"。

    根因:同一工具(如 search_local_note_cards / search_xhs_online)在一轮里会以不同 query
    被调多次,但链上只显示固定中文名 + 固定描述 → 两次调用看起来完全一样(报告的"根本不是
    一个东西")。把真实检索词带进 trace 事件,链上每步就能区分"检索本地笔记卡:露营装备"与
    "检索本地笔记卡:新手帐篷",不再是无意义的重复。取不到(非搜索类工具)返回 None,不显示。
    """
    for key in _QUERY_ARG_KEYS:
        value = kwargs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _metrics_from_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    metrics: dict[str, Any] = {}
    results = result.get("results")
    if isinstance(results, list):
        metrics["found_count"] = len(results)
    for key in ("used_count", "excluded_count"):
        value = result.get(key)
        if isinstance(value, int):
            metrics[key] = value
    return metrics


def trace_tool(tool_obj: Any, *, stage_id: str, label: str) -> Any:
    if getattr(tool_obj, "_xhs_trace_wrapped", False):
        return tool_obj

    original = tool_obj.func

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        # 本轮真实身份优先取自 langgraph get_config() contextvar(前端写入的 turn_id 在此),
        # 不依赖 config 是否被注入进 kwargs(Optional 注解会让 langchain 漏注入)。
        resolved_config = _resolve_config(kwargs.get("config"))
        identity = _config_identity(resolved_config)
        # 把解析到的真实 config 回填给原始工具:原始工具用它做租户/actor 解析。
        # 仅当调用方未显式带 config(或带的是空 config)时才覆盖,避免踩掉显式传参。
        if resolved_config is not None and not _configurable_of(kwargs.get("config")):
            kwargs = {**kwargs, "config": resolved_config}
        tool_call_id = f"xhs-tool-{uuid.uuid4().hex}"
        # 本步真实检索词(仅搜索类工具有):带进 started/completed/failed 三种事件,
        # 前端每步显示"用哪个工具 + 搜的是什么",让同工具多次调用不再看起来一模一样。
        query = _extract_query(kwargs)
        started = build_trace_event(
            type="xhs.trace.tool.started",
            stage_id=stage_id,
            tool_call_id=tool_call_id,
            tool_name=tool_obj.name,
            label=label,
            visibility="user",
            sequencer=_GLOBAL_SEQUENCER,
            query=query,
            safe_args=sanitize_payload({"args": args, "kwargs": kwargs}),
            **identity,
        )
        emit_trace(started)
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            failed = build_trace_event(
                type="xhs.trace.tool.failed",
                stage_id=stage_id,
                tool_call_id=tool_call_id,
                tool_name=tool_obj.name,
                label=label,
                visibility="user",
                sequencer=_GLOBAL_SEQUENCER,
                parent_id=started["event_id"],
                query=query,
                error={"code": exc.__class__.__name__, "message": str(exc)},
                **identity,
            )
            emit_trace(failed)
            raise

        completed = build_trace_event(
            type="xhs.trace.tool.completed",
            stage_id=stage_id,
            tool_call_id=tool_call_id,
            tool_name=tool_obj.name,
            label=label,
            visibility="user",
            sequencer=_GLOBAL_SEQUENCER,
            parent_id=started["event_id"],
            query=query,
            metrics=_metrics_from_result(result),
            safe_result=sanitize_payload(result if isinstance(result, dict) else {}),
            **identity,
        )
        emit_trace(completed)
        return result

    tool_obj.func = wrapped
    setattr(tool_obj, "_xhs_trace_wrapped", True)
    setattr(tool_obj, "_xhs_trace_stage_id", stage_id)
    return tool_obj


# 工具名 → (stage_id, 中文 label)。主 agent 与执行型子代理共用同一份映射,避免两处漂移。
# stage_id 归类 retrieve/persist,供前端把同类步骤折叠;label 是链上显示的"用了哪个工具"。
TRACE_TOOL_STAGES: dict[str, tuple[str, str]] = {
    "semantic_search_resources": ("retrieve", "按语义找相关素材"),
    "search_resources": ("retrieve", "按关键词补查素材"),
    "search_local_note_cards": ("retrieve", "检索本地笔记卡"),
    "get_resource": ("retrieve", "打开原文细看"),
    "graph_expand": ("retrieve", "顺着图谱找关联"),
    "get_operations_data": ("retrieve", "读取运营数据"),
    "get_resource_performance": ("retrieve", "读取效果表现"),
    "save_generated_topic": ("persist", "保存选题"),
    "save_generated_copy": ("persist", "保存文案"),
    "save_user_feedback": ("persist", "沉淀反馈"),
    "save_performance_metric": ("persist", "沉淀效果指标"),
    "sync_copy_to_feishu": ("persist", "同步文案到飞书"),
    "sync_topic_to_feishu": ("persist", "同步选题到飞书"),
    "sync_diagnosis_to_feishu": ("persist", "同步诊断到飞书"),
    "send_review_notification": ("persist", "发送审阅通知"),
    "adopt_online_notes": ("persist", "采纳线上笔记"),
    "search_xhs_online": ("retrieve", "搜索小红书线上"),
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
