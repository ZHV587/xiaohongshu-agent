from pathlib import Path

from prompts import MAIN_SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]
SKILL_CONTRACT = (
    ROOT / ".agents" / "skills" / "topic-content" / "SKILL.md"
).read_text(encoding="utf-8")

REQUIRED_TOOLS = {
    "search_resources",
    "semantic_search_resources",
    "graph_expand",
    "get_resource",
    "sync_feishu_resources",
    "save_generated_topic",
    "save_generated_copy",
    "save_user_feedback",
}
EVIDENCE_FIELDS = {
    "resource_id",
    "title",
    "summary",
    "source_updated_at",
    "indexed_at",
}


def _contracts() -> dict[str, str]:
    return {
        "main prompt": MAIN_SYSTEM_PROMPT,
        "topic-content skill": SKILL_CONTRACT,
    }


def test_contracts_require_unified_postgres_retrieval_without_untracked_fallback():
    for name, contract in _contracts().items():
        assert REQUIRED_TOOLS <= {
            tool for tool in REQUIRED_TOOLS if f"`{tool}`" in contract
        }, name
        assert "创作流程不得调用" in contract, name
        assert "`read_xhs_data`" in contract and "`read_feishu_wiki`" in contract, name
        assert "关键词" in contract and "semantic_search_resources" in contract, name


def test_contracts_define_no_data_degradation_and_sync_suggestion():
    for name, contract in _contracts().items():
        assert "当前数据不足" in contract, name
        assert "`sync_feishu_resources`" in contract, name
        assert "不" in contract and "编" in contract, name


def test_contracts_forbid_fabricating_missing_source_freshness():
    for name, contract in _contracts().items():
        assert "更新时间" in contract, name
        assert "未知" in contract, name
        assert "不得猜" in contract, name
        assert "source_updated_at" in contract, name
        assert "indexed_at" in contract, name
        assert '"updated_at"' not in contract, name


def test_contracts_include_evidence_schema_in_topics_and_copy():
    for name, contract in _contracts().items():
        topics_start = contract.index("```xhs_topics")
        copy_start = contract.index("```xhs_copy")
        topics_contract = contract[topics_start:copy_start]
        copy_contract = contract[copy_start:]

        for block_name, block in {
            "xhs_topics": topics_contract,
            "xhs_copy": copy_contract,
        }.items():
            assert '"evidence"' in block, f"{name} {block_name}"
            for field in EVIDENCE_FIELDS:
                assert f'"{field}"' in block, f"{name} {block_name}: {field}"


def test_contracts_require_creation_memory_persistence():
    for name, contract in _contracts().items():
        assert "`save_generated_topic`" in contract, name
        assert "`save_generated_copy`" in contract, name
        assert "`save_user_feedback`" in contract, name
        assert "最终回复用户前" in contract and "save_generated_topic" in contract, name
        assert "最终回复用户前" in contract and "save_generated_copy" in contract, name
        assert "当前文案 ID" in contract and "target_resource_id" in contract, name
        assert 'feedback_type="revision_request"' in contract, name
