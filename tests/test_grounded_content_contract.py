"""选题/文案契约回归测试。

单一数据源边界(2026-06-25 retrieval-flow-consolidation 后):
- **检索口径**(统一检索工具、mode 四态、时效/防伪)是 MAIN_SYSTEM_PROMPT §6
  《检索与证据规约》的**唯一事实源**。各创作技能不再重述检索口径,只引用 §6。
- **输出协议契约**(xhs_topics/xhs_copy fence + evidence schema)是 MAIN_SYSTEM_PROMPT 的
  唯一事实源 —— 前端 xhs-blocks.ts 与持久化工具硬依赖,渐进式披露下 agent 可能不读 skill,
  故协议常驻 prompt。SKILL.md 不内嵌 JSON 块,只引用 prompt 的「输出协议」。
- **差异化工作流 know-how**(两步流、save_*/sync_* 落库时机、效果反馈、风格沉淀、质量检查)
  是 topic-content/SKILL.md 的唯一事实源,prompt 不重复。
- **跨边界硬约束**(不编造、数据不足明示)prompt 是每轮兜底,skill 自包含也带一份。

故本测试按"各司其职"断言:检索口径只校验 prompt §6,差异化工作流只校验 SKILL.md,
不再要求 SKILL.md 自含全套检索口径(那是改造前的双份维护,已废除)。
"""
import json
import re
from pathlib import Path

from prompts import MAIN_SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]
_topic_content = (ROOT / ".agents" / "skills" / "topic-content" / "SKILL.md").read_text(encoding="utf-8")
_xhs_copywriting = (ROOT / ".agents" / "skills" / "xhs-copywriting" / "SKILL.md").read_text(encoding="utf-8")
SKILL_CONTRACT = _topic_content + "\n" + _xhs_copywriting

