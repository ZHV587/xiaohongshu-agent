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


def test_search_returns_ordered_ids_with_tenant_filter():
    client = MagicMock()
    index = client.index.return_value
    index.search.return_value = {"hits": [{"resource_id": "a"}, {"resource_id": "b"}]}
    idx = _index_with(client)
    ids = idx.search("减脂", tenant_id="default", limit=10)
    assert ids == ["a", "b"]
    args, kwargs = index.search.call_args
    assert args[0] == "减脂"
    assert kwargs["opt_params"]["filter"] == 'tenant_id = "default"'
    assert kwargs["opt_params"]["limit"] == 10
