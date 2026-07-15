"""小红书效果事实的统一归一化与可信度口径。"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math
from typing import Any, Mapping, Sequence

from data_foundation.metric_parse import weighted_engagement


PRIOR_VIEWS = 1_000.0
PRIOR_ENGAGEMENT_RATE = 0.03
EXCELLENT_ENGAGEMENT_RATE = 0.12
MIN_LEARNING_CONFIDENCE = 0.25
MIN_COHORT_SIZE = 20
FULL_OBSERVATION_DAYS = 7.0


@dataclass(frozen=True)
class NormalizedPerformance:
    schema_version: int
    score: float
    confidence: float
    learning_eligible: bool
    status: str
    weighted_engagement: float
    views: float | None
    raw_engagement_rate: float | None
    posterior_engagement_rate: float | None
    observation_window_days: float | None
    cohort_percentile: float | None
    cohort_size: int

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def normalize_performance(
    metrics: Mapping[str, Any],
    *,
    published_at: str | datetime | None = None,
    observed_at: datetime | None = None,
    cohort_scores: Sequence[float] = (),
) -> NormalizedPerformance:
    """把不同账号/时间的绝对声量变为有置信度的 ``[0, 1]`` 效果分。

    缺少 ``views`` 时绝不再拿一个点赞当作满分；这种事实仍保存，但只作低置信度
    观测，不能强化偏好或参与效果精排。
    """

    observed = observed_at or datetime.now(timezone.utc)
    observed = _utc(observed)
    weighted = max(weighted_engagement(dict(metrics)), 0.0)
    views = _finite_nonnegative(metrics.get("views"))
    window_days = _observation_window_days(published_at, observed)
    if views is None or views <= 0:
        return NormalizedPerformance(
            schema_version=1,
            score=0.0,
            confidence=0.0,
            learning_eligible=False,
            status="missing_exposure",
            weighted_engagement=round(weighted, 6),
            views=views,
            raw_engagement_rate=None,
            posterior_engagement_rate=None,
            observation_window_days=window_days,
            cohort_percentile=None,
            cohort_size=len(_valid_scores(cohort_scores)),
        )

    raw_rate = weighted / views
    posterior_rate = (
        weighted + PRIOR_VIEWS * PRIOR_ENGAGEMENT_RATE
    ) / (views + PRIOR_VIEWS)
    # 贝叶斯先验只负责抑制小样本高转化，不能凭空把 0 互动抬成正效果。
    quality_index = _unit(posterior_rate / EXCELLENT_ENGAGEMENT_RATE) * _unit(
        raw_rate / PRIOR_ENGAGEMENT_RATE
    )
    volume_confidence = views / (views + PRIOR_VIEWS)
    time_confidence = (
        0.7
        if window_days is None
        else _unit(window_days / FULL_OBSERVATION_DAYS)
    )
    confidence = _unit(volume_confidence * time_confidence)
    cohort = _valid_scores(cohort_scores)
    # 低样本数据可参与展示，但在排序中按置信度收缩，不能用偶然高转化压过成熟样本。
    confidence_factor = 0.35 + 0.65 * confidence
    base_score = quality_index * confidence_factor
    percentile = (
        _percentile_rank(base_score, cohort)
        if len(cohort) >= MIN_COHORT_SIZE
        else None
    )
    score = (
        base_score
        if percentile is None
        else 0.7 * base_score + 0.3 * percentile * confidence_factor
    )
    learning_eligible = confidence >= MIN_LEARNING_CONFIDENCE
    return NormalizedPerformance(
        schema_version=1,
        score=round(score, 6),
        confidence=round(confidence, 6),
        learning_eligible=learning_eligible,
        status="eligible" if learning_eligible else "low_confidence",
        weighted_engagement=round(weighted, 6),
        views=round(views, 6),
        raw_engagement_rate=round(raw_rate, 8),
        posterior_engagement_rate=round(posterior_rate, 8),
        observation_window_days=window_days,
        cohort_percentile=None if percentile is None else round(percentile, 6),
        cohort_size=len(cohort),
    )


def normalized_performance_from_payload(payload: Mapping[str, Any]) -> tuple[float, float]:
    normalized = payload.get("normalized_performance")
    if isinstance(normalized, Mapping) and normalized.get("schema_version") == 1:
        return _unit(normalized.get("score")), _unit(normalized.get("confidence"))
    # 历史数据只在具备曝光量时按同一新口径即时重算；无曝光绝不回退绝对互动量。
    rebuilt = normalize_performance(
        dict(payload.get("metrics") or {}),
        published_at=payload.get("published_at"),
    )
    return rebuilt.score, rebuilt.confidence


def _observation_window_days(
    published_at: str | datetime | None, observed_at: datetime
) -> float | None:
    published = _parse_datetime(published_at)
    if published is None:
        return None
    return round(max((observed_at - published).total_seconds() / 86_400.0, 0.0), 4)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if isinstance(value, datetime):
        return _utc(value)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return _utc(datetime.fromisoformat(value.strip().replace("Z", "+00:00")))
    except ValueError:
        return None


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _finite_nonnegative(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) and parsed >= 0 else None


def _valid_scores(values: Sequence[float]) -> list[float]:
    return [
        _unit(value)
        for value in values
        if not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    ]


def _percentile_rank(value: float, cohort: Sequence[float]) -> float:
    below = sum(item < value for item in cohort)
    equal = sum(item == value for item in cohort)
    return _unit((below + 0.5 * equal) / len(cohort))


def _unit(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(parsed):
        return 0.0
    return min(max(parsed, 0.0), 1.0)


__all__ = [
    "MIN_COHORT_SIZE",
    "MIN_LEARNING_CONFIDENCE",
    "NormalizedPerformance",
    "normalize_performance",
    "normalized_performance_from_payload",
]
