from datetime import datetime, timezone
import math
import uuid

import pytest

from data_foundation.search_ranker import (
    RRF_ENGINE_WEIGHTS,
    RecallHit,
    WEIGHT_FRESHNESS,
    WEIGHT_PERFORMANCE,
    WEIGHT_QUALITY,
    WEIGHT_RELEVANCE,
    rank_knowledge_candidates,
    weighted_rrf_order,
)


def _id(seed: int) -> str:
    return str(uuid.UUID(int=seed))


def _row(
    seed: int,
    *,
    version: int = 1,
    family: str | None = None,
    quality: float = 0.8,
) -> dict:
    return {
        "resource_id": _id(seed),
        "resource_version": version,
        "resource_type": "generated_copy",
        "asset_kind": "copy",
        "source_kind": "user_adopted",
        "niche": "职场",
        "title": f"标题 {seed}",
        "summary": f"摘要 {seed}",
        "quality_score": quality,
        "duplicate_family_id": family,
        "qualified_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "indexed_at": datetime(2026, 7, 2, tzinfo=timezone.utc),
        "source_updated_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }


def test_rank_weights_are_normalized() -> None:
    assert sum(
        (WEIGHT_RELEVANCE, WEIGHT_QUALITY, WEIGHT_FRESHNESS, WEIGHT_PERFORMANCE)
    ) == pytest.approx(1.0)
    assert RRF_ENGINE_WEIGHTS["semantic"] > RRF_ENGINE_WEIGHTS["keyword"]
    assert RRF_ENGINE_WEIGHTS["graph"] < RRF_ENGINE_WEIGHTS["keyword"]


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf])
def test_recall_hit_rejects_non_finite_scores(score: float) -> None:
    with pytest.raises(ValueError):
        RecallHit(_id(1), 1, score)


@pytest.mark.parametrize("resource_version", [None, 0, -1, True, 1.5])
def test_recall_hit_requires_exact_positive_version(resource_version) -> None:
    with pytest.raises(ValueError):
        RecallHit(_id(1), resource_version, 0.8)


def test_weighted_rrf_prefers_candidate_recalled_by_both_primary_engines() -> None:
    semantic = [RecallHit(_id(1), 1, 0.9), RecallHit(_id(2), 1, 0.8)]
    keyword = [RecallHit(_id(2), 1, 0.7), RecallHit(_id(3), 1, 0.6)]

    ordered = weighted_rrf_order(
        semantic_hits=semantic,
        keyword_hits=keyword,
        active_sources=["semantic", "keyword"],
    )

    assert ordered[0] == (_id(2), 1)
    assert set(ordered) == {(_id(1), 1), (_id(2), 1), (_id(3), 1)}


def test_rank_returns_complete_exact_evidence_signals() -> None:
    identity = (_id(1), 2)
    ranked = rank_knowledge_candidates(
        rows=[_row(1, version=2)],
        semantic_hits=[RecallHit(*identity, 0.91)],
        keyword_hits=[RecallHit(*identity, 0.77)],
        active_sources=["semantic", "keyword"],
        performance_data={identity: [{"metrics": {"likes": 1200, "collects": 400}}]},
        now=datetime(2026, 7, 13, tzinfo=timezone.utc),
    )
    assert len(ranked) == 1
    item = ranked[0]
    assert (item.resource_id, item.resource_version) == identity
    assert item.retrieval_sources == ("semantic", "keyword")
    assert item.type == "generated_copy"
    assert item.asset_kind == "copy"
    assert item.source_kind == "user_adopted"
    assert item.source_updated_at.startswith("2026-06-30")
    assert item.indexed_at.startswith("2026-07-02")
    assert item.performance > 0
    assert all(
        0.0 <= value <= 1.0
        for value in (
            item.score,
            item.relevance,
            item.quality,
            item.freshness,
            item.performance,
        )
    )


def test_keyword_raw_score_is_preserved_in_relevance_instead_of_rank_one_becoming_one():
    identity = (_id(1), 1)
    ranked = rank_knowledge_candidates(
        rows=[_row(1)],
        semantic_hits=[],
        keyword_hits=[RecallHit(*identity, 0.2)],
        active_sources=["keyword"],
        performance_data={},
    )

    assert ranked[0].relevance == pytest.approx(0.2)


def test_rank_uses_exact_performance_identity_not_other_version() -> None:
    identity = (_id(1), 1)
    other_version = (_id(1), 2)
    ranked = rank_knowledge_candidates(
        rows=[_row(1, version=1)],
        semantic_hits=[RecallHit(*identity, 0.9)],
        keyword_hits=[],
        active_sources=["semantic"],
        performance_data={other_version: [{"metrics": {"likes": 999999}}]},
    )
    assert ranked[0].performance == 0.0


def test_rank_deduplicates_only_by_persisted_family() -> None:
    family = str(uuid.uuid4())
    rows = [_row(1, family=family), _row(2, family=family), _row(3, family=None)]
    hits = [RecallHit(_id(seed), 1, 1.0 - seed / 10) for seed in (1, 2, 3)]

    ranked = rank_knowledge_candidates(
        rows=rows,
        semantic_hits=hits,
        keyword_hits=[],
        active_sources=["semantic"],
        performance_data={},
        limit=10,
    )

    identities = {(item.resource_id, item.resource_version) for item in ranked}
    assert len(identities & {(_id(1), 1), (_id(2), 1)}) == 1
    assert (_id(3), 1) in identities


def test_rank_ignores_rows_that_no_engine_recalled() -> None:
    ranked = rank_knowledge_candidates(
        rows=[_row(1)],
        semantic_hits=[],
        keyword_hits=[],
        active_sources=[],
        performance_data={},
    )
    assert ranked == []


def test_rank_fails_on_missing_authoritative_classification_fields() -> None:
    row = _row(1)
    row.pop("asset_kind")
    with pytest.raises(ValueError, match="asset_kind"):
        rank_knowledge_candidates(
            rows=[row],
            semantic_hits=[RecallHit(_id(1), 1, 0.9)],
            keyword_hits=[],
            active_sources=["semantic"],
            performance_data={},
        )
