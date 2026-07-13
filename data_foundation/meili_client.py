from __future__ import annotations

import json
import math
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import meilisearch

from data_foundation.engine_config import MeiliConfig


MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION = "knowledge-hybrid-v2"

# Reuse the underlying HTTP client for a deployment config. A URL/key change creates
# a new client naturally; no secret is ever included in logs or exceptions here.
_client_cache: dict[tuple[str, str], Any] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class MeiliTenantAudit:
    """Tenant cardinality split by the currently deployable index schema."""

    total_documents: int
    current_schema_documents: int

    @property
    def stale_schema_documents(self) -> int:
        return max(0, self.total_documents - self.current_schema_documents)


@dataclass(frozen=True)
class MeiliSearchHit:
    """Typed keyword candidate; PostgreSQL still owns ACL and final hydration."""

    resource_id: str
    resource_version: int
    score: float
    resource_type: str
    asset_kind: str
    source_kind: str
    niche: str | None
    quality_score: float
    qualified_at_epoch: int
    tags: tuple[str, ...] = ()
    hook_types: tuple[str, ...] = ()
    cta_types: tuple[str, ...] = ()
    structure_tags: tuple[str, ...] = ()
    style_tags: tuple[str, ...] = ()
    success_factors: tuple[str, ...] = ()


def _reset_client_cache() -> None:
    with _cache_lock:
        _client_cache.clear()


def _get_client(config: MeiliConfig) -> Any:
    key = (config.url, config.api_key)
    with _cache_lock:
        client = _client_cache.get(key)
        if client is None:
            client = meilisearch.Client(config.url, config.api_key, timeout=30)
            _client_cache[key] = client
        return client


def _json_literal(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _validated_string_list(value: Any, *, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be a list of strings")
    if len(value) > 50:
        raise ValueError(f"{field} accepts at most 50 values")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"{field} must contain only strings")
        text = item.strip()
        if not text or len(text) > 128:
            raise ValueError(f"{field} values must be 1..128 characters")
        if text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)


def _updated_after_epoch(value: Any) -> int:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("updated_after must be an ISO 8601 string")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("updated_after must be an ISO 8601 string") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("updated_after must include a timezone")
    epoch = int(parsed.timestamp())
    if epoch < 0:
        raise ValueError("updated_after must not precede the Unix epoch")
    return epoch


def _compile_metadata_filters(filters: Mapping[str, Any] | None) -> list[str]:
    if filters is None:
        return []
    if not isinstance(filters, Mapping):
        raise ValueError("filters must be an object")
    allowed = {
        "asset_kinds",
        "source_kinds",
        "niches",
        "min_quality",
        "updated_after",
    }
    unknown = set(filters) - allowed
    if unknown:
        raise ValueError(f"unsupported Meili filters: {', '.join(sorted(unknown))}")

    clauses: list[str] = []
    for public_name, document_name in (
        ("asset_kinds", "asset_kind"),
        ("source_kinds", "source_kind"),
        ("niches", "niche"),
    ):
        values = _validated_string_list(filters.get(public_name), field=public_name)
        if values:
            literals = ", ".join(_json_literal(value) for value in values)
            clauses.append(f"{document_name} IN [{literals}]")

    min_quality = filters.get("min_quality")
    if min_quality is not None:
        if (
            isinstance(min_quality, bool)
            or not isinstance(min_quality, (int, float))
            or not math.isfinite(float(min_quality))
            or not 0.0 <= float(min_quality) <= 1.0
        ):
            raise ValueError("min_quality must be a finite number between 0 and 1")
        clauses.append(f"quality_score >= {float(min_quality):.12g}")

    updated_after = filters.get("updated_after")
    if updated_after is not None:
        clauses.append(f"qualified_at_epoch >= {_updated_after_epoch(updated_after)}")
    return clauses


def _hit_strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item)


