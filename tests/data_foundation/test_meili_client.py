from datetime import datetime
from unittest.mock import MagicMock

import pytest

from data_foundation.meili_client import (
    MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION,
    MeiliResourceIndex,
    MeiliSearchHit,
    MeiliTenantAudit,
)


def _index_with(mock_client):
    return MeiliResourceIndex(client=mock_client, index_uid="resources")


def _v2_hit(**overrides):
    hit = {
        "resource_id": "a",
        "resource_version": 2,
        "_rankingScore": 0.9,
        "type": "generated_copy",
        "asset_kind": "adopted_copy",
        "source_kind": "user_adopted",
        "niche": "健身",
        "quality_score": 0.87,
        "qualified_at_epoch": 1782864000,
        "tags": ["减脂"],
        "hook_types": ["数字清单"],
        "cta_types": ["收藏"],
        "structure_tags": ["清单体"],
        "style_tags": ["第一人称"],
        "success_factors": ["实测"],
        "index_schema_version": MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION,
    }
    hit.update(overrides)
    return hit


def test_ensure_index_sets_hybrid_filterable_and_searchable_attributes():
    client = MagicMock()
    index = client.index.return_value
    index.update_filterable_attributes.return_value = MagicMock(task_uid=11)
    index.update_searchable_attributes.return_value = MagicMock(task_uid=12)
    index.wait_for_task.side_effect = [
        MagicMock(status="succeeded"),
        MagicMock(status="succeeded"),
    ]

    _index_with(client).ensure_index()

    index.update_filterable_attributes.assert_called_once_with(
        MeiliResourceIndex.FILTERABLE
    )
    assert {
        "asset_kind",
        "source_kind",
        "niche",
        "quality_score",
        "qualified_at_epoch",
        "index_schema_version",
    } <= set(MeiliResourceIndex.FILTERABLE)
    index.update_searchable_attributes.assert_called_once_with(
        MeiliResourceIndex.SEARCHABLE
    )
    assert {
        "normalized_text",
        "tags",
        "hook_types",
        "cta_types",
        "structure_tags",
        "style_tags",
        "success_factors",
    } <= set(MeiliResourceIndex.SEARCHABLE)
    assert index.wait_for_task.call_count == 2


def test_audit_tenant_counts_only_current_hybrid_schema_documents():
    client = MagicMock()
    index = client.index.return_value
    index.search.side_effect = [
        {"estimatedTotalHits": 3},
        {"estimatedTotalHits": 1},
    ]

    audit = _index_with(client).audit_tenant(tenant_id="default")

    assert audit == MeiliTenantAudit(total_documents=3, current_schema_documents=1)
    assert audit.stale_schema_documents == 2
    current_filter = index.search.call_args_list[1].kwargs["opt_params"]["filter"]
    assert 'index_schema_version = "knowledge-hybrid-v2"' in current_filter
    assert "resource_version >= 1" in current_filter


def test_upsert_document_uses_resource_id_as_primary_key_and_waits():
    client = MagicMock()
    idx = _index_with(client)
    index = client.index.return_value
    index.add_documents.return_value = MagicMock(task_uid=7)
    index.wait_for_task.return_value = MagicMock(status="succeeded")
    document = {"resource_id": "r1", "index_schema_version": "knowledge-hybrid-v2"}

    idx.upsert(document)

    index.add_documents.assert_called_once_with([document], primary_key="resource_id")
    index.wait_for_task.assert_called_once_with(7, timeout_in_ms=30000)


def test_upsert_raises_when_meili_task_not_succeeded():
    client = MagicMock()
    idx = _index_with(client)
    index = client.index.return_value
    index.add_documents.return_value = MagicMock(task_uid=9)
    index.wait_for_task.return_value = MagicMock(status="failed", error={"code": "x"})

    with pytest.raises(RuntimeError):
        idx.upsert({"resource_id": "r1"})


