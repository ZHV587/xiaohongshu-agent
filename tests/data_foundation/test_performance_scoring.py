from datetime import datetime, timedelta, timezone

import pytest

from data_foundation.performance_scoring import (
    MIN_COHORT_SIZE,
    normalize_performance,
    normalized_performance_from_payload,
)


NOW = datetime(2026, 7, 15, tzinfo=timezone.utc)


def test_missing_exposure_is_saved_but_never_learned_or_ranked() -> None:
    result = normalize_performance(
        {"likes": 100_000, "collects": 20_000}, observed_at=NOW
    )
    assert result.status == "missing_exposure"
    assert result.score == 0.0
    assert result.confidence == 0.0
    assert result.learning_eligible is False
    assert normalized_performance_from_payload(
        {"metrics": {"likes": 100_000}}
    ) == (0.0, 0.0)


def test_zero_interactions_with_real_exposure_is_a_trusted_low_outcome() -> None:
    result = normalize_performance(
        {"views": 10_000, "likes": 0, "collects": 0},
        published_at=NOW - timedelta(days=10),
        observed_at=NOW,
    )
    assert result.score == 0.0
    assert result.confidence > 0.25
    assert result.learning_eligible is True
    assert result.status == "eligible"


def test_small_sample_high_conversion_cannot_beat_mature_evidence() -> None:
    tiny = normalize_performance(
        {"views": 10, "likes": 10},
        published_at=NOW - timedelta(hours=2),
        observed_at=NOW,
    )
    mature = normalize_performance(
        {"views": 10_000, "likes": 800, "collects": 200},
        published_at=NOW - timedelta(days=10),
        observed_at=NOW,
    )
    assert tiny.raw_engagement_rate == pytest.approx(1.0)
    assert tiny.confidence < mature.confidence
    assert tiny.score < mature.score


def test_mature_higher_rate_scores_above_mature_lower_rate() -> None:
    low = normalize_performance(
        {"views": 10_000, "likes": 100},
        published_at=NOW - timedelta(days=10),
        observed_at=NOW,
    )
    high = normalize_performance(
        {"views": 10_000, "likes": 600, "collects": 100},
        published_at=NOW - timedelta(days=10),
        observed_at=NOW,
    )
    assert 0.0 <= low.score < high.score <= 1.0


def test_cohort_percentile_only_activates_after_minimum_sample() -> None:
    base = dict(
        metrics={"views": 5000, "likes": 200},
        published_at=NOW - timedelta(days=10),
        observed_at=NOW,
    )
    below = normalize_performance(**base, cohort_scores=[0.1] * (MIN_COHORT_SIZE - 1))
    ready = normalize_performance(
        **base,
        cohort_scores=[index / MIN_COHORT_SIZE for index in range(MIN_COHORT_SIZE)],
    )
    assert below.cohort_percentile is None
    assert ready.cohort_percentile is not None
    assert ready.cohort_size == MIN_COHORT_SIZE