class MeiliResourceIndex:
    SEARCHABLE = [
        "title",
        "summary",
        "content_text",
        "normalized_text",
        "niche",
        "tags",
        "hook_types",
        "cta_types",
        "structure_tags",
        "style_tags",
        "success_factors",
    ]
    FILTERABLE = [
        "tenant_id",
        "resource_version",
        "type",
        "asset_kind",
        "source_kind",
        "niche",
        "quality_score",
        "qualified_at_epoch",
        "index_schema_version",
    ]

    def __init__(self, *, client: Any, index_uid: str = "resources"):
        self.client = client
        self.index_uid = index_uid

    @classmethod
    def from_config(cls, config: MeiliConfig) -> "MeiliResourceIndex":
        return cls(client=_get_client(config))

    def ensure_index(self) -> None:
        index = self.client.index(self.index_uid)
        tasks = (
            ("filterable attributes", index.update_filterable_attributes(self.FILTERABLE)),
            ("searchable attributes", index.update_searchable_attributes(self.SEARCHABLE)),
        )
        for operation, info in tasks:
            task = index.wait_for_task(info.task_uid, timeout_in_ms=30000)
            status = getattr(task, "status", None)
            if status != "succeeded":
                raise RuntimeError(
                    f"Meili {operation} task not succeeded: status={status} "
                    f"error={getattr(task, 'error', None)}"
                )

    def upsert(self, document: dict[str, Any]) -> None:
        index = self.client.index(self.index_uid)
        info = index.add_documents([document], primary_key="resource_id")
        task = index.wait_for_task(info.task_uid, timeout_in_ms=30000)
        status = getattr(task, "status", None)
        if status != "succeeded":
            raise RuntimeError(
                f"Meili add_documents task not succeeded: status={status} "
                f"error={getattr(task, 'error', None)}"
            )

    def delete(self, resource_id: str) -> None:
        index = self.client.index(self.index_uid)
        info = index.delete_document(resource_id)
        task = index.wait_for_task(info.task_uid, timeout_in_ms=30000)
        status = getattr(task, "status", None)
        if status != "succeeded":
            raise RuntimeError(
                f"Meili delete_document task not succeeded: status={status} "
                f"error={getattr(task, 'error', None)}"
            )

    def audit_tenant(self, *, tenant_id: str) -> MeiliTenantAudit:
        """Count only exact documents written with the active hybrid schema."""
        tenant_literal = _json_literal(tenant_id)
        index = self.client.index(self.index_uid)

        def _count(filter_expression: str) -> int:
            result = index.search(
                "",
                opt_params={"filter": filter_expression, "limit": 0},
            )
            return int(result.get("estimatedTotalHits") or result.get("totalHits") or 0)

        total = _count(f"tenant_id = {tenant_literal}")
        current = _count(
            f"tenant_id = {tenant_literal} "
            f"AND index_schema_version = {_json_literal(MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION)} "
            "AND resource_version >= 1"
        )
        return MeiliTenantAudit(
            total_documents=total,
            current_schema_documents=current,
        )

    def search(
        self,
        query: str,
        *,
        tenant_id: str,
        limit: int,
        filters: Mapping[str, Any] | None = None,
    ) -> list[MeiliSearchHit]:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        clauses = [
            f"tenant_id = {_json_literal(tenant_id)}",
            "index_schema_version = "
            f"{_json_literal(MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION)}",
            *_compile_metadata_filters(filters),
        ]
        result = self.client.index(self.index_uid).search(
            query,
            opt_params={
                "filter": " AND ".join(clauses),
                "limit": limit,
                "showRankingScore": True,
            },
        )
        hits: list[MeiliSearchHit] = []
        for hit in result.get("hits", []):
            version = hit.get("resource_version")
            qualified_at_epoch = hit.get("qualified_at_epoch")
            quality_score = hit.get("quality_score")
            asset_kind = hit.get("asset_kind")
            source_kind = hit.get("source_kind")
            resource_type = hit.get("type")
            if (
                hit.get("index_schema_version") != MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION
                or not isinstance(version, int)
                or isinstance(version, bool)
                or version <= 0
                or not isinstance(qualified_at_epoch, int)
                or isinstance(qualified_at_epoch, bool)
                or qualified_at_epoch < 0
                or isinstance(quality_score, bool)
                or not isinstance(quality_score, (int, float))
                or not math.isfinite(float(quality_score))
                or not 0.0 <= float(quality_score) <= 1.0
                or not isinstance(asset_kind, str)
                or not asset_kind
                or not isinstance(source_kind, str)
                or not source_kind
                or not isinstance(resource_type, str)
                or not resource_type
                or not hit.get("resource_id")
            ):
                continue
            score = hit.get("_rankingScore") or 0.0
            if (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not math.isfinite(float(score))
            ):
                score = 0.0
            niche = hit.get("niche")
            hits.append(
                MeiliSearchHit(
                    resource_id=str(hit["resource_id"]),
                    resource_version=version,
                    score=float(score),
                    resource_type=resource_type,
                    asset_kind=asset_kind,
                    source_kind=source_kind,
                    niche=niche if isinstance(niche, str) and niche else None,
                    quality_score=float(quality_score),
                    qualified_at_epoch=qualified_at_epoch,
                    tags=_hit_strings(hit.get("tags")),
                    hook_types=_hit_strings(hit.get("hook_types")),
                    cta_types=_hit_strings(hit.get("cta_types")),
                    structure_tags=_hit_strings(hit.get("structure_tags")),
                    style_tags=_hit_strings(hit.get("style_tags")),
                    success_factors=_hit_strings(hit.get("success_factors")),
                )
            )
        return hits


__all__ = [
    "MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION",
    "MeiliResourceIndex",
    "MeiliSearchHit",
    "MeiliTenantAudit",
]
