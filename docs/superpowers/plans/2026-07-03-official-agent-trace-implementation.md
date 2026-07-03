# Official Agent Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the production execution-chain UI from official LangGraph/DeepAgents streaming events, with stable timing, friendly Chinese presentation, persistence, and browser automation acceptance.

**Architecture:** The backend emits `xhs.trace.*` events through LangGraph `custom` streaming using a dedicated trace helper and tool wrappers; the same helper persists sanitized events to `agent_trace_events`. The frontend consumes official `custom` events into a `TraceStore`, converts them through `TracePresentationAdapter`, and renders a Codex/ClaudeCode-style folded execution panel below the final answer for the matching `turn_id`.

**Tech Stack:** Python 3.11, DeepAgents, LangGraph, LangChain tools, psycopg/PostgreSQL, Next.js 15, React 19, TypeScript, node:test, Playwright.

---

## Source Spec

- `docs/superpowers/specs/2026-07-03-official-agent-trace-design.md`

## File Map

- Create `data_foundation/agent_trace.py`: backend event types, redaction, `seq` allocation, lifecycle validation, `emit_trace`, repository writes.
- Modify `data_foundation/schema.sql`: add `agent_trace_events` table and indexes.
- Create `tests/data_foundation/test_agent_trace.py`: backend trace protocol, redaction, ordering, lifecycle, writer behavior.
- Modify `data_foundation/tools.py`: wrap search/read/write tools with trace events and metrics.
- Modify `tools/feishu_actions.py`: wrap write/sync tools with trace events and safe summaries.
- Modify `agent.py`: wrap assembled tools once during DeepAgents assembly.
- Create `web/src/lib/agent-trace.ts`: frontend trace event schema, reducer, lifecycle checks, presentation adapter.
- Create `web/src/lib/agent-trace.test.ts`: reducer convergence, Chinese presentation, security, lifecycle, multi-turn ordering.
- Modify `web/src/providers/stream-context.ts`: extend `CustomEventType` to include `XhsTraceEvent`.
- Modify `web/src/providers/Stream.tsx`: route `xhs.trace.*` custom events into trace state.
- Create `web/src/providers/trace-context.tsx`: React context for `TracePresentation` by `turnId`.
- Modify `web/src/components/studio/StudioContext.tsx`: derive timeline from messages plus trace presentations.
- Modify `web/src/lib/thinking-trace.ts`: stop deriving production execution chains from tool calls when official trace exists.
- Modify `web/src/components/ds/content/ThinkingAura.tsx`: render `TracePresentation` fields while preserving DS styling and motion.
- Modify `web/src/components/studio/CreationScreen.tsx`: mount trace below the matching assistant answer.
- Create `web/tests/agent-trace-stream.test.ts`: source scan and reducer contract tests.
- Create `web/tests/e2e/agent-trace.spec.ts`: browser automation acceptance for timing, Chinese copy, and no technical leakage.

## Task 1: Backend Trace Protocol And Store

**Files:**
- Create: `data_foundation/agent_trace.py`
- Modify: `data_foundation/schema.sql`
- Test: `tests/data_foundation/test_agent_trace.py`

- [ ] **Step 1: Write failing backend protocol tests**

Create `tests/data_foundation/test_agent_trace.py` with these tests:

```python
from __future__ import annotations

import pytest

from data_foundation.agent_trace import (
    TraceLifecycleError,
    TraceRepository,
    TraceSequencer,
    build_trace_event,
    fold_lifecycle,
    sanitize_payload,
)


def test_build_trace_event_requires_identity_and_assigns_seq():
    sequencer = TraceSequencer()
    event = build_trace_event(
        type="xhs.trace.run.started",
        trace_id="trace-1",
        run_id="run-1",
        turn_id="turn-1",
        label="开始处理",
        visibility="user",
        sequencer=sequencer,
    )

    assert event["event_id"]
    assert event["seq"] == 1
    assert event["trace_id"] == "trace-1"
    assert event["run_id"] == "run-1"
    assert event["turn_id"] == "turn-1"


def test_sanitize_payload_removes_secrets_and_full_payloads():
    payload = sanitize_payload({
        "query": "职场穿搭",
        "token": "secret-token",
        "authorization": "Bearer abc",
        "payload": {"body": "完整正文不能保存"},
        "safe": {"used_count": 3},
    })

    assert payload["query"] == "职场穿搭"
    assert "token" not in payload
    assert "authorization" not in payload
    assert "payload" not in payload
    assert payload["safe"] == {"used_count": 3}


def test_lifecycle_rejects_terminal_without_started():
    events = [
        {
            "event_id": "e1",
            "type": "xhs.trace.tool.completed",
            "trace_id": "trace-1",
            "run_id": "run-1",
            "turn_id": "turn-1",
            "seq": 1,
            "tool_call_id": "tool-1",
            "visibility": "user",
            "label": "查找相关素材",
        }
    ]

    with pytest.raises(TraceLifecycleError, match="tool.started"):
        fold_lifecycle(events)


def test_repository_enforces_unique_seq(migrated_conn):
    repo = TraceRepository(migrated_conn)
    event = build_trace_event(
        type="xhs.trace.run.started",
        trace_id="trace-1",
        run_id="run-1",
        turn_id="turn-1",
        label="开始处理",
        visibility="user",
        seq=1,
    )
    repo.append("default", event)
    duplicate = dict(event)
    duplicate["event_id"] = "another-event"

    with pytest.raises(Exception):
        repo.append("default", duplicate)
```

