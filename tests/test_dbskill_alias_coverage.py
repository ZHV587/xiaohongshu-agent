"""Skill 语义触发覆盖测试（2026-06-23 废除斜杠命令后)。

产品决策：本系统不使用斜杠命令,全部走语义触发。触发词的唯一事实源是各
SKILL.md 的 `description` frontmatter —— DeepAgents SkillsMiddleware 自动把
name+description 注入系统提示,主 prompt 不再手抄路由表(那是已废除的双份维护)。

故本测试守护新契约：
1. 每个 Skill 的 description 里有足量中文语义触发短语;
2. 任何 SKILL.md 的 frontmatter 里不再残留斜杠命令;
3. 主 prompt 不再含斜杠命令、不再含手抄路由表,且仍点名真实 skill/subagent。
"""
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / ".agents" / "skills"

# 走语义路由消歧、需要主 prompt 点名的 xhs-* skill。
ROUTED_SKILLS = [
    "xhs-diagnosis",
    "xhs-positioning",
    "xhs-goal",
    "xhs-deconstruct",
    "xhs-good-question",
    "xhs-action",
    "xhs-slowisfast",
    "xhs-benchmark",
    "xhs-content-system",
    "xhs-planning",
    "xhs-title",
    "xhs-hook",
    "xhs-copywriting",
    "xhs-audit",
    "xhs-decision",
    "xhs-learning",
    "xhs-chatroom",
    "xhs-chatroom-austrian",
    "xhs-system",
    "xhs-dbskill-upgrade",
]

# 飞书工具 skill 的 description 含 /base/ 链接路径、应用内/短信 等顿号词组,
# 不是斜杠命令,扫描时豁免。
_NON_COMMAND_SLASH_SKILLS = {"lark-base", "lark-im", "lark-shared"}


def _frontmatter(name: str) -> str:
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    parts = text.split("---")
    # parts[0] 为空,parts[1] 是 frontmatter
    return parts[1] if len(parts) >= 3 else text


def _all_skill_dirs() -> list[str]:
    return sorted(p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())


def test_routed_skills_have_semantic_triggers_in_description():
    """每个被路由的 skill,description 里必须有中文语义触发短语「...」。"""
    for name in ROUTED_SKILLS:
        fm = _frontmatter(name)
        phrases = re.findall(r"「[^」]+」", fm)
        assert len(phrases) >= 2, f"{name} description 语义触发短语不足: {phrases}"


def test_no_slash_commands_left_in_any_skill_frontmatter():
    """废除斜杠命令后,任何 SKILL.md frontmatter 不得再出现 /xhs- /dbs- 等命令。

    斜杠命令以 / 起头且前面不是字母数字(排除 GitHub 仓库路径如
    `dontbesilent2025/dbskill`、链接路径 `/base/` 这类非命令斜杠)。
    """
    for name in _all_skill_dirs():
        fm = _frontmatter(name)
        leaked = re.findall(r"(?<![A-Za-z0-9])/(?:xhs|dbs|dbskill)[\w-]*", fm)
        assert not leaked, f"{name} frontmatter 残留斜杠命令: {leaked}"


def test_prompt_has_no_slash_commands_and_no_routing_table():
    """主 prompt 不得再含斜杠命令,也不得再有'强匹配路由表'手抄段。"""
    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")
    assert "强匹配" not in prompt
    leaked = re.findall(r"/(?:xhs|dbs|dbskill)[\w-]*", prompt)
    assert not leaked, f"prompt 残留斜杠命令: {leaked}"


def test_prompt_routes_to_real_units_not_virtual_master_agents():
    """主 prompt 必须路由到真实 skill/subagent,不能指向未注册的 *-main 主智能体。"""
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
    for stale in stale_master_agents:
        assert stale not in prompt
    for subagent_name in EXECUTOR_SUBAGENT_NAMES:
        assert subagent_name in prompt


def test_prompt_referenced_skills_have_real_directories():
    """prompt 中点名的 xhs-* skill 必须有真实 SKILL.md,防止虚拟路由。"""
    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")
    for name in ROUTED_SKILLS:
        skill_path = SKILLS_DIR / name / "SKILL.md"
        assert skill_path.exists(), f"prompt references {name}, but {skill_path} missing"
        assert name in prompt
