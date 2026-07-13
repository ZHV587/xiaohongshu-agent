"""统一检索离线评测的纯函数测试。"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_foundation.evidence import EvidenceItem, EvidencePackage, RetrievalFilters
from data_foundation.retrieval_eval import (
    RetrievalEvaluationDataset,
    RetrievalEvaluationResults,
    collect_retrieval_results,
    evaluate_retrieval_results,
)


ROOT = Path(__file__).resolve().parents[2]


def _judgment(
    resource_id: str,
    version: int,
    grade: int,
    *,
    allowed: bool = True,
    current: bool = True,
    family: str | None = None,
) -> dict:
    return {
        "resource_id": resource_id,
        "resource_version": version,
        "relevance_grade": grade,
        "acl_allowed": allowed,
        "current_version": current,
        "duplicate_family_id": family,
    }


def _dataset(judgments: list[dict], *, limit: int = 3) -> RetrievalEvaluationDataset:
    return RetrievalEvaluationDataset.model_validate(
        {
            "schema_version": "retrieval-eval-v1",
            "dataset_id": "dataset-1",
            "created_at": "2026-07-13T00:00:00Z",
            "cases": [
                {
                    "case_id": "case-1",
                    "tenant_id": "tenant-1",
                    "actor_open_id": "actor-1",
                    "query": "职场开头怎么写",
                    "limit": limit,
                    "filters": {"niches": ["职场"]},
                    "expected_engines": ["semantic", "keyword", "graph"],
                    "judgments": judgments,
                }
            ],
        }
    )


def _evidence(resource_id: str, version: int) -> EvidenceItem:
    return EvidenceItem(
        resource_id=resource_id,
        resource_version=version,
        type="generated_copy",
        asset_kind="copy",
        source_kind="user_adopted",
        niche="职场",
        title="标题",
        summary="摘要",
        source_updated_at="2026-07-10T00:00:00Z",
        indexed_at="2026-07-10T00:01:00Z",
        score=0.8,
        relevance=0.8,
        freshness=0.8,
        quality=0.8,
        performance=0.5,
        retrieval_sources=["semantic"],
        why_selected="语义命中",
    )


def _results(
    evidence: list[EvidenceItem],
    *,
    degraded: list[str] | None = None,
    latency_ms: float | None = 12.5,
    dataset_id: str = "dataset-1",
    case_id: str = "case-1",
) -> RetrievalEvaluationResults:
    insufficient = not evidence
    degraded_engines = ["keyword", "graph"] if degraded is None else degraded
    return RetrievalEvaluationResults.model_validate(
        {
            "schema_version": "retrieval-eval-results-v1",
            "dataset_id": dataset_id,
            "generated_at": "2026-07-13T00:01:00Z",
            "observations": [
                {
                    "case_id": case_id,
                    "latency_ms": latency_ms,
                    "result": {
                        "retrieval_mode": (
                            "insufficient_relevance" if insufficient else "semantic_only"
                        ),
                        "evidence": [item.model_dump(mode="json") for item in evidence],
                        "engines_used": ["semantic"],
                        "degraded_engines": [
                            {
                                "engine": engine,
                                "reason_code": f"{engine.upper()}_UNAVAILABLE",
                                "retryable": True,
                            }
                            for engine in degraded_engines
                        ],
                        "gaps": "合成标注期望无答案" if insufficient else None,
                    },
                }
            ],
        }
    )


def test_precision_recall_mrr_and_graded_ndcg_use_exact_identity() -> None:
    dataset = _dataset(
        [
            _judgment("a", 2, 3),
            _judgment("b", 1, 2),
            _judgment("c", 4, 0),
        ]
    )
    report = evaluate_retrieval_results(
        dataset,
        _results([_evidence("a", 2), _evidence("c", 4), _evidence("b", 1)]),
    )

    assert report.precision_at_k == pytest.approx(2 / 3)
    assert report.recall_at_k == 1.0
    assert report.mrr == 1.0
    expected_dcg = 7.0 + 3.0 / math.log2(4)
    ideal_dcg = 7.0 + 3.0 / math.log2(3)
    assert report.ndcg_at_k == pytest.approx(expected_dcg / ideal_dcg)
    assert report.latency_p50_ms == 12.5
    assert report.latency_p95_ms == 12.5
    assert report.latency_p99_ms == 12.5
    assert report.latency_observation_count == 1
    assert report.latency_observation_coverage == 1.0


def test_safety_and_family_violations_are_not_hidden_by_relevance_scores() -> None:
    dataset = _dataset(
        [
            _judgment("a", 1, 0, current=False),
            _judgment("a", 2, 3),
            _judgment("denied", 1, 0, allowed=False),
            _judgment("family-a", 1, 2, family="same-family"),
            _judgment("family-b", 1, 0, family="same-family"),
        ],
        limit=4,
    )
    results = _results(
        [
            _evidence("a", 1),
            _evidence("denied", 1),
            _evidence("family-a", 1),
            _evidence("family-b", 1),
        ],
        degraded=["keyword", "graph"],
    )

    report = evaluate_retrieval_results(dataset, results)
    assert report.exact_version_violation_count == 1
    assert report.exact_version_violation_rate == 0.25
    assert report.acl_violation_count == 1
    assert report.acl_violation_rate == 0.25
    assert report.family_duplicate_violation_count == 1
    assert report.family_duplicate_violation_rate == 0.25
    assert report.degradation_rate == pytest.approx(2 / 3)
    assert report.degraded_query_rate == 1.0
    assert report.hard_failure is True
    assert report.hard_failure_reasons == [
        "EXACT_VERSION_VIOLATION",
        "ACL_VIOLATION",
        "FAMILY_DUPLICATE_VIOLATION",
    ]


def test_duplicate_exact_identity_receives_relevance_credit_only_once() -> None:
    dataset = _dataset([_judgment("a", 1, 3)], limit=2)
    report = evaluate_retrieval_results(
        dataset,
        _results([_evidence("a", 1), _evidence("a", 1)]),
    )
    assert report.precision_at_k == 0.5
    assert report.family_duplicate_violation_count == 1
    assert report.hard_failure is True


def test_no_answer_case_scores_abstention_without_polluting_relevance_macro() -> None:
    dataset = _dataset(
        [_judgment("non-relevant", 1, 0)],
        limit=3,
    )
    report = evaluate_retrieval_results(dataset, _results([]))
    assert report.answerable_query_count == 0
    assert report.no_answer_query_count == 1
    assert report.precision_at_k is None
    assert report.recall_at_k is None
    assert report.mrr is None
    assert report.ndcg_at_k is None
    assert report.abstained_query_count == 1
    assert report.correct_abstention_count == 1
    assert report.false_abstention_count == 0
    assert report.abstention_precision == 1.0
    assert report.abstention_recall == 1.0
    assert report.no_answer_accuracy == 1.0
    assert report.hard_failure is False


def test_true_zero_candidate_no_answer_case_allows_empty_judgments() -> None:
    dataset = _dataset([], limit=3)
    report = evaluate_retrieval_results(dataset, _results([]))

    assert dataset.cases[0].judgments == []
    assert report.no_answer_query_count == 1
    assert report.no_answer_accuracy == 1.0
    assert report.total_returned == 0
    assert report.hard_failure is False


def test_unreported_expected_engine_is_a_contract_hard_failure() -> None:
    dataset = _dataset([_judgment("a", 1, 3)])
    report = evaluate_retrieval_results(
        dataset,
        _results([_evidence("a", 1)], degraded=[]),
    )

    assert report.engine_contract_violation_count == 1
    assert report.engine_contract_violation_rate == 1.0
    assert report.hard_failure is True
    assert report.hard_failure_reasons == ["ENGINE_CONTRACT_VIOLATION"]


def test_missing_latency_is_visible_in_observation_coverage() -> None:
    dataset = _dataset([_judgment("a", 1, 3)])
    report = evaluate_retrieval_results(
        dataset,
        _results([_evidence("a", 1)], latency_ms=None),
    )

    assert report.latency_observation_count == 0
    assert report.latency_observation_coverage == 0.0
    assert report.latency_p50_ms is None
    assert report.latency_p95_ms is None
    assert report.latency_p99_ms is None


def test_manifest_rejects_ambiguous_or_unreachable_relevant_judgments() -> None:
    base = {
        "schema_version": "retrieval-eval-v1",
        "dataset_id": "bad",
        "created_at": "2026-07-13T00:00:00Z",
        "cases": [
            {
                "case_id": "case",
                "tenant_id": "tenant",
                "actor_open_id": "actor",
                "query": "query",
                "judgments": [],
            }
        ],
    }
    base["cases"][0]["judgments"] = [
        _judgment("a", 1, 3, allowed=False),
    ]
    with pytest.raises(ValidationError, match="ACL-allowed"):
        RetrievalEvaluationDataset.model_validate(base)

    base["cases"][0]["judgments"] = [
        _judgment("a", 1, 3),
        _judgment("a", 1, 0),
    ]
    with pytest.raises(ValidationError, match="exact identities"):
        RetrievalEvaluationDataset.model_validate(base)


def test_dataset_and_observations_must_match_exactly() -> None:
    dataset = _dataset([_judgment("a", 1, 3)])
    with pytest.raises(ValueError, match="dataset_id"):
        evaluate_retrieval_results(
            dataset,
            _results([_evidence("a", 1)], dataset_id="other"),
        )
    with pytest.raises(ValueError, match="exactly match"):
        evaluate_retrieval_results(
            dataset,
            _results([_evidence("a", 1)], case_id="other"),
        )


def test_collect_results_calls_unified_retrieval_service_contract() -> None:
    dataset = _dataset([_judgment("a", 1, 3)])
    package = _results([_evidence("a", 1)]).observations[0].result

    class FakeService:
        calls: list[dict] = []

        def retrieve(self, **kwargs):
            self.calls.append(kwargs)
            return package

    service = FakeService()
    results = collect_retrieval_results(dataset, service)
    assert len(service.calls) == 1
    assert service.calls[0]["tenant_id"] == "tenant-1"
    assert service.calls[0]["actor_open_id"] == "actor-1"
    assert service.calls[0]["query"] == "职场开头怎么写"
    assert service.calls[0]["limit"] == 3
    assert service.calls[0]["filters"] == RetrievalFilters(niches=["职场"])
    assert results.observations[0].latency_ms is not None
    assert results.observations[0].result == package
    assert results.generated_at.tzinfo == timezone.utc


def test_versioned_examples_parse_and_evaluate() -> None:
    example_dir = ROOT / "examples" / "retrieval_eval"
    dataset = RetrievalEvaluationDataset.model_validate(
        json.loads((example_dir / "annotations.json").read_text(encoding="utf-8"))
    )
    results = RetrievalEvaluationResults.model_validate(
        json.loads((example_dir / "results.json").read_text(encoding="utf-8"))
    )
    report = evaluate_retrieval_results(dataset, results)
    assert report.dataset_id == dataset.dataset_id
    assert report.query_count == 2
    assert report.answerable_query_count == 1
    assert report.no_answer_query_count == 1
    assert report.no_answer_accuracy == 1.0
    assert report.exact_version_violation_count == 0
    assert report.acl_violation_count == 0
    assert report.engine_contract_violation_count == 0
    assert report.latency_observation_count == 2
    assert report.latency_observation_coverage == 1.0
    assert report.latency_p99_ms == 82.4
