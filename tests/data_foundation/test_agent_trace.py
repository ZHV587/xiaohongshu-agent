from __future__ import annotations

import pytest

from data_foundation.agent_trace import (
    TraceLifecycleError,
    TraceRepository,
    TraceSequencer,
    build_trace_event,
    emit_trace,
    fold_lifecycle,
    sanitize_payload,
)


def test_build_trace_event_requires_identity_and_assigns_seq() -> None:
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


def test_sanitize_payload_removes_secrets_and_full_payloads() -> None:
    payload = sanitize_payload(
        {
            "query": "职场穿搭",
            "token": "secret-token",
            "authorization": "Bearer abc",
            "payload": {"body": "完整正文不能保存"},
            "safe": {"used_count": 3},
        }
    )

    assert payload["query"] == "职场穿搭"
    assert "token" not in payload
    assert "authorization" not in payload
    assert "payload" not in payload
    assert payload["safe"] == {"used_count": 3}


def test_lifecycle_rejects_terminal_without_started() -> None:
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


def test_repository_enforces_unique_seq(migrated_conn) -> None:
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


def test_emit_trace_writes_custom_event(monkeypatch) -> None:
    written = []

    def fake_writer(event: dict) -> None:
        written.append(event)

    monkeypatch.setattr("data_foundation.agent_trace.get_stream_writer", lambda: fake_writer)
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


def test_emit_trace_noops_outside_langgraph_context(monkeypatch) -> None:
    def missing_writer():
        raise RuntimeError("not in graph context")

    monkeypatch.setattr("data_foundation.agent_trace.get_stream_writer", missing_writer)
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
