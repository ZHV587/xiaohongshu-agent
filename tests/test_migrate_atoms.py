import scripts.migrate_atoms as migrate_atoms


def test_atom_to_feishu_row_matches_batch_create_fields():
    atom = {
        "id": "atom_1",
        "knowledge": "一个知识点",
        "original": "原文",
        "url": "https://example.com",
        "date": "2026-06-23",
        "topics": ["选题"],
        "skills": ["dbs-content", "dbs-diagnosis", "dbs-content"],
        "type": "method",
        "confidence": "high",
    }

    row = migrate_atoms._atom_to_feishu_row(atom)

    assert migrate_atoms.FEISHU_ATOM_FIELDS == [
        "知识内容",
        "原子ID",
        "内容类型",
        "可信度",
        "发布日期",
        "原文摘要",
        "来源链接",
        "主题标签",
        "关联Skill",
    ]
    assert row == [
        "一个知识点",
        "atom_1",
        "method",
        "high",
        "2026-06-23",
        "原文",
        "https://example.com",
        "选题",
        "xhs-content，xhs-diagnosis",
    ]


def test_map_atom_skills_uses_local_xhs_skill_names():
    assert migrate_atoms._map_atom_skills([
        "dbs-content",
        "dbs-diagnosis",
        "dbs-deconstruct",
        "dbs-unblock",
        "dbs-benchmark",
    ]) == [
        "xhs-content",
        "xhs-diagnosis",
        "xhs-deconstruct",
        "xhs-action",
        "benchmark-analyst",
    ]


def test_write_batch_payload_returns_relative_at_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    payload_arg = migrate_atoms._write_batch_payload({"fields": ["知识内容"], "rows": [["测试"]]}, 1)

    assert payload_arg == "@large_tool_results/dbskill_atoms_import/batch_0001.json"
    assert (tmp_path / "large_tool_results/dbskill_atoms_import/batch_0001.json").exists()