- [ ] **Step 2: Run backend test and verify failure**

Run:

```powershell
python -m pytest tests/data_foundation/test_agent_trace.py -q
```

Expected: import failure for `data_foundation.agent_trace`.

- [ ] **Step 3: Add schema table**

Append this table to `data_foundation/schema.sql` after `resource_events` indexes:

```sql
create table if not exists agent_trace_events (
  id uuid primary key default gen_random_uuid(),
  event_id text not null unique,
  tenant_id text not null,
  thread_id text,
  run_id text not null,
  turn_id text not null,
  trace_id text not null,
  seq int not null check (seq > 0),
  event_type text not null,
  schema_version int not null default 1,
  stage_id text,
  tool_call_id text,
  tool_name text,
  attempt int,
  parent_id text,
  label text not null,
  visibility text not null check (visibility in ('user', 'admin', 'debug')),
  status text,
  summary text,
  metrics jsonb not null default '{}'::jsonb,
  safe_args jsonb not null default '{}'::jsonb,
  safe_result jsonb not null default '{}'::jsonb,
  error_code text,
  error_message text,
  started_at timestamptz,
  ended_at timestamptz,
  duration_ms int,
  created_at timestamptz not null default now(),
  unique (tenant_id, trace_id, seq)
);

create index if not exists idx_agent_trace_thread_recent
  on agent_trace_events (tenant_id, thread_id, created_at desc);
create index if not exists idx_agent_trace_run_recent
  on agent_trace_events (tenant_id, run_id, created_at desc);
create index if not exists idx_agent_trace_trace_recent
  on agent_trace_events (tenant_id, trace_id, created_at desc);
```

- [ ] **Step 4: Implement backend trace module**

Create `data_foundation/agent_trace.py` with the protocol functions from the test:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import threading
import uuid
from typing import Any

