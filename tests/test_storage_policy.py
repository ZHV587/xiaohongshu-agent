from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUSINESS_SKILLS = (
    "topic-content",
    "xhs-chatroom",
    "xhs-content-system",
    "xhs-decision",
    "xhs-learning",
    "xhs-system",
)
FORBIDDEN_STORAGE_MARKERS = (
    "/analysis/",
    "/drafts/",
    "/shared/",
    "/root/.dbs",
    "~/.dbs",
    "write_file",
    "edit_file",
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_agent_does_not_grant_business_file_write_permissions() -> None:
    source = _read("agent.py")

    for path in ("/drafts/**", "/analysis/**", "/shared/**", "/root/.dbs/**"):
        assert path not in source

    assert 'paths=["/memories/**"]' in source
    assert 'paths=["/user-memories/**"]' in source


def test_runtime_has_no_business_file_routes_or_ui_labels() -> None:
    backend = _read("backends.py")
    assert '"/shared/"' not in backend
    assert '"/drafts/"' not in backend

    for relative_path in (
        "web/src/lib/tool-display.ts",
        "web/src/components/thread/messages/ai.tsx",
    ):
        source = _read(relative_path)
        for marker in ("/analysis/", "/drafts/", "/shared/"):
            assert marker not in source, f"{relative_path} still contains {marker}"


def test_main_prompt_defines_authoritative_storage_policy() -> None:
    prompt = _read("prompts.py")

    for rule in ("数据库唯一权威源", "仅数据库", "仅飞书", "数据库 + 飞书"):
        assert rule in prompt
    assert "不得使用 `write_file` 或 `edit_file` 持久化业务数据" in prompt


def test_business_skills_do_not_persist_to_local_files() -> None:
    for skill_name in BUSINESS_SKILLS:
        skill = _read(f".agents/skills/{skill_name}/SKILL.md")
        for marker in FORBIDDEN_STORAGE_MARKERS:
            assert marker not in skill, f"{skill_name} still contains {marker}"


def test_shareable_business_assets_use_database_and_feishu() -> None:
    generic_snapshot_skills = (
        "xhs-chatroom",
        "xhs-content-system",
        "xhs-decision",
        "xhs-learning",
        "xhs-system",
    )
    for skill_name in generic_snapshot_skills:
        skill = _read(f".agents/skills/{skill_name}/SKILL.md")
        assert "save_session_snapshot" in skill
        assert "sync_diagnosis_to_feishu" in skill

    topic_content = _read(".agents/skills/topic-content/SKILL.md")
    assert "save_generated_topic" in topic_content
    assert "sync_topic_to_feishu" in topic_content
    assert "save_generated_copy" in topic_content
    assert "sync_copy_to_feishu" in topic_content
