from __future__ import annotations

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
from data_foundation.config import embedding_snapshot_for_version
from data_foundation.db import connect
from data_foundation.graph import expand_graph as expand_graph_query
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.performance_feedback import (
    get_resource_performance_payload,
    save_performance_metric_resource,
)
from data_foundation.processors.embedding import EmbeddingProviderConfig, embedding_config_from_snapshot
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.search import semantic_search
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


def _embedding_query_config_for_index(active_index: Any) -> EmbeddingProviderConfig:
    config_version = str(getattr(active_index, "config_version", "") or "").strip()
    if not config_version:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_PROFILE_UNAVAILABLE")
    snapshot = embedding_snapshot_for_version(config_version)
    if snapshot is None:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_PROFILE_UNAVAILABLE")
    provider_config = embedding_config_from_snapshot(snapshot)
    if provider_config is None:
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_CONFIG_MISSING")
    if provider_config.state != "enabled":
        raise EmbeddingSearchUnavailable(provider_config.reason_code or "EMBEDDING_QUERY_CONFIG_INVALID")
    if (
        provider_config.model != active_index.embedding_model
        or provider_config.dimensions != active_index.dimensions
    ):
        raise EmbeddingSearchUnavailable("EMBEDDING_QUERY_PROFILE_MISMATCH")
    return provider_config


def _embed_query(query: str, *, config: EmbeddingProviderConfig) -> list[float]:
    response = httpx.post(
        config.base_url.rstrip("/") + "/embeddings",
        headers={"Authorization": f"Bearer {config.api_key}"},
        json={"model": config.model, "input": [query], "dimensions": config.dimensions},
        timeout=config.timeout_seconds,
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


def _rows_to_payload(rows: list[Any]) -> list[dict[str, Any]]:
    payload = []
    for row in rows:
        meta = {"type": row["type"], "visibility": row["visibility"]}
        if row.get("source_updated_at"):
            meta["source_updated_at"] = row["source_updated_at"].isoformat()
        if row.get("updated_at"):
            meta["indexed_at"] = row["updated_at"].isoformat()
        payload.append({
            "resource_id": str(row["id"]),
            "title": row["title"],
            "summary": row["summary"],
            "score": float(row.get("score") or 0),
            "metadata": meta,
        })
    return payload


@tool
def search_resources(query: str, limit: int = 10, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Search readable resources by full-text (Meilisearch) and return summaries only."""
    actor = actor_from_config(config)
    from data_foundation.engine_config import meili_config_from_env
    from data_foundation.meili_client import MeiliResourceIndex
    from data_foundation.search_ranker import rank_evidence

    cfg = meili_config_from_env()
    if cfg.state != "enabled":
        return {"ok": False, "error": "MEILI_UNAVAILABLE"}
    want = min(max(int(limit), 1), 20)
    # Meili 只按 tenant 过滤(无行级 owner/visibility ACL),权限裁决在 PG 后置。
    # 若只取 want 个 id 再过权限,命中里他人私有资源会挤掉可读结果 → 静默欠召回,
    # 极端返回空让 agent 误判"无数据"。故 over-fetch(want*5,上限 200),PG 过权限后
    # 按相关性序(readable_rows_by_ids 保序)截断到 want。
    over_fetch = min(want * 5, 200)
    try:
        index = MeiliResourceIndex.from_config(cfg)
        ids = index.search(query.strip(), tenant_id=default_tenant_id(), limit=over_fetch)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"MEILI_QUERY_FAILED: {exc}"}
    with _repository() as repo:
        rows = repo.readable_rows_by_ids(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_ids=ids,
        )
        valid_ids = [str(r["id"]) for r in rows]
        perf_data = repo.bulk_performance_metrics(
            tenant_id=default_tenant_id(),
            resource_ids=valid_ids,
        )
    raw_results = _rows_to_payload(rows)
    ranked_results = rank_evidence(
        tenant_id=default_tenant_id(),
        results=raw_results,
        performance_data=perf_data,
        limit=want,
    )
    return {"ok": True, "results": ranked_results}


@tool
def semantic_search_resources(query: str, top_k: int = 10, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Search readable resources by configured embedding provider and pgvector."""
    actor = actor_from_config(config)
    from data_foundation.search_ranker import rank_evidence

    def _fulltext_fallback(reason: str) -> dict[str, Any]:
        # 语义不可用时降级到全文(Meilisearch),与设计一致(全文引擎=Meili,非 PG)
        fallback = search_resources.func(query, limit=top_k, config=config)
        if not fallback.get("ok"):
            return {"ok": False, "mode": "keyword_fallback", "fallback_reason": reason,
                    "error": fallback.get("error"), "results": []}
        return {"ok": True, "mode": "keyword_fallback", "fallback_reason": reason,
                "results": fallback.get("results", [])}

    if not query or not query.strip():
        # 空查询不送 provider(避免空文本 embedding 触发 provider 报错),直接走全文。
        return _fulltext_fallback("EMPTY_QUERY")

    with _repository() as repo:
        active_index = repo.active_embedding_index(default_tenant_id())
        if active_index is None:
            return _fulltext_fallback("NO_ACTIVE_EMBEDDING_INDEX")
        try:
            query_config = _embedding_query_config_for_index(active_index)
            embedding = _embed_query(query, config=query_config)
            results = semantic_search(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                embedding=embedding,
                embedding_model=active_index.embedding_model,
                top_k=top_k * 5,
            )
            valid_ids = [res.resource_id for res in results]
            perf_data = repo.bulk_performance_metrics(
                tenant_id=default_tenant_id(),
                resource_ids=valid_ids,
            )
        except EmbeddingSearchUnavailable as exc:
            return _fulltext_fallback(exc.reason_code)
        except httpx.HTTPError as exc:
            # provider 5xx/429/超时/连接拒绝等运行时网络异常:降级到全文,不崩工具。
            return _fulltext_fallback(f"EMBEDDING_QUERY_HTTP_ERROR: {type(exc).__name__}")
        except ValueError as exc:
            # 向量校验失败(provider 忽略 dimensions 返回非预期维度、含 NaN 等):降级。
            return _fulltext_fallback(f"EMBEDDING_QUERY_INVALID_VECTOR: {exc}")
    raw_results = _search_payload(results)
    ranked_results = rank_evidence(
        tenant_id=default_tenant_id(),
        results=raw_results,
        performance_data=perf_data,
        limit=top_k,
    )
    return {"ok": True, "mode": "semantic", "results": ranked_results}


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
    try:
        with _repository() as repo:
            graph = expand_graph_query(
                repo,
                tenant_id=default_tenant_id(),
                actor_open_id=actor,
                resource_ids=resource_ids,
                hops=hops,
                edge_types=edge_types,
            )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"GRAPH_UNAVAILABLE: {exc}"}
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


@tool
def save_session_snapshot(
    project_name: str,
    title: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Persist session state, account positioning, diagnosis, or report snapshots into the Postgres database.
    Use this for session diagnostics database persistence instead of only saving locally.
    """
    actor = actor_from_config(config)
    with _repository() as repo:
        resource = repo.upsert_resource(
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            resource_type="session_snapshot",
            title=f"[{project_name}] {title}",
            summary=title,
            content_text=content,
            content_json=metadata or {},
            visibility="team",
            owner_open_id=actor,
            outbox_requests=default_write_requests(),
        )
    return {"ok": True, "resource_id": str(resource.id)}


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
    save_session_snapshot,
]

