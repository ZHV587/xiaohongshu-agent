from __future__ import annotations

from data_foundation.models import OutboxRequest, Resource


CHUNKER_VERSION = "text-v1"


def default_write_requests() -> list[OutboxRequest]:
    return [
        OutboxRequest(topic="knowledge_enrich", dedupe_parts=("knowledge",), payload={}),
    ]


def candidate_graph_requests() -> list[OutboxRequest]:
    """候选稿只同步图结构，不进入 Meili/向量知识检索。

    图同步用于保证所有素材都有可追溯关联；待用户明确采纳或排期定稿后，再针对那个
    精确 resource_version 投递完整索引任务，避免流式片段和普通候选污染高质量知识。
    """
    return [OutboxRequest(topic="graph_ingest", dedupe_parts=("candidate-graph",), payload={})]


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