def test_search_returns_typed_hybrid_hits_and_compiles_validated_filters():
    client = MagicMock()
    index = client.index.return_value
    index.search.return_value = {"hits": [_v2_hit()]}

    hits = _index_with(client).search(
        "减脂",
        tenant_id="default",
        limit=10,
        filters={
            "asset_kinds": ["adopted_copy"],
            "source_kinds": ["user_adopted"],
            "niches": ["健身", "饮食"],
            "min_quality": 0.75,
            "updated_after": "2026-07-01T00:00:00+08:00",
        },
    )

    assert hits == [
        MeiliSearchHit(
            resource_id="a",
            resource_version=2,
            score=0.9,
            resource_type="generated_copy",
            asset_kind="adopted_copy",
            source_kind="user_adopted",
            niche="健身",
            quality_score=0.87,
            qualified_at_epoch=1782864000,
            tags=("减脂",),
            hook_types=("数字清单",),
            cta_types=("收藏",),
            structure_tags=("清单体",),
            style_tags=("第一人称",),
            success_factors=("实测",),
        )
    ]
    options = index.search.call_args.kwargs["opt_params"]
    assert options["showRankingScore"] is True
    assert options["limit"] == 10
    filter_expression = options["filter"]
    assert 'tenant_id = "default"' in filter_expression
    assert 'index_schema_version = "knowledge-hybrid-v2"' in filter_expression
    assert 'asset_kind IN ["adopted_copy"]' in filter_expression
    assert 'source_kind IN ["user_adopted"]' in filter_expression
    assert 'niche IN ["健身", "饮食"]' in filter_expression
    assert "quality_score >= 0.75" in filter_expression
    assert (
        f"qualified_at_epoch >= {int(datetime.fromisoformat('2026-07-01T00:00:00+08:00').timestamp())}"
        in filter_expression
    )


@pytest.mark.parametrize(
    "filters",
    [
        {"raw_filter": 'tenant_id = "other"'},
        {"asset_kinds": "adopted_copy"},
        {"niches": ["ok", 3]},
        {"min_quality": 1.1},
        {"updated_after": "2026-07-01"},
    ],
)
def test_search_rejects_unvalidated_or_injectable_filter_shapes(filters):
    client = MagicMock()
    with pytest.raises(ValueError):
        _index_with(client).search(
            "query", tenant_id="default", limit=5, filters=filters
        )
    client.index.assert_not_called()


def test_search_escapes_metadata_values_instead_of_accepting_filter_syntax():
    client = MagicMock()
    client.index.return_value.search.return_value = {"hits": []}
    hostile = '健身"] OR tenant_id = "other'

    _index_with(client).search(
        "query",
        tenant_id="default",
        limit=5,
        filters={"niches": [hostile]},
    )

    expression = client.index.return_value.search.call_args.kwargs["opt_params"]["filter"]
    assert f"niche IN [{json_literal(hostile)}]" in expression


def json_literal(value: str) -> str:
    # Test-side mirror only for an exact escaped literal assertion.
    import json

    return json.dumps(value, ensure_ascii=False)


def test_search_fails_closed_for_legacy_or_malformed_hits():
    client = MagicMock()
    client.index.return_value.search.return_value = {
        "hits": [
            _v2_hit(resource_id="ok"),
            _v2_hit(resource_id="legacy", index_schema_version="resource-version-v1"),
            _v2_hit(resource_id="no-version", resource_version=None),
            _v2_hit(resource_id="no-kind", asset_kind=None),
        ]
    }

    hits = _index_with(client).search("q", tenant_id="default", limit=5)

    assert [hit.resource_id for hit in hits] == ["ok"]


def test_from_config_reuses_underlying_client_for_same_config(monkeypatch):
    import data_foundation.meili_client as mc
    from data_foundation.engine_config import MeiliConfig

    mc._reset_client_cache()
    created = []

    class _FakeClient:
        def __init__(self, url, key, timeout=None):
            created.append((url, key))

    monkeypatch.setattr(mc.meilisearch, "Client", _FakeClient)
    cfg = MeiliConfig(state="enabled", url="http://x:7700", api_key="k")
    first = mc.MeiliResourceIndex.from_config(cfg)
    second = mc.MeiliResourceIndex.from_config(cfg)
    assert len(created) == 1
    assert first.client is second.client

    mc.MeiliResourceIndex.from_config(
        MeiliConfig(state="enabled", url="http://y:7700", api_key="k2")
    )
    assert len(created) == 2
