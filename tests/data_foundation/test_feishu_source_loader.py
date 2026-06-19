from data_foundation.feishu_source_loader import load_feishu_sources


def test_loader_forwards_config_and_collects_valid_sources_and_errors(monkeypatch):
    config = {"configurable": {"user_id": "ou_test"}}
    calls = []

    def read_base(*, config):
        calls.append(("base", config))
        return {
            "app_token": "app-token",
            "table_id": "tbl-id",
            "sync_rows": [
                {
                    "record_id": "rec1",
                    "identity_kind": "feishu_record_id",
                    "fields": {"标题": "一"},
                    "external_updated_at": "1714550400000",
                },
                {"record_id": "", "fields": {"标题": "坏数据"}},
            ],
            "source_errors": ["base page 2 failed"],
        }

    def read_wiki(*, config):
        calls.append(("wiki", config))
        return {
            "wiki_space_id": "space-id",
            "documents": [
                {
                    "obj_token": "doc1",
                    "node_token": "wik1",
                    "title": "文档",
                    "content": "正文",
                    "external_updated_at": 1711958400,
                },
                {"obj_token": "doc2", "title": "缺少节点", "content": "正文"},
            ],
            "source_errors": ["wiki document doc3 failed"],
        }

    monkeypatch.setattr("data_foundation.feishu_source_loader.read_xhs_data.func", read_base)
    monkeypatch.setattr("data_foundation.feishu_source_loader.read_feishu_wiki.func", read_wiki)

    result = load_feishu_sources(config)

    assert calls == [("base", config), ("wiki", config)]
    assert result["base_rows"] == [
        {
            "record_id": "rec1",
            "identity_kind": "feishu_record_id",
            "fields": {"标题": "一"},
            "external_updated_at": "2024-05-01T08:00:00+00:00",
        },
    ]
    assert result["wiki_documents"] == [
        {
            "obj_token": "doc1",
            "node_token": "wik1",
            "title": "文档",
            "content": "正文",
            "external_updated_at": "2024-04-01T08:00:00+00:00",
        },
    ]
    assert result["app_token"] == "app-token"
    assert result["table_id"] == "tbl-id"
    assert result["wiki_space_id"] == "space-id"
    assert result["source_errors"] == [
        "base page 2 failed",
        "base row missing record_id or fields",
        "wiki document doc3 failed",
        "wiki document missing obj_token or node_token",
    ]


def test_loader_turns_top_level_read_failures_into_source_errors(monkeypatch):
    monkeypatch.setattr(
        "data_foundation.feishu_source_loader.read_xhs_data.func",
        lambda *, config: {"error": "Base is not configured", "rows": []},
    )
    monkeypatch.setattr(
        "data_foundation.feishu_source_loader.read_feishu_wiki.func",
        lambda *, config: {"error": "Wiki denied", "documents": []},
    )

    result = load_feishu_sources(None)

    assert result == {
        "base_rows": [],
        "wiki_documents": [],
        "source_errors": ["base: Base is not configured", "wiki: Wiki denied"],
        "app_token": "",
        "table_id": "",
        "wiki_space_id": "",
    }


def test_loader_discards_invalid_external_updated_at(monkeypatch):
    monkeypatch.setattr(
        "data_foundation.feishu_source_loader.read_xhs_data.func",
        lambda *, config: {
            "app_token": "app-token",
            "table_id": "tbl-id",
            "sync_rows": [
                {
                    "record_id": "rec1",
                    "fields": {"标题": "一"},
                    "external_updated_at": "not-a-time",
                }
            ],
        },
    )
    monkeypatch.setattr(
        "data_foundation.feishu_source_loader.read_feishu_wiki.func",
        lambda *, config: {"wiki_space_id": "space-id", "documents": []},
    )

    result = load_feishu_sources(None)

    assert "external_updated_at" not in result["base_rows"][0]
    assert result["source_errors"] == [
        "base row rec1 has invalid external_updated_at"
    ]
