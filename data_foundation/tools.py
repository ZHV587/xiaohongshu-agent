from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from data_foundation.creation_memory import (
    save_generated_copy_resource,
    save_generated_topic_resource,
    save_user_feedback_resource,
)
from data_foundation.db import connect
from data_foundation.graph import expand_graph as expand_graph_query
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.performance_feedback import (
    get_resource_performance_payload,
    save_performance_metric_resource,
)
from data_foundation.repository import ResourceRepository
from data_foundation.search import keyword_search, semantic_search
from data_foundation.source_repository import SourceRepository
from data_foundation.sync_service import sync_feishu_sources


@contextmanager
def _repository() -> Iterator[ResourceRepository]:
    conn = connect()
    try:
        yield ResourceRepository(conn)
    finally:
        conn.close()


class EmbeddingSearchUnavailable(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _embed_query(query: str, *, embedding_model: str) -> list[float]:
    api_key = os.environ.get("XHS_EMBEDDING_API_KEY")
    base_url = os.environ.get("XHS_EMBEDDING_BASE_URL", "").strip()
    if not api_key or not base_url:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_CONFIG_MISSING")
    response = httpx.post(
        base_url.rstrip("/") + "/embeddings",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": embedding_model, "input": [query]},
        timeout=float(os.environ.get("XHS_EMBEDDING_TIMEOUT_SECONDS", "30")),
    )
    if response.status_code in {401, 403}:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_UNAUTHORIZED")
    response.raise_for_status()
    data = response.json().get("data", [])
    if len(data) != 1:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_BAD_RESPONSE")
    return [float(value) for value in data[0]["embedding"]]


def _search_payload(results: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "resource_id": item.resource_id,
            "title": item.title,
            "summary": item.summary,
            "score": item.score,
            "metadata": item.metadata,
        }
        for item in results
    ]


@tool
def search_resources(query: str, limit: int = 10, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Search readable resources by keyword and return summaries only."""
    actor = actor_from_config(config)
    with _repository() as repo:
        results = keyword_search(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            query=query,
            limit=limit,
        )
    return {"ok": True, "results": _search_payload(results)}


@tool
def semantic_search_resources(query: str, top_k: int = 10, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Search readable resources by configured embedding provider and pgvector."""
    actor = actor_from_config(config)
    with _repository() as repo:
        active_index = repo.active_embedding_index(default_tenant_id())
        if active_index is None:
            results = keyword_search(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                query=query,
                limit=top_k,
            )
            return {
                "ok": True,
                "mode": "keyword_fallback",
                "fallback_reason": "NO_ACTIVE_EMBEDDING_INDEX",
                "results": _search_payload(results),
            }
        try:
            embedding = _embed_query(query, embedding_model=active_index.embedding_model)
        except EmbeddingSearchUnavailable as exc:
            results = keyword_search(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                query=query,
                limit=top_k,
            )
            return {
                "ok": True,
                "mode": "keyword_fallback",
                "fallback_reason": exc.reason_code,
                "results": _search_payload(results),
            }
        results = semantic_search(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            embedding=embedding,
            embedding_model=active_index.embedding_model,
            top_k=top_k,
        )
    return {"ok": True, "mode": "semantic", "results": _search_payload(results)}


@tool
def get_resource(resource_id: str, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Read one resource body after tenant and permission filtering."""
    actor = actor_from_config(config)
    with _repository() as repo:
        resource = repo.get_resource(default_tenant_id(), actor, resource_id)
    if resource is None:
        return {"ok": False, "error": "Resource not found or not permitted"}
    return {
        "ok": True,
        "resource": {
            "resource_id": resource.id,
            "type": resource.type,
            "title": resource.title,
            "summary": resource.summary,
            "content_text": resource.content_text,
            "content_json": resource.content_json,
            "version": resource.version,
            "source_updated_at": (
                resource.source_updated_at.isoformat() if resource.source_updated_at else None
            ),
            "indexed_at": resource.updated_at.isoformat() if resource.updated_at else None,
        },
    }


@tool
def graph_expand(
    resource_ids: list[str],
    hops: int = 1,
    edge_types: list[str] | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Expand readable graph context from resource ids."""
    actor = actor_from_config(config)
    with _repository() as repo:
        graph = expand_graph_query(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_ids=resource_ids,
            hops=hops,
            edge_types=edge_types,
        )
    return {
        "ok": True,
        "nodes": [node.__dict__ for node in graph.nodes],
        "edges": [edge.__dict__ for edge in graph.edges],
    }


@tool
def get_data_foundation_status(config: RunnableConfig | None = None) -> dict[str, Any]:
    """Return Postgres data foundation resource, sync, and outbox status."""
    actor_from_config(config)
    with _repository() as repo:
        status = repo.data_foundation_status(default_tenant_id())
    return {"ok": True, "status": status}


@tool
def sync_feishu_resources(config: RunnableConfig | None = None) -> dict[str, Any]:
    """Trigger a manual Feishu resource sync for the current user."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return sync_feishu_sources(
            repo,
            source_repo=SourceRepository(repo.conn),
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            triggered_by="manual",
        )


@tool
def save_generated_topic(
    direction: str,
    topics: list[str],
    evidence: list[dict[str, Any]] | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist generated topic choices into the shared Postgres data foundation."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_generated_topic_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            direction=direction,
            topics=topics,
            evidence=evidence,
        )


@tool
def save_generated_copy(
    title: str,
    body: str,
    tags: list[str],
    source_topic: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist a generated Xiaohongshu copy draft into the shared Postgres data foundation."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_generated_copy_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            title=title,
            body=body,
            tags=tags,
            source_topic=source_topic,
            evidence=evidence,
        )


@tool
def save_user_feedback(
    feedback: str,
    target_resource_id: str | None = None,
    feedback_type: str = "user_feedback",
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist user feedback or a revision request into the shared Postgres data foundation."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_user_feedback_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            feedback=feedback,
            target_resource_id=target_resource_id,
            feedback_type=feedback_type,
        )


@tool
def save_performance_metric(
    target_resource_id: str,
    metrics: dict[str, Any],
    published_at: str | None = None,
    channel: str = "xiaohongshu",
    note_url: str | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist post-publish performance metrics for a generated or source content resource."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return save_performance_metric_resource(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            target_resource_id=target_resource_id,
            metrics=metrics,
            published_at=published_at,
            channel=channel,
            note_url=note_url,
        )


@tool
def get_resource_performance(
    resource_id: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Read post-publish performance metrics linked to a readable resource."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return get_resource_performance_payload(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_id=resource_id,
        )


data_foundation_tools = [
    search_resources,
    semantic_search_resources,
    graph_expand,
    get_resource,
    get_data_foundation_status,
    sync_feishu_resources,
    save_generated_topic,
    save_generated_copy,
    save_user_feedback,
    save_performance_metric,
    get_resource_performance,
]
