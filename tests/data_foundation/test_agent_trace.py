from __future__ import annotations

import json

import pytest
from langchain_core.runnables import RunnableConfig

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
            "content": "私有会话正文",
            "body": "完整文案",
            "profile": {"positive_preferences": ["私有偏好"]},
            "metadata": {"private": True},
            "safe": {"used_count": 3},
        }
    )

    assert payload["query"] == "职场穿搭"
    assert "token" not in payload
    assert "authorization" not in payload
    assert "payload" not in payload
    assert "content" not in payload
    assert "body" not in payload
    assert "profile" not in payload
    assert "metadata" not in payload
    assert payload["safe"] == {"used_count": 3}


def test_sanitize_payload_redacts_nested_urls_raw_output_and_inline_secrets() -> None:
    from data_foundation.agent_trace import REDACTED_URL

    app_token = "bascn-private-app-token"
    payload = sanitize_payload(
        {
            "ok": True,
            "redirect_url": f"https://feishu.cn/base/{app_token}?table=tbl-secret",
            "raw": f"CLI echoed app_token={app_token}",
            "nested": [
                {"message": f"request failed at https://example.test/{app_token}"},
                {"message": f"authorization=Bearer-{app_token}"},
                {"message": f"token={app_token}"},
            ],
        }
    )

    serialized = str(payload)
    assert payload["redirect_url"] == REDACTED_URL
    assert "raw" not in payload
    assert app_token not in serialized
    assert "https://" not in serialized
    assert payload["nested"][2]["message"] == "token=[REDACTED]"


def test_sanitize_payload_turns_exception_into_classification_without_raw_message() -> None:
    secret = "bascn-exception-secret"
    sanitized = sanitize_payload(
        RuntimeError(f"request https://feishu.cn/base/{secret} token={secret}")
    )

    assert sanitized == {"code": "RuntimeError", "message": "tool execution failed"}
    assert secret not in str(sanitized)


def test_sanitize_payload_redacts_quoted_json_secret_assignments() -> None:
    secrets = ("super-private-token", "cred-secret", "client-secret", "api-secret")

    sanitized = sanitize_payload(
        '{"token":"super-private-token","nested":{"app_token":"super-private-token"},'
        '"credentials":"cred-secret","client_secret":"client-secret","api_key":"api-secret"}'
    )

    assert all(secret not in sanitized for secret in secrets)
    assert sanitized.count("[REDACTED]") == 5


def test_sanitize_payload_drops_all_known_secret_key_spellings() -> None:
    sanitized = sanitize_payload(
        {
            "credentials": "cred-secret",
            "client-secret": "client-secret",
            "clientSecret": "client-camel-secret",
            "api-key": "api-secret",
            "private_key": "private-secret",
            "secretKey": "key-secret",
            "safe": True,
        }
    )

    assert sanitized == {"safe": True}


def test_build_trace_event_sanitizes_envelope_fields_and_drops_unknown_keys() -> None:
    secrets = ("trace-secret", "run-secret", "turn-secret", "event-secret", "label-secret")
    event = build_trace_event(
        type="xhs.trace.run.started",
        trace_id="https://example.test/trace-secret",
        run_id="token=run-secret",
        turn_id='{"token":"turn-secret"}',
        event_id="https://example.test/event-secret",
        label="authorization=label-secret",
        visibility="user",
        seq=1,
        arbitrary="token=must-not-be-streamed",
    )

    serialized = json.dumps(event, ensure_ascii=False)
    assert all(secret not in serialized for secret in secrets)
    assert "must-not-be-streamed" not in serialized
    assert "arbitrary" not in event
    assert event["trace_id"].startswith("trace-")
    assert event["run_id"].startswith("run-")
    assert event["turn_id"].startswith("turn-")
    assert event["event_id"].startswith("event-")


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


