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
    assert emitted[1]["metrics"]["found_count"] == 3
    assert emitted[0]["seq"] < emitted[1]["seq"]


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


def test_extract_query_reads_keyword_and_query_only() -> None:
    """检索词只认命名参数 keyword/query,不认位置参数或其它键(避免把 resource_id 误当检索词)。"""
    from data_foundation.agent_trace import _extract_query

    assert _extract_query({"keyword": "露营装备"}) == "露营装备"
    assert _extract_query({"query": "职场穿搭"}) == "职场穿搭"
    assert _extract_query({"keyword": "  帐篷  "}) == "帐篷"  # 去空白
    assert _extract_query({"resource_id": "n1"}) is None  # 非检索词不误取
    assert _extract_query({"keyword": ""}) is None  # 空串不算
    assert _extract_query({}) is None


def test_trace_tool_threads_query_into_events(monkeypatch) -> None:
    """根因修复回归:同工具多次调用此前链上显示完全一样(报告的"根本不是一个东西")。
    真实检索词(keyword/query)必须带进 started/completed 事件,前端才能区分每步搜的是什么。"""
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))

    @tool
    def search_local_note_cards(keyword: str, config: dict | None = None) -> dict:
        """Search local note cards."""
        return {"ok": True, "results": [1, 2]}

    wrapped = trace_tool(search_local_note_cards, stage_id="retrieve", label="检索本地笔记卡")
    config = {"configurable": {"thread_id": "t", "run_id": "r", "turn_id": "u"}}
    # langchain 结构化 dispatch 把工具入参按名传(kwargs),故检索词以 keyword= 到达(见 .invoke 路径)。
    wrapped.func(keyword="露营装备", config=config)

    assert [e["type"] for e in emitted] == ["xhs.trace.tool.started", "xhs.trace.tool.completed"]
    # started 与 completed 都带上真实检索词,供前端每步显示"检索本地笔记卡:露营装备"。
    assert emitted[0]["query"] == "露营装备"
    assert emitted[1]["query"] == "露营装备"


def test_trace_tool_omits_query_for_non_search_tools(monkeypatch) -> None:
    """非搜索类工具(无 keyword/query 命名参数)不带 query 字段,前端据此不拼检索词后缀。"""
    from langchain_core.tools import tool

    from data_foundation.agent_trace import trace_tool

    emitted = []
    monkeypatch.setattr("data_foundation.agent_trace.emit_trace", lambda event, **kwargs: emitted.append(event))

    @tool
    def get_resource(resource_id: str, config: dict | None = None) -> dict:
        """Open a resource."""
        return {"ok": True}

    wrapped = trace_tool(get_resource, stage_id="retrieve", label="打开原文细看")
    wrapped.func(resource_id="n1", config={"configurable": {"thread_id": "t", "run_id": "r", "turn_id": "u"}})

    # build_trace_event 只加非 None kwargs → 无检索词时事件里根本没有 query 键。
    assert "query" not in emitted[0]
    assert "query" not in emitted[1]


def test_trace_tool_prefers_explicit_config_when_it_carries_identity(monkeypatch) -> None:
    """显式传入的 config 已带身份(turn_id/thread_id)时,以它为准,不被 contextvar 覆盖。"""
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
        return {"ok": True, "results": [1]}

    wrapped = trace_tool(sample_tool, stage_id="retrieve", label="按语义找相关素材")
    wrapped.func("职场穿搭", config={"configurable": {"turn_id": "explicit-turn", "run_id": "explicit-run"}})

    assert all(event["turn_id"] == "explicit-turn" for event in emitted)
