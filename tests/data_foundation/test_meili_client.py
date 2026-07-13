from unittest.mock import MagicMock
from data_foundation.meili_client import MeiliResourceIndex, MeiliTenantAudit


def _index_with(mock_client):
    return MeiliResourceIndex(client=mock_client, index_uid="resources")


def test_ensure_index_sets_filterable_and_searchable():
    client = MagicMock()
    index = client.index.return_value
    index.update_filterable_attributes.return_value = MagicMock(task_uid=11)
    index.update_searchable_attributes.return_value = MagicMock(task_uid=12)
    index.wait_for_task.side_effect = [
        MagicMock(status="succeeded"),
        MagicMock(status="succeeded"),
    ]
    idx = _index_with(client)
    idx.ensure_index()
    client.index.assert_called_with("resources")
    index.update_filterable_attributes.assert_called_once_with(
        ["tenant_id", "type", "resource_version"]
    )
    index.update_searchable_attributes.assert_called_once_with(["title", "summary", "content_text"])
    assert index.wait_for_task.call_count == 2


def test_audit_tenant_detects_legacy_documents_when_raw_count_matches():
    client = MagicMock()
    index = client.index.return_value
    # PG expects 3 and Meili also has 3 documents, but only one can be hydrated by
    # exact immutable version.  Cardinality-only drift detection would miss this.
    index.search.side_effect = [
        {"estimatedTotalHits": 3},
        {"estimatedTotalHits": 1},
    ]

    audit = _index_with(client).audit_tenant(tenant_id="default")

    assert audit == MeiliTenantAudit(total_documents=3, versioned_documents=1)
    assert audit.malformed_documents == 2
    assert index.search.call_args_list[1].kwargs["opt_params"]["filter"] == (
        'tenant_id = "default" AND resource_version >= 1'
    )


def test_upsert_document_uses_resource_id_as_primary_key():
    client = MagicMock()
    idx = _index_with(client)
    index = client.index.return_value
    index.add_documents.return_value = MagicMock(task_uid=7)
    index.wait_for_task.return_value = MagicMock(status="succeeded")
    idx.upsert({"resource_id": "r1", "tenant_id": "default", "type": "feishu_base_record",
                "title": "t", "summary": None, "content_text": "body"})
    args, kwargs = index.add_documents.call_args
    assert args[0] == [{"resource_id": "r1", "tenant_id": "default", "type": "feishu_base_record",
                        "title": "t", "summary": None, "content_text": "body"}]
    assert kwargs.get("primary_key") == "resource_id"
    # C-1:必须等待 Meili 任务终态(否则 outbox 在文档实际入库前就被标 succeeded)
    index.wait_for_task.assert_called_once_with(7, timeout_in_ms=30000)


def test_upsert_raises_when_meili_task_not_succeeded():
    """C-1 回归:Meili 端任务失败时 upsert 必须抛出,让 outbox 重试,而非假性 succeeded。"""
    import pytest
    client = MagicMock()
    idx = _index_with(client)
    index = client.index.return_value
    index.add_documents.return_value = MagicMock(task_uid=9)
    index.wait_for_task.return_value = MagicMock(status="failed", error={"code": "x"})
    with pytest.raises(RuntimeError):
        idx.upsert({"resource_id": "r1", "tenant_id": "default", "type": "t",
                    "title": "t", "summary": None, "content_text": "b"})


def test_search_returns_id_score_version_tuples_with_tenant_filter():
    client = MagicMock()
    index = client.index.return_value
    index.search.return_value = {
        "hits": [
            {"resource_id": "a", "_rankingScore": 0.9, "resource_version": 2},
            {"resource_id": "b", "_rankingScore": 0.4, "resource_version": 7},
        ]
    }
    idx = _index_with(client)
    hits = idx.search("减脂", tenant_id="default", limit=10)
    assert hits == [("a", 0.9, 2), ("b", 0.4, 7)]
    args, kwargs = index.search.call_args
    assert args[0] == "减脂"
    assert kwargs["opt_params"]["filter"] == 'tenant_id = "default"'
    assert kwargs["opt_params"]["limit"] == 10
    assert kwargs["opt_params"]["showRankingScore"] is True


def test_search_defaults_missing_ranking_score_to_zero_and_requires_version():
    client = MagicMock()
    index = client.index.return_value
    index.search.return_value = {
        "hits": [
            {"resource_id": "a", "resource_version": 3},
            {"resource_id": "legacy-without-version"},
        ]
    }
    idx = _index_with(client)
    assert idx.search("q", tenant_id="default", limit=5) == [("a", 0.0, 3)]


def test_from_config_reuses_underlying_client_for_same_config(monkeypatch):
    import data_foundation.meili_client as mc
    mc._reset_client_cache()
    created = []

    class _FakeClient:
        def __init__(self, url, key, timeout=None):
            created.append((url, key))

    monkeypatch.setattr(mc.meilisearch, "Client", _FakeClient)
    from data_foundation.engine_config import MeiliConfig
    cfg = MeiliConfig(state="enabled", url="http://x:7700", api_key="k")
    a = mc.MeiliResourceIndex.from_config(cfg)
    b = mc.MeiliResourceIndex.from_config(cfg)
    # 同 config:底层 client 只建一次,复用
    assert len(created) == 1
    assert a.client is b.client
    # 不同 config:新建
    mc.MeiliResourceIndex.from_config(MeiliConfig(state="enabled", url="http://y:7700", api_key="k2"))
    assert len(created) == 2
