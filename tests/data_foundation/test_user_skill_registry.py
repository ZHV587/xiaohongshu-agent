from pathlib import Path

from data_foundation.models import UserSkillRegistryEntry
from data_foundation.user_skill_registry import build_skill_registry, load_system_skill_items


def _write_skill(root: Path, directory: str, frontmatter: str, body: str = "SECRET BODY") -> None:
    target = root / directory
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(
        f"---\n{frontmatter}\n---\n\n{body}\n",
        encoding="utf-8",
    )


def test_system_registry_reads_only_valid_frontmatter_and_skips_deprecated(tmp_path):
    _write_skill(tmp_path, "xhs-valid", "name: xhs-valid\ndescription: 有效流程")
    _write_skill(tmp_path, "xhs-deprecated", "name: xhs-deprecated\ndescription: 已废弃，不要使用")
    _write_skill(tmp_path, "xhs-mismatch", "name: xhs-other\ndescription: 名称不匹配")
    _write_skill(tmp_path, "xhs-invalid", "name: [broken\ndescription: 非法 YAML")

    assert load_system_skill_items(tmp_path) == [
        {
            "name": "xhs-valid",
            "displayName": "xhs-valid",
            "description": "有效流程",
            "source": "system",
            "readonly": True,
        }
    ]


def test_registry_user_projection_contains_no_body_fields(tmp_path):
    entry = UserSkillRegistryEntry(
        skill_id="skill-1",
        version_id="version-2",
        runtime_name="usr-owner-skill",
        display_name="我的流程",
        description="需要按我的流程处理时使用",
        tags=["通用"],
    )

    assert build_skill_registry([entry], skills_root=tmp_path) == [
        {
            "skillId": "skill-1",
            "versionId": "version-2",
            "runtimeName": "usr-owner-skill",
            "displayName": "我的流程",
            "description": "需要按我的流程处理时使用",
            "tags": ["通用"],
            "source": "user",
            "readonly": False,
        }
    ]
