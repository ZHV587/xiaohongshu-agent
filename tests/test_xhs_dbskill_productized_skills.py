import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _skill_text(name: str) -> str:
    return (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def _frontmatter(name: str) -> str:
    parts = _skill_text(name).split("---")
    return parts[1] if len(parts) >= 3 else _skill_text(name)


def test_productized_dbskill_skills_exist_with_semantic_triggers():
    """由上游 dbskill 产品化而来的 skill 仍存在,且走语义触发(中文短语)。"""
    expected = ["xhs-slowisfast", "xhs-goal", "xhs-deconstruct", "xhs-good-question"]

    for skill_name in expected:
        fm = _frontmatter(skill_name)
        assert f"name: {skill_name}" in fm
        assert len(re.findall(r"「[^」]+」", fm)) >= 2, f"{skill_name} 缺语义触发短语"


def test_xhs_system_documents_report_capability():
    fm = _frontmatter("xhs-system")

    assert "报告" in fm
    assert "「打包报告」" in fm or "「阶段报告」" in fm
