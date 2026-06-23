from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _skill_text(name: str) -> str:
    return (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_productized_dbskill_skills_exist_with_dbs_aliases():
    expected = {
        "xhs-slowisfast": "/dbs-slowisfast",
        "xhs-goal": "/dbs-goal",
        "xhs-deconstruct": "/dbs-deconstruct",
        "xhs-good-question": "/dbs-good-question",
    }

    for skill_name, alias in expected.items():
        text = _skill_text(skill_name)
        assert f"name: {skill_name}" in text
        assert alias in text


def test_xhs_system_documents_report_alias():
    text = _skill_text("xhs-system")

    assert "/dbs-report" in text
    assert "报告" in text


def test_router_mentions_productized_dbskill_aliases():
    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")

    for alias in [
        "/dbs-slowisfast",
        "/dbs-goal",
        "/dbs-deconstruct",
        "/dbs-good-question",
        "/dbs-report",
    ]:
        assert alias in prompt
