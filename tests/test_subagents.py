from unittest.mock import Mock

from subagents import ANALYST_SYSTEM_PROMPT, build_baokuan_analyst


def test_baokuan_analyst_registers_unified_retrieval_tools():
    registry = Mock()
    registry.get_pool.return_value = []

    analyst = build_baokuan_analyst(registry, Mock())
    tool_names = {getattr(tool, "name", "") for tool in analyst["tools"]}

    assert {
        "search_resources",
        "semantic_search_resources",
        "graph_expand",
        "get_resource",
    } <= tool_names


def test_baokuan_analyst_requires_evidence_and_explicit_degradation():
    assert ANALYST_SYSTEM_PROMPT.index("search_resources") < ANALYST_SYSTEM_PROMPT.index("read_xhs_data")
    assert "兜底" in ANALYST_SYSTEM_PROMPT or "回退" in ANALYST_SYSTEM_PROMPT
    assert "resource_id" in ANALYST_SYSTEM_PROMPT
    assert "updated_at" in ANALYST_SYSTEM_PROMPT
    assert "当前数据不足" in ANALYST_SYSTEM_PROMPT
