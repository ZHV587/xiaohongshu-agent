"""Postgres 安全门之后的统一混合检索精排。

召回引擎只负责给出精确资源身份及排序。这里用 weighted RRF 合并各引擎名次，再叠加
知识质量、时效和该精确文案版本的效果事实。去重只依赖入库阶段形成的
``duplicate_family_id``，不再用标题模糊相似度临时猜测。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import math
from typing import Any, Collection, Iterable, Literal, Mapping, Sequence
import uuid

from data_foundation.metric_parse import weighted_engagement


DEFAULT_RELEVANCE_FLOOR: float = 0.50
DEFAULT_KEYWORD_RELEVANCE_FLOOR: float = 0.15
RRF_K: int = 60
RRF_ENGINE_WEIGHTS: dict[str, float] = {
    "semantic": 0.55,
    "keyword": 0.45,
    # 图谱是一跳上下文增强，不应盖过查询本身的两路召回。
    "graph": 0.15,
}

WEIGHT_RELEVANCE: float = 0.72
WEIGHT_QUALITY: float = 0.12
WEIGHT_FRESHNESS: float = 0.08
WEIGHT_PERFORMANCE: float = 0.08

P_SCORE_LOG_CAP: float = 1_000_000.0
_P_SCORE_LOG_DENOM: float = math.log10(1.0 + P_SCORE_LOG_CAP)
_FRESHNESS_HALF_LIFE_DAYS: float = 180.0

RetrievalSource = Literal["semantic", "keyword", "graph"]
ExactIdentity = tuple[str, int]


def _validate_identity(resource_id: str, resource_version: int) -> ExactIdentity:
    try:
        normalized_id = str(uuid.UUID(str(resource_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("resource_id must be a UUID") from exc
    if (
        not isinstance(resource_version, int)
        or isinstance(resource_version, bool)
        or resource_version <= 0
    ):
        raise ValueError("resource_version must be a positive integer")
    return normalized_id, resource_version


@dataclass(frozen=True)
class RecallHit:
    resource_id: str
    resource_version: int
    score: float

    def __post_init__(self) -> None:
        resource_id, resource_version = _validate_identity(
            self.resource_id, self.resource_version
        )
        score = float(self.score)
        if not math.isfinite(score):
            raise ValueError("recall score must be finite")
        object.__setattr__(self, "resource_id", resource_id)
        object.__setattr__(self, "resource_version", resource_version)
        object.__setattr__(self, "score", score)

    @property
    def identity(self) -> ExactIdentity:
        return self.resource_id, self.resource_version


@dataclass(frozen=True)
class RankedKnowledge:
    resource_id: str
    resource_version: int
    type: str
    asset_kind: str
    source_kind: str
    niche: str | None
    title: str
    summary: str
    source_updated_at: str
    indexed_at: str
    score: float
    relevance: float
    freshness: float
    quality: float
    performance: float
    retrieval_sources: tuple[RetrievalSource, ...]
    why_selected: str
    duplicate_family_id: str | None


def _first_rank(hits: Sequence[RecallHit]) -> dict[ExactIdentity, int]:
    ranks: dict[ExactIdentity, int] = {}
    for rank, hit in enumerate(hits, start=1):
        ranks.setdefault(hit.identity, rank)
    return ranks


def _first_score(hits: Sequence[RecallHit]) -> dict[ExactIdentity, float]:
    scores: dict[ExactIdentity, float] = {}
    for hit in hits:
        scores.setdefault(hit.identity, _clamp_unit(hit.score))
    return scores


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_or_unknown(value: Any) -> str:
    parsed = _parse_datetime(value)
    return "未知" if parsed is None else parsed.isoformat()


def _freshness_score(row: Mapping[str, Any], *, now: datetime) -> float:
    observed = _parse_datetime(row.get("source_updated_at")) or _parse_datetime(
        row.get("qualified_at")
    )
    if observed is None:
        return 0.5
    age_days = max(0.0, (now - observed).total_seconds() / 86_400.0)
    return math.exp(-math.log(2.0) * age_days / _FRESHNESS_HALF_LIFE_DAYS)


def _performance_score(rows: Sequence[Mapping[str, Any]]) -> float:
    best_engagement = 0.0
    for row in rows:
        engagement = weighted_engagement(dict(row.get("metrics") or {}))
        best_engagement = max(best_engagement, engagement)
    if best_engagement <= 0:
        return 0.0
    return min(
        math.log10(1.0 + best_engagement) / _P_SCORE_LOG_DENOM,
        1.0,
    )


def _clamp_unit(value: Any, *, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return min(max(parsed, 0.0), 1.0)


def _required_text(row: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(f"ranked knowledge row is missing required field: {'/'.join(keys)}")


def weighted_rrf_order(
    *,
    semantic_hits: Sequence[RecallHit],
    keyword_hits: Sequence[RecallHit],
    graph_hits: Sequence[RecallHit] = (),
    active_sources: Collection[RetrievalSource] | None = None,
) -> list[ExactIdentity]:
    """返回候选的纯 RRF 顺序，供图扩展挑选种子与最终精排共同复用。"""

    hits_by_source: dict[RetrievalSource, Sequence[RecallHit]] = {
        "semantic": semantic_hits,
        "keyword": keyword_hits,
        "graph": graph_hits,
    }
    sources = set(active_sources or ())
    if not sources:
        sources = {source for source, hits in hits_by_source.items() if hits}
    sources &= set(RRF_ENGINE_WEIGHTS)  # type: ignore[arg-type]
    rank_maps = {source: _first_rank(hits_by_source[source]) for source in sources}
    score_maps = {source: _first_score(hits_by_source[source]) for source in sources}
    identities = {
        identity
        for rank_map in rank_maps.values()
        for identity in rank_map
    }

    def score(identity: ExactIdentity) -> float:
        return sum(
            RRF_ENGINE_WEIGHTS[source]
            * score_maps[source][identity]
            / (RRF_K + rank_map[identity])
            for source, rank_map in rank_maps.items()
            if identity in rank_map
        )

    return sorted(identities, key=lambda identity: (-score(identity), identity))


def rank_knowledge_candidates(
    *,
    rows: Sequence[Mapping[str, Any]],
    semantic_hits: Sequence[RecallHit],
    keyword_hits: Sequence[RecallHit],
    graph_hits: Sequence[RecallHit] = (),
    active_sources: Collection[RetrievalSource],
    performance_data: Mapping[ExactIdentity, Sequence[Mapping[str, Any]]],
    limit: int = 10,
    now: datetime | None = None,
) -> list[RankedKnowledge]:
    """对已经过 current knowledge + ACL 门的行进行确定性精排。"""

    safe_limit = min(max(int(limit), 1), 50)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)

    hits_by_source: dict[RetrievalSource, Sequence[RecallHit]] = {
        "semantic": semantic_hits,
        "keyword": keyword_hits,
        "graph": graph_hits,
    }
    sources = set(active_sources) & set(RRF_ENGINE_WEIGHTS)  # type: ignore[arg-type]
    rank_maps = {source: _first_rank(hits_by_source[source]) for source in sources}
    score_maps = {source: _first_score(hits_by_source[source]) for source in sources}
    denominator = sum(
        RRF_ENGINE_WEIGHTS[source] / (RRF_K + 1)
        for source in sources
    )
    if denominator <= 0:
        return []

    candidates: list[RankedKnowledge] = []
    for row in rows:
        identity = _validate_identity(
            str(row["resource_id"]), int(row["resource_version"])
        )
        retrieval_sources = tuple(
            source
            for source in ("semantic", "keyword", "graph")
            if identity in rank_maps.get(source, {})
        )
        if not retrieval_sources:
            continue
        rrf_raw = sum(
            RRF_ENGINE_WEIGHTS[source]
            * score_maps[source][identity]
            / (RRF_K + rank_maps[source][identity])
            for source in retrieval_sources
        )
        relevance = min(max(rrf_raw / denominator, 0.0), 1.0)
        quality = _clamp_unit(row.get("quality_score"))
        freshness = _freshness_score(row, now=now)
        performance = _performance_score(performance_data.get(identity, ()))
        final_score = (
            WEIGHT_RELEVANCE * relevance
            + WEIGHT_QUALITY * quality
            + WEIGHT_FRESHNESS * freshness
            + WEIGHT_PERFORMANCE * performance
        )

        source_label = "+".join(retrieval_sources)
        why = (
            f"{source_label} 召回；RRF {relevance:.2f}，质量 {quality:.2f}，"
            f"时效 {freshness:.2f}，效果 {performance:.2f}"
        )
        summary = str(row.get("summary") or "").strip()
        if not summary:
            summary = str(row.get("content_text") or "").strip()[:240]
        duplicate_family_id = row.get("duplicate_family_id")
        candidates.append(
            RankedKnowledge(
                resource_id=identity[0],
                resource_version=identity[1],
                type=_required_text(row, "resource_type", "type"),
                asset_kind=_required_text(row, "asset_kind"),
                source_kind=_required_text(row, "source_kind"),
                niche=(str(row["niche"]).strip() or None) if row.get("niche") else None,
                title=str(row.get("title") or ""),
                summary=summary,
                source_updated_at=_iso_or_unknown(row.get("source_updated_at")),
                indexed_at=_iso_or_unknown(row.get("indexed_at")),
                score=round(min(max(final_score, 0.0), 1.0), 6),
                relevance=round(relevance, 6),
                freshness=round(freshness, 6),
                quality=round(quality, 6),
                performance=round(performance, 6),
                retrieval_sources=retrieval_sources,
                why_selected=why,
                duplicate_family_id=(
                    str(duplicate_family_id) if duplicate_family_id is not None else None
                ),
            )
        )

    candidates.sort(
        key=lambda item: (
            -item.score,
            -item.relevance,
            -item.quality,
            item.resource_id,
            item.resource_version,
        )
    )

    # 家族是入库清洗阶段的稳定事实。每个家族只保留精排最高的一条；无家族数据不互相误杀。
    result: list[RankedKnowledge] = []
    seen_families: set[str] = set()
    for item in candidates:
        family = item.duplicate_family_id
        if family is not None:
            if family in seen_families:
                continue
            seen_families.add(family)
        result.append(item)
        if len(result) >= safe_limit:
            break
    return result


__all__ = [
    "DEFAULT_RELEVANCE_FLOOR",
    "DEFAULT_KEYWORD_RELEVANCE_FLOOR",
    "ExactIdentity",
    "P_SCORE_LOG_CAP",
    "RRF_ENGINE_WEIGHTS",
    "RRF_K",
    "RankedKnowledge",
    "RecallHit",
    "WEIGHT_FRESHNESS",
    "WEIGHT_PERFORMANCE",
    "WEIGHT_QUALITY",
    "WEIGHT_RELEVANCE",
    "rank_knowledge_candidates",
    "weighted_rrf_order",
]
