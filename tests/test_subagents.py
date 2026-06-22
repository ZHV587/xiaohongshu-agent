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


def test_humanizer_editor_properties():
    from subagents import HUMANIZER_SYSTEM_PROMPT, build_humanizer_editor
    registry = Mock()
    registry.get_pool.return_value = []

    editor = build_humanizer_editor(registry, Mock())
    assert editor["name"] == "humanizer-editor"
    assert editor["tools"] == []  # relies on default tools like write_file
    assert "此外" in HUMANIZER_SYSTEM_PROMPT
    assert "至关重要" in HUMANIZER_SYSTEM_PROMPT
    assert "三段式" in HUMANIZER_SYSTEM_PROMPT
    assert "write_file" in HUMANIZER_SYSTEM_PROMPT
    # 假施动/名词化空转 —— 跨语言通用的 AI 腔,点名施动者
    assert "数据告诉我们" in HUMANIZER_SYSTEM_PROMPT
    # 交付前五维自检打分,低于阈值重写
    assert "35/50" in HUMANIZER_SYSTEM_PROMPT

