from __future__ import annotations

from pathlib import Path


def test_agent_source_wraps_trace_enabled_tools() -> None:
    src = Path("agent.py").read_text(encoding="utf-8")

    assert "from data_foundation.agent_trace import trace_tool" in src
    assert "TRACE_TOOL_STAGES" in src
    assert "semantic_search_resources" in src
    assert "sync_copy_to_feishu" in src
    assert "adopt_online_notes" in src
    assert "assembled_tools = _with_trace(" in src