def test_trace_tool_wrapper_emits_started_and_completed(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))

    @tool
    def sample_tool(query: str, config: dict | None = None) -> dict:
        """Search sample resources."""
        return {"ok": True, "results": [1, 2, 3]}

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="查找相关素材")
    result = wrapped.func(
        "职场穿搭",
        config={"configurable": {"thread_id": "thread-1", "run_id": "run-1", "turn_id": "turn-1"}},
    )

    assert result == {"ok": True, "results": [1, 2, 3]}
    assert [event["type"] for event in emitted] == ["xhs.trace.tool.started", "xhs.trace.tool.completed"]
    assert emitted[0]["label"] == "查找相关素材"
    assert emitted[0]["safe_args"]["positional_arg_count"] == 1
    assert emitted[0]["safe_args"]["keyword_arg_names"] == ["config"]
    assert "职场穿搭" not in str(emitted[0]["safe_args"])
    assert "safe_result" not in emitted[1]
    assert emitted[1]["metrics"]["found_count"] == 3
    assert emitted[0]["tool_call_id"].startswith("xhs-direct-")
    assert emitted[1]["tool_call_id"] == emitted[0]["tool_call_id"]
    assert emitted[0]["seq"] < emitted[1]["seq"]


def test_trace_tool_wrapper_records_no_argument_or_result_values(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))
    secret = "bascn-no-trace-secret"

    @tool
    def syncing_tool(title: str, config: dict | None = None) -> dict:
        """Return the same redirect shape as the Feishu synchronization tool."""

        return {
            "ok": True,
            "redirect_url": f"https://feishu.cn/base/{secret}?table=tbl-1",
            "raw": f"token={secret}",
        }

    wrapped = trace_tool(syncing_tool, stage_id="persist", label="同步飞书")
    result = wrapped.func(
        title=f"私密标题-{secret}",
        config={"configurable": {"thread_id": "thread-1", "turn_id": "turn-1"}},
    )

    assert secret in result["redirect_url"]  # 业务返回不被 trace 包装器篡改
    assert emitted[0]["safe_args"] == {
        "positional_arg_count": 0,
        "keyword_arg_names": ["config", "title"],
    }
    assert "safe_result" not in emitted[1]
    assert secret not in str(emitted)


def test_trace_metrics_summarize_unified_retrieval_without_evidence_values() -> None:
    from data_foundation.agent_trace import _metrics_from_result

    secret = "private-evidence-title"
    metrics = _metrics_from_result(
        {
            "retrieval_mode": "hybrid",
            "evidence": [{"title": secret}, {"title": "another"}],
            "engines_used": ["semantic", "keyword", "graph"],
            "degraded_engines": [{"engine": "graph", "reason_code": "UNAVAILABLE"}],
        }
    )

    assert metrics == {
        "found_count": 2,
        "retrieval_mode": "hybrid",
        "engine_count": 3,
        "degraded_engine_count": 1,
    }
    assert secret not in str(metrics)


def test_trace_tool_wrapper_never_emits_raw_exception_text(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))
    secret = "bascn-runtime-secret"

    @tool
    def failing_tool(config: dict | None = None) -> dict:
        """Fail after an upstream client leaked a credential in its exception text."""

        raise RuntimeError(f"GET https://feishu.cn/base/{secret} app_token={secret}")

    wrapped = trace_tool(failing_tool, stage_id="persist", label="同步飞书")
    with pytest.raises(RuntimeError, match=secret):
        wrapped.func(
            config={"configurable": {"thread_id": "thread-1", "turn_id": "turn-1"}}
        )

    assert [event["type"] for event in emitted] == [
        "xhs.trace.tool.started",
        "xhs.trace.tool.failed",
    ]
    assert emitted[1]["error"] == {
        "code": "RuntimeError",
        "message": "tool execution failed",
    }
    assert secret not in str(emitted)


def test_trace_tool_wrapper_keeps_seq_monotonic_for_same_trace(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))

    @tool
    def sample_tool(query: str, config: dict | None = None) -> dict:
        """Search sample resources."""
        return {"ok": True, "results": [query]}

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="查找相关素材")
    config = {"configurable": {"thread_id": "thread-2", "run_id": "run-monotonic", "turn_id": "turn-2"}}

    wrapped.func("职场穿搭", config=config)
    wrapped.func("通勤包", config=config)

    assert [event["seq"] for event in emitted] == [1, 2, 3, 4]


