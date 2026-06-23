from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


EXPECTED_SKILL_ALIASES = {
    "xhs-diagnosis": ["/dbs-diagnosis"],
    "xhs-benchmark": ["/dbs-benchmark"],
    "xhs-content": ["/dbs-content"],
    "xhs-content-system": ["/dbs-content-system"],
    "xhs-deconstruct": ["/dbs-deconstruct"],
    "xhs-goal": ["/dbs-goal"],
    "xhs-good-question": ["/dbs-good-question"],
    "xhs-slowisfast": ["/dbs-slowisfast"],
    "xhs-hook": ["/dbs-hook"],
    "xhs-title": ["/dbs-xhs-title"],
    "xhs-audit": ["/dbs-ai-check"],
    "xhs-action": ["/dbs-action"],
    "xhs-decision": ["/dbs-decision"],
    "xhs-learning": ["/dbs-learning", "/dbs-learn"],
    "xhs-system": ["/dbs-save", "/dbs-restore", "/dbs-report", "/dbs-agent-migration"],
    "xhs-chatroom": ["/dbs-chatroom"],
    "xhs-chatroom-austrian": ["/dbs-chatroom-austrian"],
    "xhs-dbskill-upgrade": ["/dbskill-upgrade"],
}


def test_dbskill_aliases_are_documented_in_skill_files():
    for skill_name, aliases in EXPECTED_SKILL_ALIASES.items():
        path = ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        for alias in aliases:
            assert alias in text, f"{path} missing {alias}"


def test_router_covers_remaining_low_frequency_aliases():
    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")

    for alias in ["/dbs-chatroom-austrian", "/dbskill-upgrade", "/dbs-agent-migration"]:
        assert alias in prompt


def test_router_covers_all_dbskill_aliases():
    """所有 dbskill 斜杠命令都要在主 prompt 有入口,防止 skill 可用但路由漏触发。"""
    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")

    for aliases in EXPECTED_SKILL_ALIASES.values():
        for alias in aliases:
            assert alias in prompt


def test_router_uses_real_deepagents_units_not_virtual_master_agents():
    """主 prompt 必须路由到真实 skill/subagent,不能再指向未注册的 *-main 主智能体。"""
    from subagents_executor import EXECUTOR_SUBAGENT_NAMES

    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")

    stale_master_agents = [
        "system-main",
        "positioning-main",
        "action-main",
        "research-main",
        "decision-main",
        "planning-main",
        "copywriting-main",
        "audit-main",
        "Domain Master Agent",
        "业务主智能体",
    ]
    for name in stale_master_agents:
        assert name not in prompt

    for skill_name in EXPECTED_SKILL_ALIASES:
        assert skill_name in prompt

    for subagent_name in EXECUTOR_SUBAGENT_NAMES:
        assert subagent_name in prompt


def test_router_references_existing_skill_directories():
    """prompt 中点名的 xhs-* skill 必须有真实 SKILL.md,防止再次出现虚拟路由。"""
    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")

    expected_skill_names = sorted(EXPECTED_SKILL_ALIASES) + [
        "xhs-positioning",
        "xhs-planning",
        "xhs-copywriting",
    ]
    for skill_name in expected_skill_names:
        skill_path = ROOT / ".agents" / "skills" / skill_name / "SKILL.md"
        assert skill_path.exists(), f"prompt references {skill_name}, but {skill_path} is missing"
        assert skill_name in prompt
