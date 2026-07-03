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
