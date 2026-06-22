"""选题/文案契约回归测试。

单一数据源边界(2026-06-22 skills 改造后):
- **输出协议契约**(xhs_topics/xhs_copy fence + evidence schema)是 MAIN_SYSTEM_PROMPT 的
  唯一事实源 —— 前端 xhs-blocks.ts 与 content_rubric 硬依赖,渐进式披露下 agent 可能不读
  skill,故协议常驻 prompt。SKILL.md 不再内嵌 JSON 块,只引用 prompt 的「输出协议」。
- **工作流 know-how**(全套工具名、检索顺序、save_* 调用时机、效果反馈、风格沉淀)是
  topic-content/SKILL.md 的唯一事实源,prompt 不重复。
- **跨边界硬约束**(不编造、数据不足明示)两边都在:prompt 是每轮兜底,skill 是自包含。

故本测试按"各司其职"断言,不再要求两个文件各含全套(那是改造前的双份维护,已废除)。
"""
from pathlib import Path

from prompts import MAIN_SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]
SKILL_CONTRACT = (
    ROOT / ".agents" / "skills" / "topic-content" / "SKILL.md"
).read_text(encoding="utf-8")

# 工作流里应出现的工具名 —— 唯一源是 SKILL.md。
WORKFLOW_TOOLS = {
    "search_resources",
    "semantic_search_resources",
    "graph_expand",
    "get_resource",
    "sync_feishu_resources",
    "save_generated_topic",
    "save_generated_copy",
    "save_user_feedback",
    "save_performance_metric",
    "get_resource_performance",
}
EVIDENCE_FIELDS = {
    "resource_id",
    "title",
    "summary",
    "source_updated_at",
    "indexed_at",
}


# ── 跨边界硬约束:prompt 与 SKILL.md 都必须有(prompt 兜底 + skill 自包含)──

def test_both_forbid_fabrication_and_define_data_shortage():
    for name, contract in {"main prompt": MAIN_SYSTEM_PROMPT, "skill": SKILL_CONTRACT}.items():
        assert "当前数据不足" in contract, name
        assert "不" in contract and "编" in contract, name


# ── 输出协议契约:唯一源是 MAIN_SYSTEM_PROMPT ──

def test_prompt_owns_output_protocol_with_evidence_schema():
    topics_start = MAIN_SYSTEM_PROMPT.index("```xhs_topics")
    copy_start = MAIN_SYSTEM_PROMPT.index("```xhs_copy")
    topics_block = MAIN_SYSTEM_PROMPT[topics_start:copy_start]
    copy_block = MAIN_SYSTEM_PROMPT[copy_start:]
    for block_name, block in {"xhs_topics": topics_block, "xhs_copy": copy_block}.items():
        assert '"evidence"' in block, block_name
        for field in EVIDENCE_FIELDS:
            assert f'"{field}"' in block, f"{block_name}: {field}"


def test_prompt_forbids_fabricating_source_freshness():
    assert "未知" in MAIN_SYSTEM_PROMPT
    assert "source_updated_at" in MAIN_SYSTEM_PROMPT
    assert "indexed_at" in MAIN_SYSTEM_PROMPT
    assert '"updated_at"' not in MAIN_SYSTEM_PROMPT  # 不得用裸 updated_at 冒充源端时间


def test_prompt_points_to_skill_workflow():
    """prompt 必须留渐进式披露的钩子:指引 agent 读 topic-content skill。"""
    assert "topic-content" in MAIN_SYSTEM_PROMPT
    assert "SKILL.md" in MAIN_SYSTEM_PROMPT


# ── 工作流 know-how:唯一源是 topic-content/SKILL.md ──

def test_skill_owns_full_workflow_toolset():
    for tool in WORKFLOW_TOOLS:
        assert f"`{tool}`" in SKILL_CONTRACT, tool


def test_skill_defines_retrieval_order_without_untracked_fallback():
    assert "创作流程不得调用" in SKILL_CONTRACT
    assert "`read_xhs_data`" in SKILL_CONTRACT and "`read_feishu_wiki`" in SKILL_CONTRACT
    assert "关键词" in SKILL_CONTRACT and "semantic_search_resources" in SKILL_CONTRACT
    assert "`sync_feishu_resources`" in SKILL_CONTRACT


def test_skill_defines_creation_memory_persistence_timing():
    assert "最终回复用户前" in SKILL_CONTRACT and "save_generated_topic" in SKILL_CONTRACT
    assert "save_generated_copy" in SKILL_CONTRACT
    assert "当前文案 ID" in SKILL_CONTRACT and "target_resource_id" in SKILL_CONTRACT
    assert 'feedback_type="revision_request"' in SKILL_CONTRACT


def test_skill_defines_performance_feedback_loop():
    assert "`save_performance_metric`" in SKILL_CONTRACT
    assert "`get_resource_performance`" in SKILL_CONTRACT
    assert "发布后" in SKILL_CONTRACT and "点赞" in SKILL_CONTRACT and "收藏" in SKILL_CONTRACT
    assert "过去表现" in SKILL_CONTRACT and "为什么推荐" in SKILL_CONTRACT
    assert "最终回复用户前" in SKILL_CONTRACT and "save_performance_metric" in SKILL_CONTRACT
    assert "不得猜" in SKILL_CONTRACT and "目标内容" in SKILL_CONTRACT


def test_skill_forbids_fabricating_source_freshness():
    assert "更新时间" in SKILL_CONTRACT
    assert "未知" in SKILL_CONTRACT
    assert "不得猜" in SKILL_CONTRACT
    assert "source_updated_at" in SKILL_CONTRACT
    assert "indexed_at" in SKILL_CONTRACT
