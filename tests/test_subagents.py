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
    assert "创作分析不得调用" in ANALYST_SYSTEM_PROMPT
    assert "read_xhs_data" in ANALYST_SYSTEM_PROMPT
    assert "read_feishu_wiki" in ANALYST_SYSTEM_PROMPT
    assert "resource_id" in ANALYST_SYSTEM_PROMPT
    assert "source_updated_at" in ANALYST_SYSTEM_PROMPT
    assert "indexed_at" in ANALYST_SYSTEM_PROMPT
    assert "当前数据不足" in ANALYST_SYSTEM_PROMPT
