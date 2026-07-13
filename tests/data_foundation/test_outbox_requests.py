from __future__ import annotations

from datetime import UTC, datetime

from data_foundation.models import Resource
from data_foundation.outbox_requests import (
    CHUNKER_VERSION,
    default_write_requests,
    embedding_request,
)
from data_foundation.repositories.resource import ResourceRepository


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

    assert [request.topic for request in requests] == ["knowledge_enrich"]
    assert [request.payload for request in requests] == [{}]


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


def test_lifecycle_outbox_dedupe_includes_transition_event_only_when_requested():
    class _Cursor:
        def __init__(self):
            self.calls = []

        def execute(self, sql, params):
            self.calls.append((sql, params))

    repo = ResourceRepository()
    cursor = _Cursor()
    common = dict(
        tenant_id="tenant-a",
        resource_id="11111111-1111-1111-1111-111111111111",
        version=1,
        requests=default_write_requests(),
        cursor=cursor,
    )
    repo._enqueue_outbox(**common, event_id="event-v1-first", dedupe_event=True)
    first_transition = [call[1][5] for call in cursor.calls]
    cursor.calls.clear()
    repo._enqueue_outbox(**common, event_id="event-v1-again", dedupe_event=True)
    second_transition = [call[1][5] for call in cursor.calls]
    assert first_transition != second_transition

    cursor.calls.clear()
    repo._enqueue_outbox(**common, event_id="ordinary-event-a")
    ordinary_first = [call[1][5] for call in cursor.calls]
    cursor.calls.clear()
    repo._enqueue_outbox(**common, event_id="ordinary-event-b")
    ordinary_second = [call[1][5] for call in cursor.calls]
    assert ordinary_first == ordinary_second