def test_trace_tool_uses_langgraph_config_turn_id(monkeypatch) -> None:
    """根因 A 回归:被包装工具签名是 config: RunnableConfig | None,langchain 不会注入 config
    (Optional 检测不到)→ 传进包装器的 config 为 None。此时必须从 langgraph get_config()
    contextvar 取本轮真实 turn_id(前端写入的 human 消息 id),否则伪造 turn_id 会让前端官方
    trace 轨道永远匹配不上、只能退兜底轨道。"""
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))
    # 模拟 langgraph 运行上下文:contextvar 提供本轮真实 configurable。
    monkeypatch.setattr(
        "langgraph.config.get_config",
        lambda: {"configurable": {"turn_id": "human-msg-abc", "thread_id": "thread-x", "run_id": "run-x", "trace_id": "run-x"}},
    )

    @tool
    def sample_tool(query: str, config: "dict | None" = None) -> dict:
        """Search sample resources."""
        return {"ok": True, "results": [1]}

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="按语义找相关素材")
    # 关键:不显式传 config(复刻 langchain 因 Optional 注解漏注入的真实情形)。
    wrapped.func("职场穿搭")

    assert emitted, "应 emit 出 trace 事件"
    assert all(event["turn_id"] == "human-msg-abc" for event in emitted)
    assert all(event["trace_id"] == "run-x" for event in emitted)


def test_trace_tool_runtime_config_cannot_be_forged_by_explicit_config(monkeypatch) -> None:
    """LangGraph context is server-owned and must also drive business-tool ACL."""
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))
    monkeypatch.setattr(
        "langgraph.config.get_config",
        lambda: {"configurable": {"turn_id": "ctx-turn", "run_id": "ctx-run"}},
    )

    @tool
    def sample_tool(query: str, config: "dict | None" = None) -> dict:
        """Search sample resources."""
        return {
            "ok": True,
            "turn_id": config["configurable"]["turn_id"],
            "results": [1],
        }

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="按语义找相关素材")
    result = wrapped.func(
        "职场穿搭",
        config={
            "configurable": {
                "turn_id": "explicit-turn",
                "run_id": "explicit-run",
            }
        },
    )

    assert result["turn_id"] == "ctx-turn"
    assert all(event["turn_id"] == "ctx-turn" for event in emitted)
    assert all(event["run_id"] == "ctx-run" for event in emitted)


def test_tool_schemas_hide_config_and_dynamic_trace_identity() -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool
    from data_foundation.tools import data_foundation_tools
    from tools.feishu_actions import feishu_action_tools
    from tools.online_adopt import adopt_online_notes
    from tools.redfox_search import search_xhs_online

    for tool_obj in [
        *data_foundation_tools,
        *feishu_action_tools,
        adopt_online_notes,
        search_xhs_online,
    ]:
        public_schema = tool_obj.tool_call_schema.model_json_schema()
        assert "config" not in public_schema.get("properties", {}), tool_obj.name

    @tool
    def sample_tool(query: str, config: RunnableConfig = None) -> dict:
        """Search sample resources."""

        return {"ok": True, "results": [query]}

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="按语义找相关素材")
    public_properties = wrapped.tool_call_schema.model_json_schema()["properties"]
    validation_properties = wrapped.args_schema.model_json_schema()["properties"]
    assert set(public_properties) == {"query"}
    assert "xhs_trace_tool_call_id" in validation_properties


def test_trace_tool_reuses_real_tool_call_id_and_separates_turns(monkeypatch) -> None:
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr(
        "data_foundation.agent_trace.emit_trace",
        lambda event, **kwargs: emitted.append(event),
    )

    @tool
    def sample_tool(query: str, config: RunnableConfig = None) -> dict:
        """Search sample resources."""

        return {"ok": True, "results": [query]}

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="按语义找相关素材")
    tool_call = {
        "name": "sample_tool",
        "args": {"query": "职场穿搭"},
        "id": "provider-call-stable",
        "type": "tool_call",
    }
    for turn_id in ("turn-a", "turn-a", "turn-b"):
        wrapped.invoke(
            tool_call,
            config={
                "configurable": {
                    "thread_id": "thread-1",
                    "run_id": f"run-{turn_id}",
                    "turn_id": turn_id,
                }
            },
        )

    assert [event["tool_call_id"] for event in emitted] == [
        "provider-call-stable"
    ] * 6
    assert [event["turn_id"] for event in emitted] == [
        "turn-a",
        "turn-a",
        "turn-a",
        "turn-a",
        "turn-b",
        "turn-b",
    ]
