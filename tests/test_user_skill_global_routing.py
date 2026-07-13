from prompts import MAIN_SYSTEM_PROMPT


def test_user_skills_are_declared_global_across_agent_workflows():
    stages = (
        "诊断",
        "定位",
        "目标",
        "概念",
        "选题",
        "爆款拆解",
        "学习",
        "决策",
        "标题",
        "开头",
        "润色",
        "整篇创作",
        "仿写",
        "运营复盘",
    )
    user_skill_rule = next(
        line for line in MAIN_SYSTEM_PROMPT.splitlines() if "/user-skills/" in line
    )
    assert all(stage in user_skill_rule for stage in stages)
    assert "不增加工具或权限" in user_skill_rule


def test_subagent_brief_must_carry_active_user_skill_constraints():
    assert "子 agent 不会自行加载用户 Skill" in MAIN_SYSTEM_PROMPT
    assert "不得因此获得额外工具" in MAIN_SYSTEM_PROMPT
