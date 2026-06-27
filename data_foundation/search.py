from __future__ import annotations

import math
from typing import Any

from data_foundation.models import ResourceSearchResult
from data_foundation.repositories.resource import ResourceRepository


def validate_embedding(embedding: list[float]) -> None:
    if len(embedding) != 1536:
        raise ValueError("Embedding must contain exactly 1536 finite numbers")
    for value in embedding:
        try:
            finite = math.isfinite(float(value))
        except (TypeError, ValueError):
            finite = False
        if not finite:
            raise ValueError("Embedding must contain exactly 1536 finite numbers")


def _result_from_row(row: Any) -> ResourceSearchResult:
    metadata = {"type": row["type"], "visibility": row["visibility"]}
    source_updated_at = row.get("source_updated_at") if hasattr(row, "get") else None
    indexed_at = row.get("updated_at") if hasattr(row, "get") else None
    if source_updated_at is not None:
        metadata["source_updated_at"] = source_updated_at.isoformat()
    if indexed_at is not None:
        metadata["indexed_at"] = indexed_at.isoformat()
    if "chunk_index" in row:
        metadata.update(chunk_index=int(row["chunk_index"]), chunk_text=row["chunk_text"])
    return ResourceSearchResult(
        resource_id=str(row["id"]),
        title=row["title"],
        summary=row["summary"],
        score=float(row["score"] or 0),
        metadata=metadata,
    )


def semantic_search(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    embedding: list[float],
    embedding_model: str,
    top_k: int = 10,
) -> list[ResourceSearchResult]:
    # 返回的 ResourceSearchResult.score 为**绝对余弦相似度**(semantic_rows 内
    # `1 - (embedding <=> vector)`,约 0~1),供工具层闸门与 rank_evidence(score_kind="cosine")
    # 直接按绝对值使用,不做候选集内归一化。
    validate_embedding(embedding)
    embedding_model = embedding_model.strip()
    if not embedding_model:
        raise ValueError("Embedding model is required")
    rows = repo.semantic_rows(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        embedding=embedding,
        embedding_model=embedding_model,
        # 上限 100(不是 20):工具层传 top_k*5 做去重 + rerank 的候选头寸,若这里砍回 20,
        # top_k≥4 时 5× over-fetch 完全失效、去重后欠填。工具层已对**最终**结果另做 [1,20] clamp,
        # 这里只约束候选池规模,放到 100 让 over-fetch 真正生效,同时仍有界。
        top_k=min(max(int(top_k), 1), 100),
    )
    best_by_resource: dict[str, ResourceSearchResult] = {}
    for row in rows:
        result = _result_from_row(row)
        previous = best_by_resource.get(result.resource_id)
        if previous is None or result.score > previous.score:
            best_by_resource[result.resource_id] = result
    return sorted(best_by_resource.values(), key=lambda item: item.score, reverse=True)
