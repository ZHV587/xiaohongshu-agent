import pytest

from data_foundation.user_skill_service import SkillDefinitionError, UserSkillCompiler


def _payload(**overrides):
    value = {
        "displayName": "表达更直接",
        "description": "用户要求删掉铺垫并直接表达观点时使用",
        "instructions": "保留事实，第一句直接给结论。\r\n不要虚构案例。",
        "triggerExamples": ["写得直接一点", "写得直接一点"],
        "nonTriggerExamples": ["只检查错别字"],
        "tags": ["表达", "结构"],
    }
    value.update(overrides)
    return value


def test_compiler_emits_only_name_and_description_frontmatter():
    definition = UserSkillCompiler.validate(_payload())
    rendered = UserSkillCompiler.compile("usr-owner-123", definition)
    frontmatter = rendered.split("---", 2)[1]

    assert [line.split(":", 1)[0] for line in frontmatter.strip().splitlines()] == [
        "name",
        "description",
    ]
    assert "tools:" not in rendered
    assert "permissions:" not in rendered
    assert definition.trigger_examples == ("写得直接一点",)
    assert "\r" not in definition.instructions


@pytest.mark.parametrize(
    "field",
    [
        "tools",
        "permissions",
        "scripts",
        "path",
        "allowedTools",
        "filesystemPath",
        "tool_permissions",
        "allowed-commands",
    ],
)
def test_compiler_rejects_capability_escalation_fields(field):
    with pytest.raises(SkillDefinitionError) as error:
        UserSkillCompiler.validate(_payload(**{field: ["shell"]}))
    assert error.value.code == "SKILL_FIELD_NOT_ALLOWED"


def test_compiler_rejects_unknown_fields_and_illegal_controls():
    with pytest.raises(SkillDefinitionError) as unknown:
        UserSkillCompiler.validate(_payload(color="red"))
    assert unknown.value.code == "SKILL_UNKNOWN_FIELD"

    with pytest.raises(SkillDefinitionError) as control:
        UserSkillCompiler.validate(_payload(instructions="正常\x00恶意"))
    assert control.value.code == "SKILL_INVALID_INPUT"


def test_compiler_normalizes_unicode_and_respects_deepagents_description_limit():
    definition = UserSkillCompiler.validate(_payload(displayName="A\u0301"))
    assert "\u0301" not in definition.display_name

    with pytest.raises(SkillDefinitionError, match="Compiled description exceeds"):
        UserSkillCompiler.validate(
            _payload(
                description="a" * 500,
                triggerExamples=[("b" * 199) + str(index) for index in range(4)],
            )
        )
