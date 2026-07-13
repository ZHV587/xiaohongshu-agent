from datetime import datetime, timezone
import uuid

from hypothesis import given, strategies as st
import pytest

from data_foundation.search_ranker import RecallHit, rank_knowledge_candidates


RESOURCE_ID = str(uuid.UUID(int=1))
IDENTITY = (RESOURCE_ID, 1)


def _rank(metrics: dict) -> float:
    rows = [
        {
            "resource_id": RESOURCE_ID,
            "resource_version": 1,
            "resource_type": "xhs_online_note",
            "asset_kind": "benchmark",
            "source_kind": "viral_teardown",
            "title": "同一素材",
            "summary": "同一摘要",
            "quality_score": 0.8,
            "qualified_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "indexed_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        }
    ]
    ranked = rank_knowledge_candidates(
        rows=rows,
        semantic_hits=[RecallHit(RESOURCE_ID, 1, 0.9)],
        keyword_hits=[],
        active_sources=["semantic"],
        performance_data={IDENTITY: [{"metrics": metrics}]},
        now=datetime(2026, 7, 13, tzinfo=timezone.utc),
    )
    return ranked[0].performance


def test_no_effect_facts_produce_zero_performance() -> None:
    assert _rank({}) == 0.0
    assert _rank({"likes": 0, "collects": 0, "comments": 0}) == 0.0


def test_performance_is_monotonic_but_not_immediately_saturated() -> None:
    scores = [
        _rank({"likes": 10}),
        _rank({"likes": 1_000}),
        _rank({"likes": 100_000}),
        _rank({"likes": 1_000_000}),
    ]
    assert scores == sorted(scores)
    assert len(set(scores)) == len(scores)
    assert scores[-1] <= 1.0


def test_best_exact_effect_snapshot_wins() -> None:
    low = _rank({"likes": 20})
    rows = [
        {
            "resource_id": RESOURCE_ID,
            "resource_version": 1,
            "resource_type": "xhs_online_note",
            "asset_kind": "benchmark",
            "source_kind": "viral_teardown",
            "title": "素材",
            "summary": "摘要",
            "quality_score": 0.8,
            "qualified_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "indexed_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        }
    ]
    ranked = rank_knowledge_candidates(
        rows=rows,
        semantic_hits=[RecallHit(RESOURCE_ID, 1, 0.9)],
        keyword_hits=[],
        active_sources=["semantic"],
        performance_data={
            IDENTITY: [
                {"metrics": {"likes": 20}},
                {"metrics": {"likes": 20_000}},
            ]
        },
    )
    assert ranked[0].performance > low


@given(
    likes=st.integers(min_value=0, max_value=10_000_000),
    collects=st.integers(min_value=0, max_value=10_000_000),
    comments=st.integers(min_value=0, max_value=10_000_000),
)
def test_performance_property_is_bounded(likes: int, collects: int, comments: int) -> None:
    score = _rank({"likes": likes, "collects": collects, "comments": comments})
    assert 0.0 <= score <= 1.0
    if likes == collects == comments == 0:
        assert score == pytest.approx(0.0)