# 检索口径里的工具名 —— 唯一源是 MAIN_SYSTEM_PROMPT §6《检索与证据规约》。
RETRIEVAL_TOOLS = {
    "retrieve_knowledge",
    "get_resource",
    "sync_feishu_resources",
}
# 差异化工作流的持久化/反馈工具 —— 唯一源是 topic-content/SKILL.md。
WORKFLOW_TOOLS = {
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
    "quality",
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


def test_output_protocol_shape_matches_frontend_renderer():
    """回归(Q-1):§5 模板结构必须与前端 xhs-blocks.ts 渲染器一致,否则照权威 prompt 写卡片必渲染失败。
    渲染器要求(富选题契约):topics 是**对象数组**,每个选题对象带 title + 富字段 + 每选题独立 evidence
    (含 relevance/freshness/quality/performance);文案用 title/body/tags(非 copy_text)。"""
    topics_start = MAIN_SYSTEM_PROMPT.index("```xhs_topics")
    copy_start = MAIN_SYSTEM_PROMPT.index("```xhs_copy")
    topics_block = MAIN_SYSTEM_PROMPT[topics_start:copy_start]
    copy_block = MAIN_SYSTEM_PROMPT[copy_start:]

    # 旧的错误结构不得再出现(对象数组 topic_title / copy_text)
    assert "topic_title" not in MAIN_SYSTEM_PROMPT
    assert "copy_text" not in topics_block and "copy_text" not in copy_block.replace(
        "不要用 `copy_text`", ""
    )  # 仅允许出现在"不要用 copy_text"的警示里

    # topics 必须是对象数组:模板里 topics 后跟 [ 且元素是 { 对象(富选题),不再是裸字符串
    import re
    m = re.search(r'"topics"\s*:\s*\[\s*\{', topics_block)
    assert m is not None, "topics 必须是富选题对象数组(形如 \"topics\": [{ ... }])"

    # 每个富选题对象必带 title + 富字段;hotRate 无法得出时省略(不输出 0)
    for field in ('"title"', '"hotRate"', '"angle"', '"kw"', '"rationale"', '"emotional"'):
        assert field in topics_block, f"xhs_topics 富选题缺字段 {field}"

    # 每选题独立 evidence 必带统一检索信号 + score
    for field in ('"score"', '"relevance"', '"freshness"', '"quality"', '"performance"', '"retrieval_mode"'):
        assert field in topics_block, f"xhs_topics evidence 缺三信号字段 {field}"

    # 数据不足分支:insufficient_relevance 时空 evidence + 非空 gaps
    assert "insufficient_relevance" in topics_block
    assert '"gaps"' in topics_block

    # 文案必须用 title/body/tags
    for field in ('"title"', '"body"', '"tags"'):
        assert field in copy_block, f"xhs_copy 缺字段 {field}"


def test_xhs_copy_documents_multi_version_contract():
    """xhs_copy 多版本增量契约(Req 4.1):用户要多版本时输出 versions 数组,
    每项含 label/title/body/tags/cover/note;versions 为可选增量字段(不足 1 项不输出),
    单版本仍保留顶层 title/body/tags 向后兼容。前端按 label 映射 A/B/C。"""
    copy_start = MAIN_SYSTEM_PROMPT.index("```xhs_copy")
    copy_block = MAIN_SYSTEM_PROMPT[copy_start:]

    # versions 增量字段及其每项必填字段必须被文档化
    assert '"versions"' in copy_block, "xhs_copy 缺多版本 versions 字段文档"
    for field in ('"label"', '"title"', '"body"', '"tags"', '"cover"', '"note"'):
        assert field in copy_block, f"xhs_copy versions 项缺字段 {field}"

    # 向后兼容:必须说明可选/不足时省略,且单版本保持顶层 title/body/tags 契约
    assert "顶层仍保留" in copy_block and "省略 `versions`" in copy_block
    # 前端按 label 映射 A/B/C 选择器
    assert '"A"' in copy_block and '"B"' in copy_block


def test_xhs_imitation_saves_before_emission_and_carries_exact_lifecycle_identity():
    """仿写不能只继承全局口号:最接近输出的局部契约必须完整规定先保存、再回填身份。"""
    section_start = MAIN_SYSTEM_PROMPT.index("**子代理报告 → `xhs_imitation`")
    section_end = MAIN_SYSTEM_PROMPT.index("**`xhs_panel`", section_start)
    imitation_section = MAIN_SYSTEM_PROMPT[section_start:section_end]

    # 保存顺序与输入必须在仿写局部契约内明确,避免模型被就近示例引导成先输出后落库。
    assert imitation_section.index("save_writing_teardown") < imitation_section.index("save_generated_copy")
    assert imitation_section.index("save_generated_copy") < imitation_section.index("保存成功后")
    assert "完整 A/B/C `versions`" in imitation_section
    assert "reference_resource_id" in imitation_section and "reference_resource_version" in imitation_section
    assert "唯一来源" in imitation_section and "禁止从 `ImitationReport` 推导" in imitation_section
    assert "保存失败时不得输出带伪造身份" in imitation_section

    # 示例本身就是前端/模型会照抄的契约,必须可解析且携带完整稳定身份。
    match = re.search(r"```xhs_imitation\s*\n(.*?)\n```", imitation_section, re.DOTALL)
    assert match is not None, "缺少 xhs_imitation JSON 示例"
    payload = json.loads(match.group(1))

    for field in ("resource_id", "resource_version", "latest_resource_version", "state_version"):
        assert field in payload, f"xhs_imitation 顶层缺少生命周期字段 {field}"
    assert payload["reference_resource_id"]
    assert payload["reference_resource_version"] > 0
    assert [version["label"] for version in payload["versions"]] == ["A", "B", "C"]
    assert [version["resource_version"] for version in payload["versions"]] == [1, 2, 3]
    assert payload["resource_version"] == payload["versions"][0]["resource_version"]
    assert payload["latest_resource_version"] == payload["versions"][-1]["resource_version"]


def test_prompt_forbids_fabricating_source_freshness():
    assert "未知" in MAIN_SYSTEM_PROMPT
    assert "source_updated_at" in MAIN_SYSTEM_PROMPT
    assert "indexed_at" in MAIN_SYSTEM_PROMPT
    assert '"updated_at"' not in MAIN_SYSTEM_PROMPT  # 不得用裸 updated_at 冒充源端时间


def test_prompt_points_to_skill_workflow():
    """prompt 必须留渐进式披露的钩子:指引 agent 读 topic-content skill。"""
    assert "topic-content" in MAIN_SYSTEM_PROMPT
    assert "SKILL.md" in MAIN_SYSTEM_PROMPT


# ── 检索口径:唯一源是 MAIN_SYSTEM_PROMPT §6《检索与证据规约》──

def test_prompt_owns_retrieval_protocol_as_single_source():
    """检索顺序/工具/mode/时效防伪集中在 §6,是唯一事实源。"""
    assert "检索与证据规约" in MAIN_SYSTEM_PROMPT
    for tool in RETRIEVAL_TOOLS:
        # §6 里工具名可能带调用签名,用代码 span 前缀匹配。
        assert f"`{tool}" in MAIN_SYSTEM_PROMPT, tool
    # mode 四态措辞只在 prompt
    assert "hybrid" in MAIN_SYSTEM_PROMPT
    assert "semantic_only" in MAIN_SYSTEM_PROMPT
    assert "insufficient_relevance" in MAIN_SYSTEM_PROMPT
    assert "keyword_only" in MAIN_SYSTEM_PROMPT
    # 时效防伪集中在 §6
    assert "源端" in MAIN_SYSTEM_PROMPT and "本地索引" in MAIN_SYSTEM_PROMPT


def test_skill_references_retrieval_protocol_not_restates_it():
    """技能引用 §6,不重述检索口径,不出现 mode 字面量。"""
    assert "检索与证据规约" in SKILL_CONTRACT  # 引用钩子
    # mode 字面量只在 prompt §6,技能正文不重述(避免双份维护漂移)
    assert "insufficient_relevance" not in SKILL_CONTRACT
    assert "keyword_only" not in SKILL_CONTRACT


# ── 差异化工作流 know-how:唯一源是 topic-content/SKILL.md ──

def test_skill_owns_persistence_workflow_toolset():
    for tool in WORKFLOW_TOOLS:
        assert f"`{tool}`" in SKILL_CONTRACT, tool


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


def test_skill_records_source_freshness_fields():
    """技能在记录证据时仍要带源端/索引时间字段,未知写"未知"(口径细则在 §6)。"""
    assert "未知" in SKILL_CONTRACT
    assert "source_updated_at" in SKILL_CONTRACT
    assert "indexed_at" in SKILL_CONTRACT
