"""统一知识检索的离线标注、回放与评测。

标注集以 ``(resource_id, resource_version)`` 为唯一身份，并显式记录当前版本、
ACL 与重复家族。这样离线分数不会掩盖线上最重要的三类错误：返回旧版本、越权
返回以及同一家族重复占位。生产运行可通过 :func:`collect_retrieval_results` 直接
调用 ``RetrievalService.retrieve``；日常回归则回放同一份 ``EvidencePackage`` JSON，
不依赖数据库或外部检索引擎。
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import math
from time import perf_counter
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_foundation.evidence import (
    EvidencePackage,
    RecallEngine,
    RetrievalFilters,
)


EVAL_DATASET_SCHEMA_VERSION = "retrieval-eval-v1"
EVAL_RESULTS_SCHEMA_VERSION = "retrieval-eval-results-v1"
EVAL_REPORT_SCHEMA_VERSION = "retrieval-eval-report-v1"

ExactIdentity = tuple[str, int]


class RetrievalServiceLike(Protocol):
    """``RetrievalService`` 的最小同步契约，便于注入确定性测试实现。"""

    def retrieve(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        query: str,
        limit: int,
        filters: RetrievalFilters,
    ) -> EvidencePackage: ...


class RetrievalJudgment(BaseModel):
    """一个候选精确版本在固定租户、用户和知识快照下的人工判断。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    resource_id: str = Field(min_length=1)
    resource_version: int = Field(gt=0, strict=True)
    relevance_grade: int = Field(ge=0, le=3, strict=True)
    acl_allowed: bool = Field(strict=True)
    current_version: bool = Field(strict=True)
    duplicate_family_id: str | None = None

    @field_validator("resource_id")
    @classmethod
    def _strip_resource_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("resource_id is required")
        return value

    @field_validator("duplicate_family_id")
    @classmethod
    def _strip_family(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @property
    def identity(self) -> ExactIdentity:
        return self.resource_id, self.resource_version


class RetrievalEvalCase(BaseModel):
    """单次检索的完整候选清单与相关性标注。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    actor_open_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    limit: int = Field(default=10, ge=1, le=20, strict=True)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    expected_engines: list[RecallEngine] = Field(
        default_factory=lambda: ["semantic", "keyword", "graph"],
        min_length=1,
        max_length=3,
    )
    judgments: list[RetrievalJudgment] = Field(default_factory=list)

    @field_validator("case_id", "tenant_id", "actor_open_id", "query")
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required text must not be blank")
        return value

    @model_validator(mode="after")
    def _validate_manifest(self) -> "RetrievalEvalCase":
        if len(self.expected_engines) != len(set(self.expected_engines)):
            raise ValueError("expected_engines must not contain duplicates")

        identities = [item.identity for item in self.judgments]
        if len(identities) != len(set(identities)):
            raise ValueError("judgment exact identities must be unique")

        current_by_resource: Counter[str] = Counter(
            item.resource_id for item in self.judgments if item.current_version
        )
        if any(count > 1 for count in current_by_resource.values()):
            raise ValueError("a resource may have at most one current version")

        relevant = [item for item in self.judgments if item.relevance_grade > 0]
        if any(not item.current_version or not item.acl_allowed for item in relevant):
            raise ValueError(
                "relevant judgments must be current and ACL-allowed for this actor"
            )
        return self


class RetrievalEvaluationDataset(BaseModel):
    """可版本控制的离线标注集。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["retrieval-eval-v1"] = EVAL_DATASET_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1)
    created_at: datetime
    cases: list[RetrievalEvalCase] = Field(min_length=1)

    @field_validator("created_at")
    @classmethod
    def _require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> "RetrievalEvaluationDataset":
        case_ids = [item.case_id for item in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case_id values must be unique")
        return self


class RetrievalObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    latency_ms: float | None = Field(default=None, ge=0.0)
    result: EvidencePackage


class RetrievalEvaluationResults(BaseModel):
    """由统一 ``RetrievalService`` 产出或从线上安全导出的回放结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["retrieval-eval-results-v1"] = EVAL_RESULTS_SCHEMA_VERSION
    dataset_id: str = Field(min_length=1)
    generated_at: datetime
    observations: list[RetrievalObservation] = Field(min_length=1)

    @field_validator("generated_at")
    @classmethod
    def _require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _unique_case_ids(self) -> "RetrievalEvaluationResults":
        case_ids = [item.case_id for item in self.observations]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("observation case_id values must be unique")
        return self


class QueryRetrievalMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    k: int
    returned_count: int
    relevant_count: int
    relevant_returned_count: int
    answerable: bool
    abstained: bool
    correct_abstention: bool
    precision_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    reciprocal_rank: float | None = Field(default=None, ge=0.0, le=1.0)
    ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_version_violation_count: int = Field(ge=0)
    acl_violation_count: int = Field(ge=0)
    family_duplicate_violation_count: int = Field(ge=0)
    degraded_engine_count: int = Field(ge=0)
    expected_engine_count: int = Field(gt=0)
    engine_contract_violation: bool
    retrieval_mode: str
    latency_ms: float | None = Field(default=None, ge=0.0)


class RetrievalEvaluationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["retrieval-eval-report-v1"] = EVAL_REPORT_SCHEMA_VERSION
    dataset_id: str
    query_count: int = Field(gt=0)
    answerable_query_count: int = Field(ge=0)
    no_answer_query_count: int = Field(ge=0)
    k_values: list[int]
    precision_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    recall_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    mrr: float | None = Field(default=None, ge=0.0, le=1.0)
    ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    abstained_query_count: int = Field(ge=0)
    correct_abstention_count: int = Field(ge=0)
    false_abstention_count: int = Field(ge=0)
    abstention_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    abstention_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    no_answer_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    total_returned: int = Field(ge=0)
    exact_version_violation_count: int = Field(ge=0)
    exact_version_violation_rate: float = Field(ge=0.0, le=1.0)
    acl_violation_count: int = Field(ge=0)
    acl_violation_rate: float = Field(ge=0.0, le=1.0)
    family_duplicate_violation_count: int = Field(ge=0)
    family_duplicate_violation_rate: float = Field(ge=0.0, le=1.0)
    degradation_rate: float = Field(ge=0.0, le=1.0)
    degraded_query_rate: float = Field(ge=0.0, le=1.0)
    engine_contract_violation_count: int = Field(ge=0)
    engine_contract_violation_rate: float = Field(ge=0.0, le=1.0)
    hard_failure: bool
    hard_failure_reasons: list[str]
    latency_observation_count: int = Field(ge=0)
    latency_observation_coverage: float = Field(ge=0.0, le=1.0)
    latency_p50_ms: float | None = Field(default=None, ge=0.0)
    latency_p95_ms: float | None = Field(default=None, ge=0.0)
    latency_p99_ms: float | None = Field(default=None, ge=0.0)
    retrieval_mode_counts: dict[str, int]

    @model_validator(mode="after")
    def _validate_latency_percentiles(self) -> "RetrievalEvaluationReport":
        percentiles = [
            value
            for value in (
                self.latency_p50_ms,
                self.latency_p95_ms,
                self.latency_p99_ms,
            )
            if value is not None
        ]
        if percentiles != sorted(percentiles):
            raise ValueError("latency percentiles must be monotonic")
        return self


def _dcg(grades: list[int]) -> float:
    return sum(
        (2**grade - 1) / math.log2(rank + 2)
        for rank, grade in enumerate(grades)
    )


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _evaluate_case(
    case: RetrievalEvalCase,
    observation: RetrievalObservation,
) -> QueryRetrievalMetrics:
    judgments = {item.identity: item for item in case.judgments}
    current_identity_by_resource = {
        item.resource_id: item.identity
        for item in case.judgments
        if item.current_version
    }
    relevant = {
        identity: item.relevance_grade
        for identity, item in judgments.items()
        if item.relevance_grade > 0 and item.current_version and item.acl_allowed
    }

    ranked = list(observation.result.evidence[: case.limit])
    credited: set[ExactIdentity] = set()
    ranked_grades: list[int] = []
    for evidence in ranked:
        identity = evidence.resource_id, evidence.resource_version
        grade = relevant.get(identity, 0)
        if identity in credited:
            grade = 0
        elif grade > 0:
            credited.add(identity)
        ranked_grades.append(grade)

    relevant_returned = len(credited)
    answerable = bool(relevant)
    abstained = observation.result.retrieval_mode == "insufficient_relevance"
    correct_abstention = not answerable and abstained
    if answerable:
        precision: float | None = relevant_returned / case.limit
        recall: float | None = relevant_returned / len(relevant)
        reciprocal_rank: float | None = next(
            (
                1.0 / rank
                for rank, grade in enumerate(ranked_grades, start=1)
                if grade > 0
            ),
            0.0,
        )
        ideal_grades = sorted(relevant.values(), reverse=True)[: case.limit]
        ndcg: float | None = _dcg(ranked_grades) / _dcg(ideal_grades)
    else:
        # 无答案 case 的正确行为是拒答，不能用人为的 0/1 相关性分数污染宏平均。
        precision = recall = reciprocal_rank = ndcg = None

    exact_version_violations = 0
    acl_violations = 0
    family_counts: Counter[str] = Counter()
    for evidence in observation.result.evidence:
        identity = evidence.resource_id, evidence.resource_version
        judgment = judgments.get(identity)
        if current_identity_by_resource.get(evidence.resource_id) != identity:
            exact_version_violations += 1
        if judgment is None or not judgment.acl_allowed:
            acl_violations += 1
        family = (
            judgment.duplicate_family_id
            if judgment is not None and judgment.duplicate_family_id
            else f"exact:{evidence.resource_id}:{evidence.resource_version}"
        )
        family_counts[family] += 1
    family_duplicate_violations = sum(
        max(count - 1, 0) for count in family_counts.values()
    )

    expected_engines = set(case.expected_engines)
    used_engines = set(observation.result.engines_used)
    reported_degraded_engines = {
        item.engine for item in observation.result.degraded_engines
    }
    degraded = {
        engine
        for engine in reported_degraded_engines
        if engine in expected_engines
    }
    engine_contract_violation = (
        expected_engines != used_engines | reported_degraded_engines
    )
    return QueryRetrievalMetrics(
        case_id=case.case_id,
        k=case.limit,
        returned_count=len(observation.result.evidence),
        relevant_count=len(relevant),
        relevant_returned_count=relevant_returned,
        answerable=answerable,
        abstained=abstained,
        correct_abstention=correct_abstention,
        precision_at_k=precision,
        recall_at_k=recall,
        reciprocal_rank=reciprocal_rank,
        ndcg_at_k=ndcg,
        exact_version_violation_count=exact_version_violations,
        acl_violation_count=acl_violations,
        family_duplicate_violation_count=family_duplicate_violations,
        degraded_engine_count=len(degraded),
        expected_engine_count=len(expected_engines),
        engine_contract_violation=engine_contract_violation,
        retrieval_mode=observation.result.retrieval_mode,
        latency_ms=observation.latency_ms,
    )


def evaluate_retrieval_results(
    dataset: RetrievalEvaluationDataset | dict[str, Any],
    results: RetrievalEvaluationResults | dict[str, Any],
) -> RetrievalEvaluationReport:
    """严格匹配标注集与结果集并计算宏平均检索指标。"""

    annotations = (
        dataset
        if isinstance(dataset, RetrievalEvaluationDataset)
        else RetrievalEvaluationDataset.model_validate(dataset)
    )
    observations = (
        results
        if isinstance(results, RetrievalEvaluationResults)
        else RetrievalEvaluationResults.model_validate(results)
    )
    if observations.dataset_id != annotations.dataset_id:
        raise ValueError("result dataset_id does not match annotations")

    case_by_id = {item.case_id: item for item in annotations.cases}
    result_by_id = {item.case_id: item for item in observations.observations}
    if set(case_by_id) != set(result_by_id):
        missing = sorted(set(case_by_id) - set(result_by_id))
        unexpected = sorted(set(result_by_id) - set(case_by_id))
        raise ValueError(
            f"result cases must exactly match annotations; missing={missing}, "
            f"unexpected={unexpected}"
        )

    queries = [
        _evaluate_case(case, result_by_id[case.case_id])
        for case in annotations.cases
    ]
    query_count = len(queries)
    answerable_queries = [item for item in queries if item.answerable]
    no_answer_queries = [item for item in queries if not item.answerable]
    abstained_queries = [item for item in queries if item.abstained]
    correct_abstentions = [item for item in queries if item.correct_abstention]
    false_abstentions = [
        item for item in queries if item.answerable and item.abstained
    ]
    total_returned = sum(item.returned_count for item in queries)
    denominator = max(total_returned, 1)
    exact_violations = sum(item.exact_version_violation_count for item in queries)
    acl_violations = sum(item.acl_violation_count for item in queries)
    family_violations = sum(
        item.family_duplicate_violation_count for item in queries
    )
    degraded_engines = sum(item.degraded_engine_count for item in queries)
    expected_engines = sum(item.expected_engine_count for item in queries)
    engine_contract_violations = sum(
        item.engine_contract_violation for item in queries
    )
    latencies = [item.latency_ms for item in queries if item.latency_ms is not None]
    hard_failure_reasons: list[str] = []
    if exact_violations:
        hard_failure_reasons.append("EXACT_VERSION_VIOLATION")
    if acl_violations:
        hard_failure_reasons.append("ACL_VIOLATION")
    if family_violations:
        hard_failure_reasons.append("FAMILY_DUPLICATE_VIOLATION")
    if engine_contract_violations:
        hard_failure_reasons.append("ENGINE_CONTRACT_VIOLATION")

    def mean_metric(name: str) -> float | None:
        values = [getattr(item, name) for item in answerable_queries]
        return sum(values) / len(values) if values else None

    return RetrievalEvaluationReport(
        dataset_id=annotations.dataset_id,
        query_count=query_count,
        answerable_query_count=len(answerable_queries),
        no_answer_query_count=len(no_answer_queries),
        k_values=sorted({item.k for item in queries}),
        precision_at_k=mean_metric("precision_at_k"),
        recall_at_k=mean_metric("recall_at_k"),
        mrr=mean_metric("reciprocal_rank"),
        ndcg_at_k=mean_metric("ndcg_at_k"),
        abstained_query_count=len(abstained_queries),
        correct_abstention_count=len(correct_abstentions),
        false_abstention_count=len(false_abstentions),
        abstention_precision=(
            len(correct_abstentions) / len(abstained_queries)
            if abstained_queries
            else None
        ),
        abstention_recall=(
            len(correct_abstentions) / len(no_answer_queries)
            if no_answer_queries
            else None
        ),
        no_answer_accuracy=(
            len(correct_abstentions) / len(no_answer_queries)
            if no_answer_queries
            else None
        ),
        total_returned=total_returned,
        exact_version_violation_count=exact_violations,
        exact_version_violation_rate=exact_violations / denominator,
        acl_violation_count=acl_violations,
        acl_violation_rate=acl_violations / denominator,
        family_duplicate_violation_count=family_violations,
        family_duplicate_violation_rate=family_violations / denominator,
        degradation_rate=degraded_engines / expected_engines,
        degraded_query_rate=(
            sum(item.degraded_engine_count > 0 for item in queries) / query_count
        ),
        engine_contract_violation_count=engine_contract_violations,
        engine_contract_violation_rate=engine_contract_violations / query_count,
        hard_failure=bool(hard_failure_reasons),
        hard_failure_reasons=hard_failure_reasons,
        latency_observation_count=len(latencies),
        latency_observation_coverage=len(latencies) / query_count,
        latency_p50_ms=_percentile(latencies, 0.50),
        latency_p95_ms=_percentile(latencies, 0.95),
        latency_p99_ms=_percentile(latencies, 0.99),
        retrieval_mode_counts=dict(
            sorted(Counter(item.retrieval_mode for item in queries).items())
        ),
    )


def collect_retrieval_results(
    dataset: RetrievalEvaluationDataset | dict[str, Any],
    service: RetrievalServiceLike,
) -> RetrievalEvaluationResults:
    """用统一 ``RetrievalService`` 执行标注集并保留可回放结果。"""

    annotations = (
        dataset
        if isinstance(dataset, RetrievalEvaluationDataset)
        else RetrievalEvaluationDataset.model_validate(dataset)
    )
    observations: list[RetrievalObservation] = []
    for case in annotations.cases:
        started = perf_counter()
        package = service.retrieve(
            tenant_id=case.tenant_id,
            actor_open_id=case.actor_open_id,
            query=case.query,
            limit=case.limit,
            filters=case.filters,
        )
        latency_ms = (perf_counter() - started) * 1000
        observations.append(
            RetrievalObservation(
                case_id=case.case_id,
                latency_ms=latency_ms,
                result=package,
            )
        )
    return RetrievalEvaluationResults(
        dataset_id=annotations.dataset_id,
        generated_at=datetime.now(timezone.utc),
        observations=observations,
    )


__all__ = [
    "EVAL_DATASET_SCHEMA_VERSION",
    "EVAL_REPORT_SCHEMA_VERSION",
    "EVAL_RESULTS_SCHEMA_VERSION",
    "QueryRetrievalMetrics",
    "RetrievalEvalCase",
    "RetrievalEvaluationDataset",
    "RetrievalEvaluationReport",
    "RetrievalEvaluationResults",
    "RetrievalJudgment",
    "RetrievalObservation",
    "collect_retrieval_results",
    "evaluate_retrieval_results",
]
