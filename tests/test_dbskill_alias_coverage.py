"""Skill 语义触发覆盖测试（2026-06-23 废除斜杠命令后)。

产品决策：本系统不使用斜杠命令,全部走语义触发。触发词的唯一事实源是各
SKILL.md 的 `description` frontmatter —— DeepAgents SkillsMiddleware 自动把
name+description 注入系统提示,主 prompt 不再手抄路由表(那是已废除的双份维护)。

故本测试守护新契约：
1. 每个 Skill 的 description 里有足量中文语义触发短语;
2. 任何 SKILL.md 的 frontmatter 与正文里都不再残留斜杠命令;
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
    "xhs-title",
    "xhs-hook",
    "xhs-copywriting",
    "xhs-audit",
    "xhs-decision",
    "xhs-learning",
]

# 飞书工具 skill 的 description 含 /base/ 链接路径、应用内/短信 等顿号词组,
# 不是斜杠命令,扫描时豁免。
_NON_COMMAND_SLASH_SKILLS = {"lark-base", "lark-im", "lark-shared"}


def _frontmatter(name: str) -> str:
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    parts = text.split("---")
    # parts[0] 为空,parts[1] 是 frontmatter
    return parts[1] if len(parts) >= 3 else text


def _body(name: str) -> str:
    """SKILL.md 去掉 frontmatter 后的正文(含工作流、下一步建议表、存档提示等)。"""
    text = (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")
    parts = text.split("---")
    # 标准结构 parts[0]="" parts[1]=frontmatter parts[2:]=正文(正文里的 --- 分隔线也会被切开,需拼回)
    return "---".join(parts[2:]) if len(parts) >= 3 else text


# 斜杠命令:以 / 起头且前面不是字母数字(排除 GitHub 仓库路径如
# `dontbesilent2025/dbskill`、markdown 链接路径如 `references/lark-base-x.md`、
# `/base/` 这类非命令斜杠)。xhs/dbs/dbskill 是本系统曾用命令前缀。
_SLASH_COMMAND_RE = re.compile(r"(?<![A-Za-z0-9])/(?:xhs|dbs|dbskill)[\w-]*")


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
        leaked = _SLASH_COMMAND_RE.findall(fm)
        assert not leaked, f"{name} frontmatter 残留斜杠命令: {leaked}"


def test_no_slash_commands_left_in_any_skill_body():
    """正文同样不得残留斜杠命令。

    历史缺口:旧测试只查 frontmatter,正文里的「用 `/xhs-xxx`」下一步建议、
    「输入 `/xhs-save` 存档」提示等积累了大量斜杠命令而长期漏检 —— 它们会被主控
    原样输出给用户,指向已不存在的命令。本测试把守护范围扩到正文,堵住漂移。

    合法保留(被正则前缀规则天然排除,不会误报):markdown 链接里的 `references/xxx.md`
    路径、上游仓库引用 `dontbesilent2025/dbskill`。
    """
    for name in _all_skill_dirs():
        body = _body(name)
        leaked = _SLASH_COMMAND_RE.findall(body)
        assert not leaked, f"{name} 正文残留斜杠命令: {leaked}"


def test_prompt_has_no_slash_commands_and_no_routing_table():
    """主 prompt 不得再含斜杠命令,也不得再有'强匹配路由表'手抄段。"""
    prompt = (ROOT / "prompts.py").read_text(encoding="utf-8")
    assert "强匹配" not in prompt
    leaked = _SLASH_COMMAND_RE.findall(prompt)
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


def test_skill_body_cross_refs_point_to_real_skills():
    """技能正文(尤其"下一步建议"表)里反引号包裹的 xhs-*/topic-content/anti-ai-copy-taste
    技能名,必须都有真实 SKILL.md 目录 —— 防技能改名后正文留死引用(主控会原样转述给用户,
    指向已不存在的技能)。补齐 test_prompt_referenced_skills_have_real_directories 只守 prompt
    的缺口,把守护扩到所有 SKILL.md 正文。"""
    real = set(_all_skill_dirs())
    ref_re = re.compile(r"`(xhs-[a-z0-9-]+|topic-content|anti-ai-copy-taste)`")
    for name in _all_skill_dirs():
        body = _body(name)
        for ref in sorted(set(ref_re.findall(body))):
            assert ref in real, f"{name} 正文引用了不存在的技能 `{ref}`"
