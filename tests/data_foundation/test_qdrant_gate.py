"""Qdrant 只能通过连续退化、严格配对、统计非劣与运维硬门。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_foundation.qdrant_gate import (
    QdrantDecisionInput,
    QdrantDecisionPolicy,
    decide_qdrant,
)


ROOT = Path(__file__).resolve().parents[2]

FINGERPRINTS = {
    "dataset_fingerprint": "a" * 64,
    "query_set_fingerprint": "b" * 64,
    "corpus_snapshot_fingerprint": "c" * 64,
    "embedding_profile_fingerprint": "d" * 64,
}


def _metrics(**over) -> dict:
    base = {
        "sample_queries": 500,
        "corpus_documents": 250_000,
        "k": 10,
        **FINGERPRINTS,
        "retrieval_contract_version": "knowledge-hybrid-v2",
        "latency_scope": "end_to_end",
        "latency_observation_count": 500,
        "latency_observation_coverage": 1.0,
        "p95_latency_ms": 410.0,
        "p99_latency_ms": 720.0,
        "recall_at_k": 0.70,
        "ndcg_at_k": 0.68,
        "no_answer_or_filtered_query_ratio": 0.25,
        "no_answer_accuracy": 0.82,
        "abstention_precision": 0.83,
        "abstention_recall": 0.81,
        "exact_version_violation_rate": 0.0,
        "acl_violation_rate": 0.0,
        "family_duplicate_violation_rate": 0.0,
        "engine_contract_violation_rate": 0.0,
        "degradation_rate": 0.03,
    }
    base.update(over)
    return base


def _readiness(**over) -> dict:
    base = {
        "backup_automation_ready": True,
        "restore_drill_completed": True,
        "monitoring_alerting_ready": True,
        "capacity_plan_approved": True,
        "compose_topology_validated": True,
        "rollback_drill_completed": True,
    }
    base.update(over)
    return base


def _request(*, experiment: bool = True) -> dict:
    latest_metrics = _metrics()
    payload = {
        "schema_version": "qdrant-decision-v1",
        "policy": {},
        "pgvector_windows": [
            {
                "window_id": "w0",
                "started_at": "2026-06-21T00:00:00Z",
                "ended_at": "2026-06-28T00:00:00Z",
                "online_query_count": 10_000,
                "pgvector_tuning_completed": True,
                "metrics": _metrics(p95_latency_ms=405.0, p99_latency_ms=710.0),
            },
            {
                "window_id": "w1",
                "started_at": "2026-06-28T00:00:00Z",
                "ended_at": "2026-07-05T00:00:00Z",
                "online_query_count": 10_000,
                "pgvector_tuning_completed": True,
                "metrics": _metrics(p95_latency_ms=420.0, p99_latency_ms=730.0),
            },
            {
                "window_id": "w2",
                "started_at": "2026-07-05T00:00:00Z",
                "ended_at": "2026-07-12T00:00:00Z",
                "online_query_count": 10_000,
                "pgvector_tuning_completed": True,
                "metrics": latest_metrics,
            },
        ],
        "qdrant_experiment": None,
        "qdrant_operations_readiness": _readiness(),
    }
    if experiment:
        payload["qdrant_experiment"] = {
            "experiment_id": "experiment-1",
            "baseline_window_id": "w2",
            "online_shadow_query_count": 10_000,
            "baseline_pgvector": dict(latest_metrics),
            "candidate_qdrant": _metrics(
                p95_latency_ms=270.0,
                p99_latency_ms=500.0,
                recall_at_k=0.78,
                ndcg_at_k=0.72,
                no_answer_accuracy=0.93,
                abstention_precision=0.94,
                abstention_recall=0.92,
                degradation_rate=0.02,
            ),
            "p95_latency_p_value": 0.01,
            "p99_latency_p_value": 0.01,
            "quality_confidence_level": 0.95,
            "recall_difference_ci_lower": 0.02,
            "ndcg_difference_ci_lower": 0.01,
        }
    return payload


def _set(payload: dict, path: tuple, value) -> None:
    cursor = payload
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value


def test_only_all_hard_gates_recommend_qdrant() -> None:
    result = decide_qdrant(_request())
    assert result.status == "recommend_qdrant"
    assert result.recommend_qdrant is True
    assert result.reason_codes == ["QDRANT_GATE_PASSED"]
    assert result.evaluated_window_ids == ["w0", "w1", "w2"]
    assert result.p95_relative_improvement == pytest.approx(140 / 410)
    assert result.p99_relative_improvement == pytest.approx(220 / 720)
    assert result.recall_absolute_improvement == pytest.approx(0.08)


def test_continuous_failure_without_experiment_requests_shadow_test_only() -> None:
    result = decide_qdrant(_request(experiment=False))
    assert result.status == "run_qdrant_experiment"
    assert result.recommend_qdrant is False
    assert result.reason_codes == ["QDRANT_PAIRED_EXPERIMENT_REQUIRED"]


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("pgvector_windows", 1, "metrics", "corpus_documents"), 199_999,
         "PGVECTOR_SCALE_THRESHOLD_NOT_REACHED"),
        (("pgvector_windows", 1, "online_query_count"), 9_999,
         "PGVECTOR_ONLINE_TRAFFIC_INSUFFICIENT"),
        (("pgvector_windows", 1, "pgvector_tuning_completed"), False,
         "PGVECTOR_TUNING_NOT_COMPLETED"),
        (("pgvector_windows", 1, "metrics", "no_answer_or_filtered_query_ratio"), 0.19,
         "PGVECTOR_HARD_CASE_COVERAGE_INSUFFICIENT"),
        (("pgvector_windows", 1, "metrics", "acl_violation_rate"), 0.01,
         "PGVECTOR_SAFETY_GATE_VIOLATION"),
        (("pgvector_windows", 1, "metrics", "family_duplicate_violation_rate"), 0.01,
         "PGVECTOR_SAFETY_GATE_VIOLATION"),
        (("pgvector_windows", 1, "metrics", "engine_contract_violation_rate"), 0.01,
         "PGVECTOR_SAFETY_GATE_VIOLATION"),
    ],
)
def test_any_pgvector_prerequisite_missing_keeps_current_backend(
    path: tuple,
    value,
    reason: str,
) -> None:
    payload = _request()
    _set(payload, path, value)
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert result.recommend_qdrant is False
    assert reason in result.reason_codes


def test_window_with_latency_and_relevance_in_target_breaks_failure_streak() -> None:
    payload = _request()
    metrics = payload["pgvector_windows"][1]["metrics"]
    metrics.update(
        p95_latency_ms=290.0,
        p99_latency_ms=590.0,
        recall_at_k=0.80,
        ndcg_at_k=0.75,
    )

    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert "PGVECTOR_LATENCY_WITHIN_TARGET" in result.reason_codes
    assert "PGVECTOR_RELEVANCE_WITHIN_TARGET" in result.reason_codes


def test_window_latency_coverage_must_be_representative() -> None:
    payload = _request()
    metrics = payload["pgvector_windows"][1]["metrics"]
    metrics["latency_observation_count"] = 490
    metrics["latency_observation_coverage"] = 0.98
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert "PGVECTOR_LATENCY_COVERAGE_INSUFFICIENT" in result.reason_codes


def test_continuous_windows_must_keep_the_same_benchmark_contract() -> None:
    payload = _request()
    payload["pgvector_windows"][1]["metrics"]["query_set_fingerprint"] = "e" * 64
    with pytest.raises(ValidationError, match="same dataset, query set"):
        QdrantDecisionInput.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    [
        (("qdrant_experiment", "online_shadow_query_count"), 9_999,
         "QDRANT_ONLINE_SHADOW_TRAFFIC_INSUFFICIENT"),
        (("qdrant_experiment", "p95_latency_p_value"), 0.2,
         "QDRANT_P95_SIGNIFICANCE_NOT_MET"),
        (("qdrant_experiment", "candidate_qdrant", "p95_latency_ms"), 300.0,
         "QDRANT_P95_GAIN_INSUFFICIENT"),
        (("qdrant_experiment", "candidate_qdrant", "p99_latency_ms"), 550.0,
         "QDRANT_P99_GAIN_INSUFFICIENT"),
        (("qdrant_experiment", "candidate_qdrant", "recall_at_k"), 0.74,
         "QDRANT_TARGETS_NOT_MET"),
        (("qdrant_experiment", "candidate_qdrant", "acl_violation_rate"), 0.01,
         "QDRANT_SAFETY_REGRESSION"),
        (("qdrant_experiment", "candidate_qdrant", "engine_contract_violation_rate"), 0.01,
         "QDRANT_SAFETY_REGRESSION"),
        (
            (
                "qdrant_experiment",
                "candidate_qdrant",
                "family_duplicate_violation_rate",
            ),
            0.01,
            "QDRANT_FAMILY_DUPLICATE_VIOLATION",
        ),
        (("qdrant_experiment", "candidate_qdrant", "degradation_rate"), 0.04,
         "QDRANT_DEGRADATION_REGRESSION"),
    ],
)
def test_any_experiment_gate_failure_blocks_recommendation(
    path: tuple,
    value,
    reason: str,
) -> None:
    payload = _request()
    _set(payload, path, value)
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert result.recommend_qdrant is False
    assert reason in result.reason_codes


def test_qdrant_candidate_latency_coverage_must_be_representative() -> None:
    payload = _request()
    metrics = payload["qdrant_experiment"]["candidate_qdrant"]
    metrics["latency_observation_count"] = 490
    metrics["latency_observation_coverage"] = 0.98
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert "QDRANT_LATENCY_COVERAGE_INSUFFICIENT" in result.reason_codes


@pytest.mark.parametrize(
    ("metric", "value", "reason"),
    [
        ("no_answer_accuracy", 0.89, "QDRANT_TARGETS_NOT_MET"),
        ("abstention_precision", 0.89, "QDRANT_TARGETS_NOT_MET"),
        ("abstention_recall", 0.89, "QDRANT_TARGETS_NOT_MET"),
        ("no_answer_accuracy", 0.81, "QDRANT_NO_ANSWER_REGRESSION"),
        ("abstention_precision", 0.82, "QDRANT_NO_ANSWER_REGRESSION"),
        ("abstention_recall", 0.80, "QDRANT_NO_ANSWER_REGRESSION"),
    ],
)
def test_qdrant_no_answer_metrics_must_reach_target_without_regression(
    metric: str,
    value: float,
    reason: str,
) -> None:
    payload = _request()
    payload["qdrant_experiment"]["candidate_qdrant"][metric] = value
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert reason in result.reason_codes


def test_quality_non_inferiority_requires_confidence_lower_bounds() -> None:
    payload = _request()
    payload["qdrant_experiment"]["recall_difference_ci_lower"] = -0.02
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert "QDRANT_QUALITY_NON_INFERIORITY_NOT_ESTABLISHED" in result.reason_codes


@pytest.mark.parametrize(
    "field",
    [
        "backup_automation_ready",
        "restore_drill_completed",
        "monitoring_alerting_ready",
        "capacity_plan_approved",
        "compose_topology_validated",
        "rollback_drill_completed",
    ],
)
def test_every_operations_readiness_item_is_a_hard_gate(field: str) -> None:
    payload = _request()
    payload["qdrant_operations_readiness"][field] = False
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert "QDRANT_OPERATIONS_NOT_READY" in result.reason_codes


def test_missing_operations_readiness_never_recommends() -> None:
    payload = _request()
    payload["qdrant_operations_readiness"] = None
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert result.reason_codes == ["QDRANT_OPERATIONS_NOT_READY"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sample_queries", 501),
        ("corpus_documents", 250_001),
        ("k", 9),
        ("dataset_fingerprint", "e" * 64),
        ("query_set_fingerprint", "e" * 64),
        ("corpus_snapshot_fingerprint", "e" * 64),
        ("embedding_profile_fingerprint", "e" * 64),
        ("retrieval_contract_version", "knowledge-hybrid-v3"),
        ("no_answer_or_filtered_query_ratio", 0.26),
    ],
)
def test_paired_experiment_requires_identical_population_and_configuration(
    field: str,
    value,
) -> None:
    payload = _request()
    payload["qdrant_experiment"]["candidate_qdrant"][field] = value
    if field == "sample_queries":
        payload["qdrant_experiment"]["candidate_qdrant"][
            "latency_observation_count"
        ] = value
        payload["qdrant_experiment"]["candidate_qdrant"][
            "latency_observation_coverage"
        ] = 1.0
    with pytest.raises(ValidationError, match="paired experiment"):
        QdrantDecisionInput.model_validate(payload)


@pytest.mark.parametrize(
    "field",
    [
        "dataset_fingerprint",
        "query_set_fingerprint",
        "corpus_snapshot_fingerprint",
        "embedding_profile_fingerprint",
    ],
)
def test_fingerprints_are_safe_lowercase_sha256(field: str) -> None:
    payload = _request()
    payload["qdrant_experiment"]["candidate_qdrant"][field] = "unsafe value"
    with pytest.raises(ValidationError, match=field):
        QdrantDecisionInput.model_validate(payload)


def test_experiment_must_bind_exactly_to_latest_window_snapshot() -> None:
    payload = _request()
    payload["qdrant_experiment"]["baseline_window_id"] = "w1"
    with pytest.raises(ValidationError, match="latest pgvector window"):
        QdrantDecisionInput.model_validate(payload)

    payload = _request()
    payload["qdrant_experiment"]["baseline_pgvector"]["p95_latency_ms"] = 411.0
    with pytest.raises(ValidationError, match="exactly match"):
        QdrantDecisionInput.model_validate(payload)


def test_windows_must_be_continuous_and_have_positive_duration() -> None:
    payload = _request()
    payload["pgvector_windows"][1]["started_at"] = "2026-06-29T00:00:00Z"
    with pytest.raises(ValidationError, match="continuous"):
        QdrantDecisionInput.model_validate(payload)

    payload = _request()
    payload["pgvector_windows"][0]["ended_at"] = "2026-06-20T00:00:00Z"
    with pytest.raises(ValidationError, match="positive duration"):
        QdrantDecisionInput.model_validate(payload)


def test_p95_cannot_exceed_p99() -> None:
    payload = _request()
    payload["pgvector_windows"][0]["metrics"]["p95_latency_ms"] = 800.0
    with pytest.raises(ValidationError, match="p95_latency_ms"):
        QdrantDecisionInput.model_validate(payload)


def test_too_few_consecutive_windows_never_recommend() -> None:
    payload = _request()
    payload["pgvector_windows"] = payload["pgvector_windows"][:2]
    payload["qdrant_experiment"] = None
    result = decide_qdrant(payload)
    assert result.status == "keep_pgvector"
    assert result.reason_codes == ["PGVECTOR_CONSECUTIVE_WINDOWS_INSUFFICIENT"]


@pytest.mark.parametrize(
    "override",
    [
        {"min_scale_documents": 199_999},
        {"max_pgvector_p95_latency_ms": 301.0},
        {"max_pgvector_p99_latency_ms": 601.0},
        {"min_recall_at_k": 0.749},
        {"min_ndcg_at_k": 0.699},
        {"consecutive_failure_windows": 2},
        {"min_queries_per_window": 499},
        {"min_online_queries_per_window": 9_999},
        {"min_no_answer_or_filtered_ratio": 0.19},
        {"min_experiment_queries": 499},
        {"min_experiment_online_shadow_queries": 9_999},
        {"min_latency_observation_coverage": 0.98},
        {"min_no_answer_accuracy": 0.899},
        {"min_abstention_precision": 0.899},
        {"min_abstention_recall": 0.899},
        {"max_p_value": 0.051},
        {"min_quality_confidence_level": 0.949},
        {"min_p95_relative_improvement": 0.29},
        {"min_p99_relative_improvement": 0.24},
        {"max_quality_absolute_regression": 0.011},
    ],
)
def test_production_policy_defaults_cannot_be_weakened(override: dict) -> None:
    with pytest.raises(ValidationError):
        QdrantDecisionPolicy.model_validate(override)


def test_versioned_qdrant_example_passes_contract_and_gate() -> None:
    path = ROOT / "examples" / "retrieval_eval" / "qdrant_decision.json"
    request = QdrantDecisionInput.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )
    result = decide_qdrant(request)
    assert result.status == "recommend_qdrant"
    assert result.recommend_qdrant is True