SENSITIVE_KEY_RE = ("token", "credential", "authorization", "secret", "password", "dsn", "uat", "payload")
TERMINAL_EVENTS = {
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
            if any(marker in key.lower() for marker in SENSITIVE_KEY_RE):
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
        if event_type.startswith("xhs.trace.stage.") and event.get("stage_id"):
            key = (trace_id, str(event["stage_id"]))
            if event_type == "xhs.trace.stage.started":
                seen_stages.add(key)
            elif key not in seen_stages:
                raise TraceLifecycleError("stage.started missing before terminal")
        if event_type.startswith("xhs.trace.tool.") and event.get("tool_call_id"):
            key = (trace_id, str(event["tool_call_id"]))
            if event_type == "xhs.trace.tool.started":
                seen_tools.add(key)
            elif event_type in TERMINAL_EVENTS and key not in seen_tools:
                raise TraceLifecycleError("tool.started missing before terminal")
        if event_type in {"xhs.trace.run.completed", "xhs.trace.run.failed"} and trace_id not in seen_runs:
            raise TraceLifecycleError("run.started missing before terminal")
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
              %(event_id)s, %(tenant_id)s, %(thread_id)s, %(run_id)s, %(turn_id)s,
              %(trace_id)s, %(seq)s, %(event_type)s, %(schema_version)s,
              %(stage_id)s, %(tool_call_id)s, %(tool_name)s, %(attempt)s,
              %(parent_id)s, %(label)s, %(visibility)s, %(status)s, %(summary)s,
              %(metrics)s, %(safe_args)s, %(safe_result)s, %(error_code)s,
              %(error_message)s, %(started_at)s, %(ended_at)s, %(duration_ms)s
            )
            """,
            {
                "tenant_id": tenant_id,
                "event_type": event["type"],
                "thread_id": event.get("thread_id"),
                "run_id": event["run_id"],
                "turn_id": event["turn_id"],
                "trace_id": event["trace_id"],
                "seq": event["seq"],
                "event_id": event["event_id"],
                "schema_version": event.get("schema_version", 1),
                "stage_id": event.get("stage_id"),
                "tool_call_id": event.get("tool_call_id"),
                "tool_name": event.get("tool_name"),
                "attempt": event.get("attempt"),
                "parent_id": event.get("parent_id"),
                "label": event["label"],
                "visibility": event["visibility"],
                "status": event.get("status"),
                "summary": event.get("summary"),
                "metrics": event.get("metrics", {}),
                "safe_args": event.get("safe_args", {}),
                "safe_result": event.get("safe_result", {}),
                "error_code": (event.get("error") or {}).get("code"),
                "error_message": (event.get("error") or {}).get("message"),
                "started_at": event.get("started_at"),
                "ended_at": event.get("ended_at"),
                "duration_ms": event.get("duration_ms"),
            },
        )
```

- [ ] **Step 5: Run backend protocol tests**

Run:

```powershell
python -m pytest tests/data_foundation/test_agent_trace.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add data_foundation/agent_trace.py data_foundation/schema.sql tests/data_foundation/test_agent_trace.py
git commit -m "feat: add official agent trace protocol"
```

## Task 2: Official Custom Stream Emission

**Files:**
- Modify: `data_foundation/agent_trace.py`
- Test: `tests/data_foundation/test_agent_trace.py`

- [ ] **Step 1: Add failing writer tests**

Add tests:

```python
def test_emit_trace_writes_custom_event(monkeypatch):
    written = []

    def fake_writer(event):
        written.append(event)

    monkeypatch.setattr("data_foundation.agent_trace.get_stream_writer", lambda: fake_writer)
    from data_foundation.agent_trace import emit_trace

    event = build_trace_event(
        type="xhs.trace.run.started",
        trace_id="trace-2",
        run_id="run-2",
        turn_id="turn-2",
        label="开始处理",
        visibility="user",
        seq=1,
    )
    emit_trace(event, persist=False)

    assert written == [event]


def test_emit_trace_noops_outside_langgraph_context(monkeypatch):
    def missing_writer():
        raise RuntimeError("not in graph context")

    monkeypatch.setattr("data_foundation.agent_trace.get_stream_writer", missing_writer)
    from data_foundation.agent_trace import emit_trace

    event = build_trace_event(
        type="xhs.trace.run.started",
        trace_id="trace-3",
        run_id="run-3",
        turn_id="turn-3",
        label="开始处理",
        visibility="user",
        seq=1,
    )
    emit_trace(event, persist=False)
```

- [ ] **Step 2: Run and verify failure**

```powershell
python -m pytest tests/data_foundation/test_agent_trace.py::test_emit_trace_writes_custom_event tests/data_foundation/test_agent_trace.py::test_emit_trace_noops_outside_langgraph_context -q
```

Expected: import failure for `emit_trace`.

- [ ] **Step 3: Implement `emit_trace` using official LangGraph writer**

Add to `data_foundation/agent_trace.py`:

```python
try:
    from langgraph.config import get_stream_writer
except Exception:
    get_stream_writer = None  # type: ignore[assignment]


def emit_trace(event: dict[str, Any], *, persist: bool = True, repository: TraceRepository | None = None, tenant_id: str = "default") -> None:
    if persist and repository is not None:
        repository.append(tenant_id, event)
    if get_stream_writer is None:
        return
    try:
        writer = get_stream_writer()
    except RuntimeError:
        return
    writer(event)
```

- [ ] **Step 4: Run tests**

```powershell
python -m pytest tests/data_foundation/test_agent_trace.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add data_foundation/agent_trace.py tests/data_foundation/test_agent_trace.py
git commit -m "feat: emit trace through official custom stream"
```

## Task 3: Tool Wrapper Integration

**Files:**
- Modify: `data_foundation/agent_trace.py`
- Modify: `agent.py`
- Test: `tests/test_agent_assembly.py`
- Test: `tests/data_foundation/test_agent_trace.py`

- [ ] **Step 1: Add failing wrapper test**

Add:

```python
def test_trace_tool_wrapper_emits_started_and_completed(monkeypatch):
    from langchain_core.tools import tool
    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))

    @tool
    def sample_tool(query: str) -> dict:
        return {"ok": True, "results": [1, 2, 3]}

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="查找相关素材")
    result = wrapped.func("职场穿搭", config={"configurable": {"thread_id": "thread-1", "run_id": "run-1", "turn_id": "turn-1"}})

    assert result == {"ok": True, "results": [1, 2, 3]}
    assert [event["type"] for event in emitted] == ["xhs.trace.tool.started", "xhs.trace.tool.completed"]
    assert emitted[0]["label"] == "查找相关素材"
    assert emitted[1]["metrics"]["found_count"] == 3
```

- [ ] **Step 2: Run and verify failure**

```powershell
python -m pytest tests/data_foundation/test_agent_trace.py::test_trace_tool_wrapper_emits_started_and_completed -q
```

Expected: import failure for `trace_tool`.

- [ ] **Step 3: Implement `trace_tool`**

Add:

```python
def _config_identity(config: Any) -> dict[str, str]:
    configurable = {}
    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
    trace_id = str(configurable.get("trace_id") or configurable.get("run_id") or f"trace-{uuid.uuid4().hex}")
    run_id = str(configurable.get("run_id") or trace_id)
    turn_id = str(configurable.get("turn_id") or configurable.get("thread_id") or run_id)
    thread_id = configurable.get("thread_id")
    return {"trace_id": trace_id, "run_id": run_id, "turn_id": turn_id, "thread_id": thread_id}


def _metrics_from_result(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    metrics: dict[str, Any] = {}
    results = result.get("results")
    if isinstance(results, list):
        metrics["found_count"] = len(results)
    if isinstance(result.get("used_count"), int):
        metrics["used_count"] = result["used_count"]
    if isinstance(result.get("excluded_count"), int):
        metrics["excluded_count"] = result["excluded_count"]
    return metrics


def trace_tool(tool_obj: Any, *, stage_id: str, label: str) -> Any:
    original = tool_obj.func

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        config = kwargs.get("config")
        identity = _config_identity(config)
        sequencer = TraceSequencer()
        started = build_trace_event(
            type="xhs.trace.tool.started",
            stage_id=stage_id,
            tool_call_id=str(uuid.uuid4()),
            tool_name=tool_obj.name,
            label=label,
            visibility="user",
            sequencer=sequencer,
            safe_args=sanitize_payload(kwargs),
            **identity,
        )
        emit_trace(started)
        try:
            result = original(*args, **kwargs)
        except Exception as exc:
            failed = build_trace_event(
                type="xhs.trace.tool.failed",
                stage_id=stage_id,
                tool_call_id=started["tool_call_id"],
                tool_name=tool_obj.name,
                label=label,
                visibility="user",
                sequencer=sequencer,
                parent_id=started["event_id"],
                error={"message": str(exc), "code": exc.__class__.__name__},
                **identity,
            )
            emit_trace(failed)
            raise
        completed = build_trace_event(
            type="xhs.trace.tool.completed",
            stage_id=stage_id,
            tool_call_id=started["tool_call_id"],
            tool_name=tool_obj.name,
            label=label,
            visibility="user",
            sequencer=sequencer,
            parent_id=started["event_id"],
            metrics=_metrics_from_result(result),
            safe_result=sanitize_payload(result if isinstance(result, dict) else {}),
            **identity,
        )
        emit_trace(completed)
        return result

    tool_obj.func = wrapped
    return tool_obj
```

- [ ] **Step 4: Wire wrappers during assembly**

Modify `agent.py`:

```python
from data_foundation.agent_trace import trace_tool

TRACE_TOOL_STAGES = {
    "semantic_search_resources": ("retrieve", "查找相关素材"),
    "search_resources": ("retrieve", "按关键词补查素材"),
    "search_local_note_cards": ("retrieve", "检索本地笔记卡"),
    "get_resource": ("retrieve", "打开原文细看"),
    "graph_expand": ("retrieve", "顺着图谱找关联"),
    "save_generated_topic": ("persist", "保存选题"),
    "save_generated_copy": ("persist", "保存文案"),
    "sync_copy_to_feishu": ("persist", "同步文案到飞书"),
    "sync_topic_to_feishu": ("persist", "同步选题到飞书"),
    "sync_diagnosis_to_feishu": ("persist", "同步诊断到飞书"),
    "adopt_online_notes": ("persist", "采纳线上笔记"),
    "search_xhs_online": ("retrieve", "搜索小红书线上"),
}


def _with_trace(tools):
    wrapped = []
    for tool_obj in tools:
        stage = TRACE_TOOL_STAGES.get(tool_obj.name)
        wrapped.append(trace_tool(tool_obj, stage_id=stage[0], label=stage[1]) if stage else tool_obj)
    return wrapped


assembled_tools = _with_trace(data_foundation_tools + feishu_action_tools + [search_xhs_online, adopt_online_notes, lark_cli])
```

- [ ] **Step 5: Run targeted tests**

```powershell
python -m pytest tests/data_foundation/test_agent_trace.py tests/test_agent_assembly.py -q
```

Expected: pass.

- [ ] **Step 6: Commit**

```powershell
git add data_foundation/agent_trace.py agent.py tests/data_foundation/test_agent_trace.py tests/test_agent_assembly.py
git commit -m "feat: wrap production tools with trace events"
```

## Task 4: Frontend Trace Schema And Reducer

**Files:**
- Create: `web/src/lib/agent-trace.ts`
- Create: `web/src/lib/agent-trace.test.ts`

- [ ] **Step 1: Write failing TypeScript reducer tests**

Create `web/src/lib/agent-trace.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";
import {
  isXhsTraceEvent,
  reduceTraceEvents,
  toTracePresentation,
  type XhsTraceEvent,
} from "./agent-trace";

function event(overrides: Partial<XhsTraceEvent>): XhsTraceEvent {
  return {
    type: "xhs.trace.tool.completed",
    schema_version: 1,
    event_id: "event-1",
    trace_id: "trace-1",
    run_id: "run-1",
    turn_id: "turn-1",
    seq: 1,
    ts: "2026-07-03T12:00:00.000Z",
    label: "查找相关素材",
    visibility: "user",
    ...overrides,
  };
}

test("isXhsTraceEvent accepts only official custom trace events", () => {
  assert.equal(isXhsTraceEvent(event({})), true);
  assert.equal(isXhsTraceEvent({ type: "ui" }), false);
});

test("reduceTraceEvents dedupes by event_id and sorts by seq", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e3", seq: 3 }),
    event({ event_id: "e1", seq: 1 }),
    event({ event_id: "e3", seq: 3 }),
    event({ event_id: "e2", seq: 2 }),
  ]);

  assert.deepEqual(state.events.map((item) => item.event_id), ["e1", "e2", "e3"]);
});

test("presentation uses friendly Chinese and preserves source ids", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "开始处理" }),
    event({
      event_id: "e2",
      seq: 2,
      type: "xhs.trace.tool.completed",
      stage_id: "retrieve",
      metrics: { found_count: 12, used_count: 3 },
    }),
    event({ event_id: "e3", seq: 3, type: "xhs.trace.run.completed", label: "处理完成" }),
  ]);

  const presentation = toTracePresentation(state);

  assert.equal(presentation.traceId, "trace-1");
  assert.match(presentation.userSummary, /查完/);
  assert.equal(presentation.userStages[0].title, "查找相关素材");
  assert.equal(presentation.userStages[0].metricsText, "找到 12 条，采用 3 条");
  assert.deepEqual(presentation.userStages[0].sourceEventIds, ["e2"]);
});
```

- [ ] **Step 2: Run and verify failure**

```powershell
cd web
npm run test:unit -- agent-trace.test.ts
```

Expected: module not found for `agent-trace`.

- [ ] **Step 3: Implement trace reducer and adapter**

Create `web/src/lib/agent-trace.ts`:

```ts
export interface XhsTraceEvent {
  type: `xhs.trace.${string}`;
  schema_version: 1;
  event_id: string;
  trace_id: string;
  run_id: string;
  turn_id: string;
  thread_id?: string;
  parent_id?: string;
  seq: number;
  stage_id?: string;
  tool_call_id?: string;
  tool_name?: string;
  attempt?: number;
  ts: string;
  label: string;
  summary?: string;
  status?: "pending" | "active" | "done" | "warning" | "error" | "waiting";
  visibility: "user" | "admin" | "debug";
  metrics?: Record<string, number | string | boolean>;
}

export interface TraceRunState {
  traceId: string;
  turnId: string;
  events: XhsTraceEvent[];
  warnings: string[];
}

export interface TracePresentation {
  traceId: string;
  turnId: string;
  status: "active" | "done" | "warning" | "error" | "waiting";
  collapsedByDefault: boolean;
  userSummary: string;
  userStages: Array<{
    id: string;
    title: string;
    summary: string;
    statusText: string;
    metricsText?: string;
    sourceEventIds: string[];
  }>;
  adminDetails: XhsTraceEvent[];
}

export function isXhsTraceEvent(value: unknown): value is XhsTraceEvent {
  const item = value as Partial<XhsTraceEvent>;
  return Boolean(
    item &&
      typeof item.type === "string" &&
      item.type.startsWith("xhs.trace.") &&
      item.schema_version === 1 &&
      typeof item.event_id === "string" &&
      typeof item.trace_id === "string" &&
      typeof item.run_id === "string" &&
      typeof item.turn_id === "string" &&
      typeof item.seq === "number",
  );
}

export function reduceTraceEvents(previous: TraceRunState | undefined, incoming: XhsTraceEvent[]): TraceRunState {
  const byId = new Map<string, XhsTraceEvent>();
  for (const item of previous?.events ?? []) byId.set(item.event_id, item);
  for (const item of incoming) byId.set(item.event_id, item);
  const events = [...byId.values()].sort((a, b) => a.seq - b.seq);
  const first = events[0];
  return {
    traceId: first?.trace_id ?? previous?.traceId ?? "",
    turnId: first?.turn_id ?? previous?.turnId ?? "",
    events,
    warnings: [],
  };
}

function metricsText(metrics: XhsTraceEvent["metrics"]): string | undefined {
  if (!metrics) return undefined;
  const parts: string[] = [];
  if (typeof metrics.found_count === "number") parts.push(`找到 ${metrics.found_count} 条`);
  if (typeof metrics.used_count === "number") parts.push(`采用 ${metrics.used_count} 条`);
  if (typeof metrics.excluded_count === "number") parts.push(`排除 ${metrics.excluded_count} 条`);
  return parts.join("，") || undefined;
}

function statusText(event: XhsTraceEvent): string {
  if (event.type.endsWith(".failed")) return "这一步没完成";
  if (event.type.endsWith(".completed")) return "已完成";
  if (event.status === "waiting") return "等你确认";
  if (event.status === "warning") return "需要留意";
  return "正在处理";
}

export function toTracePresentation(state: TraceRunState): TracePresentation {
  const userEvents = state.events.filter((item) => item.visibility === "user");
  const terminal = userEvents.find((item) => item.type === "xhs.trace.run.completed" || item.type === "xhs.trace.run.failed");
  const stageEvents = userEvents.filter((item) => item.stage_id || item.type.startsWith("xhs.trace.tool."));
  const userStages = stageEvents.map((item) => ({
    id: item.stage_id ?? item.tool_call_id ?? item.event_id,
    title: item.label,
    summary: item.summary ?? item.label,
    statusText: statusText(item),
    metricsText: metricsText(item.metrics),
    sourceEventIds: [item.event_id],
  }));
  return {
    traceId: state.traceId,
    turnId: state.turnId,
    status: terminal?.type === "xhs.trace.run.failed" ? "error" : terminal ? "done" : "active",
    collapsedByDefault: Boolean(terminal),
    userSummary: terminal ? `查完 ${userStages.length} 步` : "正在查素材和历史数据",
    userStages,
    adminDetails: state.events.filter((item) => item.visibility !== "user"),
  };
}
```

- [ ] **Step 4: Run frontend unit tests**

```powershell
cd web
npm run test:unit -- agent-trace.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add web/src/lib/agent-trace.ts web/src/lib/agent-trace.test.ts
git commit -m "feat: add frontend agent trace reducer"
```

## Task 5: Stream Provider And Trace Context

**Files:**
- Modify: `web/src/providers/stream-context.ts`
- Modify: `web/src/providers/Stream.tsx`
- Create: `web/src/providers/trace-context.tsx`
- Create: `web/tests/agent-trace-stream.test.ts`

- [ ] **Step 1: Write failing source contract test**

Create `web/tests/agent-trace-stream.test.ts`:

```ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const streamContext = readFileSync(join(process.cwd(), "src", "providers", "stream-context.ts"), "utf8");
const streamProvider = readFileSync(join(process.cwd(), "src", "providers", "Stream.tsx"), "utf8");

test("custom stream type includes XhsTraceEvent", () => {
  assert.match(streamContext, /XhsTraceEvent/);
  assert.match(streamContext, /CustomEventType:\s*UIMessage \| RemoveUIMessage \| XhsTraceEvent/);
});

test("Stream routes xhs trace events separately from UI events", () => {
  assert.match(streamProvider, /isXhsTraceEvent/);
  assert.match(streamProvider, /appendTraceEvent/);
});
```

- [ ] **Step 2: Run and verify failure**

```powershell
cd web
npm run test:unit -- agent-trace-stream.test.ts
```

Expected: test fails because stream context only supports UI custom events.

- [ ] **Step 3: Add trace context**

Create `web/src/providers/trace-context.tsx`:

```tsx
"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { isXhsTraceEvent, reduceTraceEvents, toTracePresentation, type TracePresentation, type TraceRunState, type XhsTraceEvent } from "@/lib/agent-trace";

interface TraceContextValue {
  presentationsByTurnId: Record<string, TracePresentation>;
  appendTraceEvent: (event: XhsTraceEvent) => void;
  clearTraceEvents: () => void;
}

const TraceContext = createContext<TraceContextValue | null>(null);

export function TraceProvider({ children }: { children: ReactNode }) {
  const [states, setStates] = useState<Record<string, TraceRunState>>({});
  const appendTraceEvent = useCallback((event: XhsTraceEvent) => {
    if (!isXhsTraceEvent(event)) return;
    setStates((prev) => ({
      ...prev,
      [event.trace_id]: reduceTraceEvents(prev[event.trace_id], [event]),
    }));
  }, []);
  const clearTraceEvents = useCallback(() => setStates({}), []);
  const presentationsByTurnId = useMemo(() => {
    const out: Record<string, TracePresentation> = {};
    for (const state of Object.values(states)) {
      const presentation = toTracePresentation(state);
      out[presentation.turnId] = presentation;
    }
    return out;
  }, [states]);
  return <TraceContext.Provider value={{ presentationsByTurnId, appendTraceEvent, clearTraceEvents }}>{children}</TraceContext.Provider>;
}

export function useTraceContext(): TraceContextValue {
  const value = useContext(TraceContext);
  if (!value) throw new Error("useTraceContext must be used within TraceProvider");
  return value;
}
```

- [ ] **Step 4: Extend stream types**

Modify `web/src/providers/stream-context.ts`:

```ts
import type { XhsTraceEvent } from "@/lib/agent-trace";

export const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
    };
    CustomEventType: UIMessage | RemoveUIMessage | XhsTraceEvent;
  }
>;
```

- [ ] **Step 5: Route trace events**

Wrap children with `TraceProvider` in `StreamProvider` and route events in `Stream.tsx`:

```tsx
import { isXhsTraceEvent } from "@/lib/agent-trace";
import { TraceProvider, useTraceContext } from "./trace-context";

// Inside StreamSession:
const { appendTraceEvent } = useTraceContext();

onCustomEvent: (event, options) => {
  if (isStreamUiEvent(event)) {
    options.mutate((prev) => {
      const ui = reduceUiMessages(prev.ui, event);
      return { ...prev, ui };
    });
    return;
  }
  if (isXhsTraceEvent(event)) {
    appendTraceEvent(event);
  }
},

// In StreamProvider return:
return (
  <TraceProvider>
    <StreamSession
      apiKey={apiKey}
      apiUrl={browserApiUrl}
      assistantId={finalAssistantId}
      authScheme={finalAuthScheme || undefined}
    >
      {children}
    </StreamSession>
  </TraceProvider>
);
```

- [ ] **Step 6: Run tests**

```powershell
cd web
npm run test:unit -- agent-trace-stream.test.ts agent-trace.test.ts
```

Expected: pass.

- [ ] **Step 7: Commit**

```powershell
git add web/src/providers/stream-context.ts web/src/providers/Stream.tsx web/src/providers/trace-context.tsx web/tests/agent-trace-stream.test.ts
git commit -m "feat: consume official trace custom events"
```

## Task 6: Timeline Mounting And UI Presentation

**Files:**
- Modify: `web/src/lib/thinking-trace.ts`
- Modify: `web/src/components/studio/StudioContext.tsx`
- Modify: `web/src/components/studio/CreationScreen.tsx`
- Modify: `web/src/components/ds/content/ThinkingAura.tsx`
- Test: `web/src/lib/thinking-trace.test.ts`
- Test: `web/tests/creation-timeline-render.test.ts`

- [ ] **Step 1: Add failing timeline tests**

Add to `web/src/lib/thinking-trace.test.ts`:

```ts
test("official trace presentation mounts below the matching assistant answer", () => {
  const timeline = deriveTimeline(
    [human("按职场穿搭出 1 个选题"), aiText("这是最终回答")],
    {
      tracePresentationsByTurnId: {
        a: {
          traceId: "trace-1",
          turnId: "a",
          status: "done",
          collapsedByDefault: true,
          userSummary: "查完 2 步",
          userStages: [
            { id: "retrieve", title: "查找相关素材", summary: "找到 12 条，采用 3 条", statusText: "已完成", sourceEventIds: ["e1"] },
          ],
          adminDetails: [],
        },
      },
    },
  );

  assert.deepEqual(timeline.map((item) => item.kind), ["user", "ai", "thinking"]);
});
```

- [ ] **Step 2: Run and verify failure**

```powershell
cd web
npm run test:unit -- thinking-trace.test.ts creation-timeline-render.test.ts
```

Expected: type failure because timeline context does not accept official presentations.

- [ ] **Step 3: Extend timeline types**

In `web/src/lib/thinking-trace.ts`, extend `TimelineContext` and `ThinkingRun`:

```ts
import type { TracePresentation } from "@/lib/agent-trace";

export interface ThinkingRun {
  steps: ThinkingStep[];
  logs: ThinkingLog[];
  done: boolean;
  presentation?: TracePresentation;
}

export interface TimelineContext {
  loading?: boolean;
  error?: unknown;
  tracePresentationsByTurnId?: Record<string, TracePresentation>;
}
```

- [ ] **Step 4: Prefer official trace over message-derived trace**

In `deriveTimeline`, after pushing the final AI item for a turn, append the matching presentation:

```ts
const appendOfficialTrace = (turnId: string | undefined) => {
  if (!turnId) return;
  const presentation = context.tracePresentationsByTurnId?.[turnId];
  if (!presentation) return;
  out.push({
    kind: "thinking",
    run: {
      steps: presentation.userStages.map((stage) => ({
        label: stage.title,
        state: presentation.status === "done" ? "done" : presentation.status === "error" ? "active" : "active",
      })),
      logs: presentation.userStages.map((stage) => ({ text: stage.metricsText ?? stage.summary })),
      done: presentation.status === "done",
      presentation,
    },
  });
};
```

Call it with the AI message id if present:

```ts
const turnId = typeof m.id === "string" ? m.id : undefined;
if (prose) {
  out.push({ kind: "ai", text: prose });
  appendOfficialTrace(turnId);
}
```

- [ ] **Step 5: Inject trace context into StudioProvider**

In `web/src/components/studio/StudioContext.tsx`:

```tsx
import { useTraceContext } from "@/providers/trace-context";

const { presentationsByTurnId } = useTraceContext();

const timeline: TimelineItem[] = useMemo(
  () => deriveTimeline(t.messages, { loading: t.isLoading, error: t.error, tracePresentationsByTurnId: presentationsByTurnId }),
  [t.messages, t.isLoading, t.error, presentationsByTurnId],
);
```

- [ ] **Step 6: Render presentation fields in ThinkingAura**

Extend `ThinkingAuraProps`:

```ts
traceSummary?: string;
statusText?: string;
```

In `CreationScreen.tsx`, pass official fields when present:

```tsx
<ThinkingAura
  steps={item.run.steps}
  logs={item.run.logs.length ? item.run.logs : null}
  title={item.run.presentation?.userSummary ?? (item.run.done ? undefined : RESPONSE_LOADING_TEXT)}
  defaultCollapsed={item.run.presentation?.collapsedByDefault ?? item.run.done}
/>
```

- [ ] **Step 7: Run tests**

```powershell
cd web
npm run test:unit -- thinking-trace.test.ts creation-timeline-render.test.ts agent-trace.test.ts
```

Expected: pass.

- [ ] **Step 8: Commit**

```powershell
git add web/src/lib/thinking-trace.ts web/src/lib/thinking-trace.test.ts web/src/components/studio/StudioContext.tsx web/src/components/studio/CreationScreen.tsx web/src/components/ds/content/ThinkingAura.tsx web/tests/creation-timeline-render.test.ts
git commit -m "feat: mount official trace below answers"
```

## Task 7: Friendly Chinese And Security Guardrails

**Files:**
- Modify: `web/src/lib/agent-trace.ts`
- Modify: `web/src/lib/agent-trace.test.ts`
- Modify: `web/tests/warning-hygiene.test.ts`

- [ ] **Step 1: Add failing Chinese guard test**

Add:

```ts
test("ordinary presentation hides engineering words", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "run started" }),
    event({ event_id: "e2", seq: 2, tool_name: "semantic_search_resources", label: "tool completed", metrics: { found_count: 12, used_count: 3 } }),
    event({ event_id: "e3", seq: 3, type: "xhs.trace.run.completed", label: "run completed" }),
  ]);
  const presentation = toTracePresentation(state);
  const visible = JSON.stringify({ summary: presentation.userSummary, stages: presentation.userStages });

  for (const word of ["Agent", "trace", "run", "tool", "custom", "debug", "schema", "payload", "warning", "error", "retry"]) {
    assert.equal(visible.includes(word), false, `ordinary UI leaked ${word}`);
  }
  assert.match(visible, /查找相关素材/);
  assert.match(visible, /找到 12 条/);
});
```

- [ ] **Step 2: Run and verify failure**

```powershell
cd web
npm run test:unit -- agent-trace.test.ts
```

Expected: failure while adapter still uses raw labels.

- [ ] **Step 3: Add presentation dictionary**

In `web/src/lib/agent-trace.ts`:

```ts
const STAGE_TITLES: Record<string, string> = {
  understand: "理解你的需求",
  retrieve: "查找相关素材",
  rank: "筛选可用依据",
  compose: "整理选题/正文",
  validate: "检查依据是否充分",
  persist: "保存/同步结果",
};

const TOOL_TITLES: Record<string, string> = {
  semantic_search_resources: "查找相关素材",
  search_resources: "按关键词补查素材",
  search_local_note_cards: "检索本地笔记卡",
  get_resource: "打开原文细看",
  graph_expand: "顺着图谱找关联",
  save_generated_topic: "保存选题",
  save_generated_copy: "保存文案",
  sync_copy_to_feishu: "同步文案到飞书",
  sync_topic_to_feishu: "同步选题到飞书",
  sync_diagnosis_to_feishu: "同步诊断到飞书",
  adopt_online_notes: "采纳线上笔记",
  search_xhs_online: "搜索小红书线上",
};

function userTitle(event: XhsTraceEvent): string {
  if (event.stage_id && STAGE_TITLES[event.stage_id]) return STAGE_TITLES[event.stage_id];
  if (event.tool_name && TOOL_TITLES[event.tool_name]) return TOOL_TITLES[event.tool_name];
  return "处理当前步骤";
}
```

Use `userTitle(item)` instead of `item.label` in `toTracePresentation`.

- [ ] **Step 4: Run guard tests**

```powershell
cd web
npm run test:unit -- agent-trace.test.ts warning-hygiene.test.ts
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add web/src/lib/agent-trace.ts web/src/lib/agent-trace.test.ts web/tests/warning-hygiene.test.ts
git commit -m "feat: enforce friendly Chinese trace presentation"
```

## Task 8: Browser Automation Acceptance

**Files:**
- Create: `web/tests/e2e/agent-trace.spec.ts`
- Modify: `web/playwright.config.ts` only if the current server config cannot boot the tested page.

- [ ] **Step 1: Add browser acceptance spec**

Create:

```ts
import { expect, test } from "@playwright/test";

test("agent trace renders below answer with friendly Chinese and no engineering words", async ({ page }) => {
  await page.goto("/?section=create");
  await expect(page.getByText("先说一个方向")).toBeVisible();

  const composer = page.getByPlaceholder("比如：按职场穿搭出 3 个选题，要有依据…");
  await composer.fill("按职场穿搭出 1 个选题，要有依据");
  await composer.press("Enter");

  await expect(page.getByText(/查找相关素材|正在查素材和历史数据/)).toBeVisible({ timeout: 30000 });
  await expect(page.getByText(/查完 \d+ 步/)).toBeVisible({ timeout: 60000 });

  const bodyText = await page.locator("body").innerText();
  for (const word of ["trace", "run", "tool", "custom", "debug", "schema", "payload"]) {
    expect(bodyText).not.toContain(word);
  }
});
```

- [ ] **Step 2: Run Playwright against local dev server**

```powershell
cd web
npm run build
npm run dev
```

In a second shell:

```powershell
cd web
npx playwright test tests/e2e/agent-trace.spec.ts --project=chromium
```

Expected: pass, with screenshots/traces available from Playwright output.

- [ ] **Step 3: Commit**

```powershell
git add web/tests/e2e/agent-trace.spec.ts web/playwright.config.ts
git commit -m "test: verify official agent trace in browser"
```

## Task 9: Full Verification And Warning Cleanup

**Files:**
- Modify only files that produce warnings during verification.

- [ ] **Step 1: Run backend targeted suite**

```powershell
python -m pytest tests/data_foundation/test_agent_trace.py tests/test_agent_assembly.py tests/test_public_api_contract.py -q
```

Expected: pass.

- [ ] **Step 2: Run frontend unit suite**

```powershell
cd web
npm run test:unit
```

Expected: pass.

- [ ] **Step 3: Run lint**

```powershell
cd web
npm run lint
```

Expected: zero warnings and zero errors.

- [ ] **Step 4: Run build**

```powershell
cd web
npm run build
```

Expected: successful production build.

- [ ] **Step 5: Fix warnings at source**

For every warning, change the typed code or tests directly. Do not suppress with blanket disables. Re-run the command that produced the warning until it is clean.

- [ ] **Step 6: Commit**

```powershell
git add .
git commit -m "chore: verify trace implementation"
```

## Task 10: Production Deployment Handoff

**Files:**
- Modify: `scripts/deploy.py` only when `python scripts/deploy.py` itself fails.
- Modify: `docs/deployment/server-deployment-rules.md` only when verified production topology has changed.

- [ ] **Step 1: Confirm branch state**

```powershell
git status --short --branch
```

Expected: clean worktree before push, except user-owned files explicitly excluded from this feature.

- [ ] **Step 2: Push local branch**

```powershell
git push origin master
```

Expected: remote accepts push.

- [ ] **Step 3: Deploy using existing production deployment command**

Run:

```powershell
python scripts/deploy.py
```

Expected remote command sequence, already encoded by `scripts/deploy.py`:

```text
cd /home/ubuntu/xiaohongshu-agent && git pull --ff-only origin master
cd /home/ubuntu/xiaohongshu-agent && /home/ubuntu/.local/bin/langgraph build -t xhs-langgraph:latest
cd /home/ubuntu/xiaohongshu-agent && docker compose up -d --build
cd /home/ubuntu/xiaohongshu-agent && docker compose ps
cd /home/ubuntu/xiaohongshu-agent && docker compose exec -T langgraph python scripts/runtime_import_smoke.py
cd /home/ubuntu/xiaohongshu-agent && python3 scripts/deploy_health_check.py --public-url http://127.0.0.1:9091/
```

Expected local result: `python scripts/deploy.py` exits `0`.

- [ ] **Step 4: Production smoke**

Verify:

```text
/api/me returns 200
Web create page loads
One real prompt produces final answer
Execution chain appears below the final answer
Execution chain uses friendly Chinese
No console/page/network errors
```

- [ ] **Step 5: Commit deployment-script changes when the deployment command was changed**

```powershell
git add scripts/deploy.py docs/deployment/server-deployment-rules.md tests/test_deploy_script.py
git commit -m "chore: align trace production deployment"
git push origin master
```

## Self-Review

**Spec coverage:** Covered official stream modes, custom events, no private patching, production persistence, strict no fallback from messages, Chinese presentation adapter, timing invariants, browser automation, and deployment. Mobile remains intentionally out of scope.

**Placeholder scan:** This plan contains no reserved placeholder markers and no intentionally blank implementation steps. Deployment uses the repository’s real command `python scripts/deploy.py`, which performs fast-forward pull, LangGraph build, Docker Compose rollout, runtime import smoke, and health check.

**Type consistency:** Backend event fields use `event_id`, `trace_id`, `run_id`, `turn_id`, `seq`, `attempt`, `stage_id`, `tool_call_id`. Frontend uses matching camel/snake names only inside typed `XhsTraceEvent`; `sourceEventIds` exists only in `TracePresentation`.
