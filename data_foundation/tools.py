from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import OpenAIEmbeddings

from data_foundation.db import connect
from data_foundation.graph import expand_graph as expand_graph_query
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.repository import ResourceRepository
from data_foundation.search import keyword_search, semantic_search


@contextmanager
def _repository() -> Iterator[ResourceRepository]:
    conn = connect()
    try:
        yield ResourceRepository(conn)
    finally:
        conn.close()


def _embedding_model_name() -> str:
    return os.environ.get("XHS_EMBEDDING_MODEL", "text-embedding-3-small").strip()


def _embed_query(query: str) -> list[float]:
    api_key = os.environ.get("XHS_EMBEDDING_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("XHS_EMBEDDING_API_KEY or LLM_API_KEY is required for semantic search")
    embeddings = OpenAIEmbeddings(
        model=_embedding_model_name(),
        api_key=api_key,
        base_url=os.environ.get("XHS_EMBEDDING_BASE_URL") or os.environ.get("LLM_BASE_URL"),
    )
    return [float(value) for value in embeddings.embed_query(query)]


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
        results = semantic_search(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            embedding=_embed_query(query),
            embedding_model=_embedding_model_name(),
            top_k=top_k,
        )
    return {"ok": True, "results": _search_payload(results)}


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


phase3_tools = [search_resources, semantic_search_resources, graph_expand, get_resource]
