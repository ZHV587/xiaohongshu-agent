from __future__ import annotations

from pathlib import Path


def test_agent_source_wraps_trace_enabled_tools() -> None:
    src = Path("agent.py").read_text(encoding="utf-8")

    # 共享的 trace 包装工具 + stage 映射(agent 与子代理同一份,避免漂移)。
    assert "from data_foundation.agent_trace import TRACE_TOOL_STAGES, with_trace" in src
    assert "assembled_tools = with_trace(" in src


def test_stage_mapping_lives_in_agent_trace() -> None:
    """TRACE_TOOL_STAGES 已收敛到 data_foundation/agent_trace.py 作单一事实源。"""
    src = Path("data_foundation/agent_trace.py").read_text(encoding="utf-8")
    assert "TRACE_TOOL_STAGES" in src
    for name in ("semantic_search_resources", "sync_copy_to_feishu", "adopt_online_notes", "search_local_note_cards"):
        assert name in src
    assert "def with_trace(" in src


def test_subagents_wrap_tools_with_trace() -> None:
    """执行型子代理的工具必须过 with_trace —— 否则委派出去的检索/精读不 emit trace,
    工具调用链会缺失子代理这一大段(报告的思考链稀疏根因 B)。"""
    src = Path("subagents_executor.py").read_text(encoding="utf-8")
    assert "from data_foundation.agent_trace import with_trace" in src
    assert 'with_trace(sub["tools"])' in src
