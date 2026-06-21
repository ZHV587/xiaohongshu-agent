from __future__ import annotations

from datetime import UTC, datetime

from data_foundation.models import Resource
from data_foundation.outbox_requests import (
    CHUNKER_VERSION,
    default_write_requests,
    embedding_request,
)


def _resource() -> Resource:
    now = datetime(2026, 6, 20, tzinfo=UTC)
    return Resource(
        id="res-1",
        tenant_id="tenant-a",
        type="feishu_doc",
        title="title",
        summary=None,
        content_text="body",
        content_json={},
        status="active",
        visibility="team",
        owner_open_id="ou_owner",
        created_at=now,
        updated_at=now,
        version=3,
    )


def test_default_write_requests_are_resource_agnostic_declarations():
    requests = default_write_requests()

    assert [request.topic for request in requests] == ["meili_index", "graph_ingest"]
    assert [request.payload for request in requests] == [{}, {}]


def test_embedding_request_requires_explicit_index_profile():
    request = embedding_request(_resource(), embedding_index_id="idx-1")

    assert request.topic == "embedding_generate"
    assert request.dedupe_parts == ("embedding", "res-1", "3", "idx-1", CHUNKER_VERSION)
    assert request.payload == {
        "resource_id": "res-1",
        "version": 3,
        "embedding_index_id": "idx-1",
        "chunker_version": CHUNKER_VERSION,
    }
