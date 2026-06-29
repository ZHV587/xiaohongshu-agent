from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

USER_VISIBLE_MARKERS = (
    "直接告诉用户",
    "直接提示",
    "| 资源数为0",
    "| 对标拆解完毕",
    "输出以下引导词",
    "| 对标找到了",
    "| 诊断出开头问题",
    "| 诊断出标题问题",
    "| 诊断出明显 AI 味",
    "| 用户在方法上走捷径",
    "| 内容涉及对标和平台选择",
    "| 选题装配完成",
    "| 底座内容很少",
    "| 主题地图完成",
    "| 文案写完需要质检",
    "| 执行力诊断后",
    "| 问题说明书完成",
)

FORBIDDEN_USER_VISIBLE_TOKENS = (
    "`xhs-",
    "`sync_",
    "调用 `",
    "转入 `xhs-",
    "使用专门的 `xhs-",
    "技能来",
    "system prompt",
    "主控 §",
    "主控 system prompt",
)

TARGET_SKILLS = (
    "topic-content",
    "xhs-copywriting",
    "xhs-content-system",
    "xhs-benchmark",
    "xhs-content",
    "xhs-action",
)


def _skill_text(name: str) -> str:
    return (ROOT / ".agents" / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def _user_visible_lines(text: str) -> list[tuple[int, str]]:
    lines = text.splitlines()
    result: list[tuple[int, str]] = []
    in_guidance_block = False
    for idx, line in enumerate(lines, start=1):
        if "输出以下引导词" in line:
            in_guidance_block = True
            result.append((idx, line))
            continue
        if in_guidance_block:
            result.append((idx, line))
            if line.strip().endswith("```") and idx > 1:
                in_guidance_block = False
            continue
        if any(marker in line for marker in USER_VISIBLE_MARKERS):
            result.append((idx, line))
    return result


def test_user_visible_skill_lines_do_not_expose_internal_names():
    failures: list[str] = []
    for skill in TARGET_SKILLS:
        for line_no, line in _user_visible_lines(_skill_text(skill)):
            for token in FORBIDDEN_USER_VISIBLE_TOKENS:
                if token in line:
                    failures.append(f"{skill}:{line_no}: contains {token!r}: {line}")
    assert failures == []
