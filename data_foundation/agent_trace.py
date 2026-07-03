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


def _config_identity(config: Any) -> dict[str, str | None]:
    configurable: dict[str, Any] = {}
    if isinstance(config, dict):
        raw = config.get("configurable")
        if isinstance(raw, dict):
            configurable = raw
    else:
        raw = getattr(config, "configurable", None)
        if isinstance(raw, dict):
            configurable = raw

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
        identity = _config_identity(kwargs.get("config"))
        tool_call_id = f"xhs-tool-{uuid.uuid4().hex}"
        started = build_trace_event(
            type="xhs.trace.tool.started",
            stage_id=stage_id,
            tool_call_id=tool_call_id,
            tool_name=tool_obj.name,
            label=label,
            visibility="user",
            sequencer=_GLOBAL_SEQUENCER,
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
