from __future__ import annotations

from data_foundation.models import OutboxRequest, Resource


CHUNKER_VERSION = "text-v1"


def default_write_requests() -> list[OutboxRequest]:
    return [
        OutboxRequest(topic="meili_index", dedupe_parts=("search",), payload={}),
        OutboxRequest(topic="graph_ingest", dedupe_parts=("graph",), payload={}),
    ]


def search_index_request(resource: Resource) -> OutboxRequest:
    return OutboxRequest(
        topic="meili_index",
        dedupe_parts=("search", resource.id, str(resource.version or 0)),
        payload={"resource_id": resource.id, "version": resource.version},
    )


def graph_ingest_request(resource: Resource) -> OutboxRequest:
    return OutboxRequest(
        topic="graph_ingest",
        dedupe_parts=("graph", resource.id, str(resource.version or 0)),
        payload={"resource_id": resource.id, "version": resource.version},
    )


def embedding_request(resource: Resource, *, embedding_index_id: str) -> OutboxRequest:
    return OutboxRequest(
        topic="embedding_generate",
        dedupe_parts=("embedding", resource.id, str(resource.version or 0), embedding_index_id, CHUNKER_VERSION),
        payload={
            "resource_id": resource.id,
            "version": resource.version,
            "embedding_index_id": embedding_index_id,
            "chunker_version": CHUNKER_VERSION,
        },
    )
