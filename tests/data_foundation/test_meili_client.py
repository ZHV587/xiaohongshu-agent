from unittest.mock import MagicMock
from data_foundation.meili_client import MeiliResourceIndex


def _index_with(mock_client):
    return MeiliResourceIndex(client=mock_client, index_uid="resources")


def test_ensure_index_sets_filterable_and_searchable():
    client = MagicMock()
    idx = _index_with(client)
    idx.ensure_index()
    client.index.assert_called_with("resources")
    index = client.index.return_value
    index.update_filterable_attributes.assert_called_once_with(["tenant_id", "type"])
    index.update_searchable_attributes.assert_called_once_with(["title", "summary", "content_text"])


def test_upsert_document_uses_resource_id_as_primary_key():
    client = MagicMock()
    idx = _index_with(client)
    idx.upsert({"resource_id": "r1", "tenant_id": "default", "type": "feishu_base_record",
                "title": "t", "summary": None, "content_text": "body"})
    index = client.index.return_value
    args, kwargs = index.add_documents.call_args
    assert args[0] == [{"resource_id": "r1", "tenant_id": "default", "type": "feishu_base_record",
                        "title": "t", "summary": None, "content_text": "body"}]
    assert kwargs.get("primary_key") == "resource_id"


def test_search_returns_id_score_pairs_with_tenant_filter():
    client = MagicMock()
    index = client.index.return_value
    index.search.return_value = {
        "hits": [
            {"resource_id": "a", "_rankingScore": 0.9},
            {"resource_id": "b", "_rankingScore": 0.4},
        ]
    }
    idx = _index_with(client)
    hits = idx.search("减脂", tenant_id="default", limit=10)
    assert hits == [("a", 0.9), ("b", 0.4)]
    args, kwargs = index.search.call_args
    assert args[0] == "减脂"
    assert kwargs["opt_params"]["filter"] == 'tenant_id = "default"'
    assert kwargs["opt_params"]["limit"] == 10
    assert kwargs["opt_params"]["showRankingScore"] is True


def test_search_defaults_missing_ranking_score_to_zero():
    client = MagicMock()
    index = client.index.return_value
    index.search.return_value = {"hits": [{"resource_id": "a"}]}
    idx = _index_with(client)
    assert idx.search("q", tenant_id="default", limit=5) == [("a", 0.0)]


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
