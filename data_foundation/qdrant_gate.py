"""是否值得引入 Qdrant 的离线量化决策门。

本模块只读取基准数据，不导入 Qdrant、不创建客户端，也不改变生产检索路径。
只有 pgvector 在足够规模下连续多个完整窗口同时错过延迟和相关性目标，并且绑定
最后一个窗口的 Qdrant 配对影子实验通过质量、安全、统计和运维硬门，才会返回
``recommend_qdrant=True``。
"""
from __future__ import annotations

from datetime import datetime, timezone
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


QDRANT_GATE_SCHEMA_VERSION = "qdrant-decision-v1"
QDRANT_DECISION_SCHEMA_VERSION = "qdrant-decision-result-v1"

_FINGERPRINT_PATTERN = r"^[0-9a-f]{64}$"
_SAFE_TOKEN_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$"
_SAFE_VERSION_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,63}$"


class RetrievalBenchmarkMetrics(BaseModel):
    """一个固定数据集、查询集、语料和检索配置上的聚合指标。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_queries: int = Field(gt=0, strict=True)
    corpus_documents: int = Field(gt=0, strict=True)
    k: int = Field(ge=1, le=20, strict=True)
    dataset_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN, strict=True)
    query_set_fingerprint: str = Field(pattern=_FINGERPRINT_PATTERN, strict=True)
    corpus_snapshot_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN,
        strict=True,
    )
    embedding_profile_fingerprint: str = Field(
        pattern=_FINGERPRINT_PATTERN,
        strict=True,
    )
    retrieval_contract_version: str = Field(
        pattern=_SAFE_VERSION_PATTERN,
        strict=True,
    )
    latency_scope: Literal["end_to_end"] = "end_to_end"
    latency_observation_count: int = Field(ge=0, strict=True)
    latency_observation_coverage: float = Field(ge=0.0, le=1.0)
    p95_latency_ms: float = Field(gt=0.0)
    p99_latency_ms: float = Field(gt=0.0)
    recall_at_k: float = Field(ge=0.0, le=1.0)
    ndcg_at_k: float = Field(ge=0.0, le=1.0)
    no_answer_or_filtered_query_ratio: float = Field(ge=0.0, le=1.0)
    no_answer_accuracy: float = Field(ge=0.0, le=1.0)
    abstention_precision: float = Field(ge=0.0, le=1.0)
    abstention_recall: float = Field(ge=0.0, le=1.0)
    exact_version_violation_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    acl_violation_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    family_duplicate_violation_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    engine_contract_violation_rate: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    degradation_rate: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _validate_latency_order(self) -> "RetrievalBenchmarkMetrics":
        if self.latency_observation_count > self.sample_queries:
            raise ValueError(
                "latency_observation_count cannot exceed sample_queries"
            )
        observed_coverage = self.latency_observation_count / self.sample_queries
        if not math.isclose(
            self.latency_observation_coverage,
            observed_coverage,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError(
                "latency_observation_coverage must match the observed sample count"
            )
        if self.p95_latency_ms > self.p99_latency_ms:
            raise ValueError(
                "p95_latency_ms must be less than or equal to p99_latency_ms"
            )
        return self


class PgVectorBenchmarkWindow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_id: str = Field(pattern=_SAFE_TOKEN_PATTERN, strict=True)
    started_at: datetime
    ended_at: datetime
    online_query_count: int = Field(ge=0, strict=True)
    pgvector_tuning_completed: bool = Field(strict=True)
    metrics: RetrievalBenchmarkMetrics

    @field_validator("started_at", "ended_at")
    @classmethod
    def _require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("benchmark window timestamps must include a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def _require_positive_window(self) -> "PgVectorBenchmarkWindow":
        if self.started_at >= self.ended_at:
            raise ValueError("benchmark window must have positive duration")
        return self


class QdrantPairedExperiment(BaseModel):
    """同语料、同查询配对实验；统计量由逐查询样本计算。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: str = Field(pattern=_SAFE_TOKEN_PATTERN, strict=True)
    baseline_window_id: str = Field(pattern=_SAFE_TOKEN_PATTERN, strict=True)
    online_shadow_query_count: int = Field(ge=0, strict=True)
    baseline_pgvector: RetrievalBenchmarkMetrics
    candidate_qdrant: RetrievalBenchmarkMetrics
    p95_latency_p_value: float = Field(ge=0.0, le=1.0)
    p99_latency_p_value: float = Field(ge=0.0, le=1.0)
    quality_confidence_level: float = Field(gt=0.0, lt=1.0)
    recall_difference_ci_lower: float = Field(ge=-1.0, le=1.0)
    ndcg_difference_ci_lower: float = Field(ge=-1.0, le=1.0)

    @model_validator(mode="after")
    def _require_paired_population(self) -> "QdrantPairedExperiment":
        baseline = self.baseline_pgvector
        candidate = self.candidate_qdrant
        paired_fields = (
            "sample_queries",
            "corpus_documents",
            "k",
            "dataset_fingerprint",
            "query_set_fingerprint",
            "corpus_snapshot_fingerprint",
            "embedding_profile_fingerprint",
            "retrieval_contract_version",
            "latency_scope",
            "no_answer_or_filtered_query_ratio",
        )
        if any(
            getattr(baseline, field) != getattr(candidate, field)
            for field in paired_fields
        ):
            raise ValueError(
                "paired experiment must use the same dataset, query set, corpus, "
                "embedding profile, retrieval contract and K"
            )
        recall_gain = candidate.recall_at_k - baseline.recall_at_k
        ndcg_gain = candidate.ndcg_at_k - baseline.ndcg_at_k
        if self.recall_difference_ci_lower > recall_gain:
            raise ValueError(
                "recall confidence lower bound cannot exceed point estimate"
            )
        if self.ndcg_difference_ci_lower > ndcg_gain:
            raise ValueError("nDCG confidence lower bound cannot exceed point estimate")
        return self


class QdrantOperationsReadiness(BaseModel):
    """采用新向量库前必须逐项完成的生产运维准备。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    backup_automation_ready: bool = Field(strict=True)
    restore_drill_completed: bool = Field(strict=True)
    monitoring_alerting_ready: bool = Field(strict=True)
    capacity_plan_approved: bool = Field(strict=True)
    compose_topology_validated: bool = Field(strict=True)
    rollback_drill_completed: bool = Field(strict=True)

    @property
    def all_ready(self) -> bool:
        return all(
            (
                self.backup_automation_ready,
                self.restore_drill_completed,
                self.monitoring_alerting_ready,
                self.capacity_plan_approved,
                self.compose_topology_validated,
                self.rollback_drill_completed,
            )
        )


class QdrantDecisionPolicy(BaseModel):
    """不可放宽的生产下限；调用方只能提供相同或更严格的门槛。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_scale_documents: int = Field(default=200_000, ge=200_000, strict=True)
    max_pgvector_p95_latency_ms: float = Field(default=300.0, gt=0.0, le=300.0)
    max_pgvector_p99_latency_ms: float = Field(default=600.0, gt=0.0, le=600.0)
    min_recall_at_k: float = Field(default=0.75, ge=0.75, le=1.0)
    min_ndcg_at_k: float = Field(default=0.70, ge=0.70, le=1.0)
    consecutive_failure_windows: int = Field(default=3, ge=3, le=12, strict=True)
    min_queries_per_window: int = Field(default=500, ge=500, strict=True)
    min_online_queries_per_window: int = Field(
        default=10_000,
        ge=10_000,
        strict=True,
    )
    min_no_answer_or_filtered_ratio: float = Field(default=0.20, ge=0.20, le=1.0)
    min_experiment_queries: int = Field(default=500, ge=500, strict=True)
    min_experiment_online_shadow_queries: int = Field(
        default=10_000,
        ge=10_000,
        strict=True,
    )
    min_latency_observation_coverage: float = Field(
        default=0.99,
        ge=0.99,
        le=1.0,
    )
    min_no_answer_accuracy: float = Field(default=0.90, ge=0.90, le=1.0)
    min_abstention_precision: float = Field(default=0.90, ge=0.90, le=1.0)
    min_abstention_recall: float = Field(default=0.90, ge=0.90, le=1.0)
    max_p_value: float = Field(default=0.05, gt=0.0, le=0.05)
    min_quality_confidence_level: float = Field(default=0.95, ge=0.95, lt=1.0)
    min_p95_relative_improvement: float = Field(default=0.30, ge=0.30, le=1.0)
    min_p99_relative_improvement: float = Field(default=0.25, ge=0.25, le=1.0)
    max_quality_absolute_regression: float = Field(
        default=0.01,
        ge=0.0,
        le=0.01,
    )


class QdrantDecisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["qdrant-decision-v1"] = QDRANT_GATE_SCHEMA_VERSION
    policy: QdrantDecisionPolicy = Field(default_factory=QdrantDecisionPolicy)
    pgvector_windows: list[PgVectorBenchmarkWindow] = Field(min_length=1)
    qdrant_experiment: QdrantPairedExperiment | None = None
    qdrant_operations_readiness: QdrantOperationsReadiness | None = None

    @model_validator(mode="after")
    def _validate_window_and_experiment_binding(self) -> "QdrantDecisionInput":
        ids = [item.window_id for item in self.pgvector_windows]
        if len(ids) != len(set(ids)):
            raise ValueError("window_id values must be unique")

        for previous, current in zip(
            self.pgvector_windows,
            self.pgvector_windows[1:],
            strict=False,
        ):
            if previous.ended_at != current.started_at:
                raise ValueError(
                    "pgvector_windows must be chronological and continuous without gaps"
                )
            if (
                current.ended_at - current.started_at
                != previous.ended_at - previous.started_at
            ):
                raise ValueError("pgvector benchmark windows must have equal duration")

        comparable_fields = (
            "k",
            "dataset_fingerprint",
            "query_set_fingerprint",
            "embedding_profile_fingerprint",
            "retrieval_contract_version",
        )
        first_metrics = self.pgvector_windows[0].metrics
        if any(
            getattr(window.metrics, field) != getattr(first_metrics, field)
            for window in self.pgvector_windows[1:]
            for field in comparable_fields
        ):
            raise ValueError(
                "pgvector windows must use the same dataset, query set, embedding "
                "profile, retrieval contract and K"
            )

        experiment = self.qdrant_experiment
        if experiment is not None:
            latest = self.pgvector_windows[-1]
            if experiment.baseline_window_id != latest.window_id:
                raise ValueError(
                    "qdrant experiment must bind to the latest pgvector window"
                )
            if experiment.baseline_pgvector != latest.metrics:
                raise ValueError(
                    "qdrant experiment baseline must exactly match the latest "
                    "pgvector metrics snapshot"
                )
        return self


QdrantDecisionStatus = Literal[
    "keep_pgvector",
    "run_qdrant_experiment",
    "recommend_qdrant",
]


class QdrantDecisionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["qdrant-decision-result-v1"] = (
        QDRANT_DECISION_SCHEMA_VERSION
    )
    status: QdrantDecisionStatus
    recommend_qdrant: bool
    reason_codes: list[str] = Field(min_length=1)
    evaluated_window_ids: list[str]
    p95_relative_improvement: float | None = None
    p99_relative_improvement: float | None = None
    recall_absolute_improvement: float | None = None
    ndcg_absolute_improvement: float | None = None

    @model_validator(mode="after")
    def _recommendation_matches_status(self) -> "QdrantDecisionResult":
        if self.recommend_qdrant != (self.status == "recommend_qdrant"):
            raise ValueError("recommend_qdrant must match status")
        return self


def _pg_window_failure_reasons(
    window: PgVectorBenchmarkWindow,
    policy: QdrantDecisionPolicy,
) -> list[str]:
    metrics = window.metrics
    reasons: list[str] = []
    if metrics.sample_queries < policy.min_queries_per_window:
        reasons.append("PGVECTOR_WINDOW_SAMPLE_TOO_SMALL")
    if (
        metrics.latency_observation_coverage
        < policy.min_latency_observation_coverage
    ):
        reasons.append("PGVECTOR_LATENCY_COVERAGE_INSUFFICIENT")
    if window.online_query_count < policy.min_online_queries_per_window:
        reasons.append("PGVECTOR_ONLINE_TRAFFIC_INSUFFICIENT")
    if not window.pgvector_tuning_completed:
        reasons.append("PGVECTOR_TUNING_NOT_COMPLETED")
    if (
        metrics.no_answer_or_filtered_query_ratio
        < policy.min_no_answer_or_filtered_ratio
    ):
        reasons.append("PGVECTOR_HARD_CASE_COVERAGE_INSUFFICIENT")
    if metrics.corpus_documents < policy.min_scale_documents:
        reasons.append("PGVECTOR_SCALE_THRESHOLD_NOT_REACHED")
    if (
        metrics.p95_latency_ms <= policy.max_pgvector_p95_latency_ms
        and metrics.p99_latency_ms <= policy.max_pgvector_p99_latency_ms
    ):
        reasons.append("PGVECTOR_LATENCY_WITHIN_TARGET")
    relevance_failed = (
        metrics.recall_at_k < policy.min_recall_at_k
        or metrics.ndcg_at_k < policy.min_ndcg_at_k
    )
    if not relevance_failed:
        reasons.append("PGVECTOR_RELEVANCE_WITHIN_TARGET")
    if (
        metrics.exact_version_violation_rate > 0
        or metrics.acl_violation_rate > 0
        or metrics.family_duplicate_violation_rate > 0
        or metrics.engine_contract_violation_rate > 0
    ):
        # 版本/ACL 是 PostgreSQL 资格门问题，更换向量数据库不能修复。
        reasons.append("PGVECTOR_SAFETY_GATE_VIOLATION")
    return reasons


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def decide_qdrant(
    decision_input: QdrantDecisionInput | dict,
) -> QdrantDecisionResult:
    """执行保守决策门；任何条件缺失都不会建议改动生产架构。"""

    request = (
        decision_input
        if isinstance(decision_input, QdrantDecisionInput)
        else QdrantDecisionInput.model_validate(decision_input)
    )
    policy = request.policy
    required = policy.consecutive_failure_windows
    if len(request.pgvector_windows) < required:
        return QdrantDecisionResult(
            status="keep_pgvector",
            recommend_qdrant=False,
            reason_codes=["PGVECTOR_CONSECUTIVE_WINDOWS_INSUFFICIENT"],
            evaluated_window_ids=[item.window_id for item in request.pgvector_windows],
        )

    tail = request.pgvector_windows[-required:]
    window_ids = [item.window_id for item in tail]
    failure_reasons = [
        reason
        for window in tail
        for reason in _pg_window_failure_reasons(window, policy)
    ]
    if failure_reasons:
        return QdrantDecisionResult(
            status="keep_pgvector",
            recommend_qdrant=False,
            reason_codes=_unique(failure_reasons),
            evaluated_window_ids=window_ids,
        )

    experiment = request.qdrant_experiment
    if experiment is None:
        return QdrantDecisionResult(
            status="run_qdrant_experiment",
            recommend_qdrant=False,
            reason_codes=["QDRANT_PAIRED_EXPERIMENT_REQUIRED"],
            evaluated_window_ids=window_ids,
        )

    baseline = experiment.baseline_pgvector
    candidate = experiment.candidate_qdrant
    p95_gain = (baseline.p95_latency_ms - candidate.p95_latency_ms) / max(
        baseline.p95_latency_ms,
        1e-12,
    )
    p99_gain = (baseline.p99_latency_ms - candidate.p99_latency_ms) / max(
        baseline.p99_latency_ms,
        1e-12,
    )
    recall_gain = candidate.recall_at_k - baseline.recall_at_k
    ndcg_gain = candidate.ndcg_at_k - baseline.ndcg_at_k

    experiment_reasons: list[str] = []
    if baseline.sample_queries < policy.min_experiment_queries:
        experiment_reasons.append("QDRANT_EXPERIMENT_SAMPLE_TOO_SMALL")
    if (
        baseline.latency_observation_coverage
        < policy.min_latency_observation_coverage
        or candidate.latency_observation_coverage
        < policy.min_latency_observation_coverage
    ):
        experiment_reasons.append("QDRANT_LATENCY_COVERAGE_INSUFFICIENT")
    if (
        experiment.online_shadow_query_count
        < policy.min_experiment_online_shadow_queries
    ):
        experiment_reasons.append("QDRANT_ONLINE_SHADOW_TRAFFIC_INSUFFICIENT")
    if baseline.corpus_documents < policy.min_scale_documents:
        experiment_reasons.append("QDRANT_EXPERIMENT_SCALE_NOT_COMPARABLE")
    if (
        baseline.exact_version_violation_rate > 0
        or baseline.acl_violation_rate > 0
        or baseline.family_duplicate_violation_rate > 0
        or baseline.engine_contract_violation_rate > 0
    ):
        experiment_reasons.append("QDRANT_BASELINE_SAFETY_GATE_VIOLATION")
    if (
        baseline.no_answer_or_filtered_query_ratio
        < policy.min_no_answer_or_filtered_ratio
    ):
        experiment_reasons.append("QDRANT_HARD_CASE_COVERAGE_INSUFFICIENT")

    baseline_latency_failed = (
        baseline.p95_latency_ms > policy.max_pgvector_p95_latency_ms
        or baseline.p99_latency_ms > policy.max_pgvector_p99_latency_ms
    )
    baseline_relevance_failed = (
        baseline.recall_at_k < policy.min_recall_at_k
        or baseline.ndcg_at_k < policy.min_ndcg_at_k
    )
    if not baseline_latency_failed or not baseline_relevance_failed:
        experiment_reasons.append("QDRANT_BASELINE_DOES_NOT_REPRODUCE_FAILURE")
    if p95_gain < policy.min_p95_relative_improvement:
        experiment_reasons.append("QDRANT_P95_GAIN_INSUFFICIENT")
    if p99_gain < policy.min_p99_relative_improvement:
        experiment_reasons.append("QDRANT_P99_GAIN_INSUFFICIENT")
    if experiment.p95_latency_p_value > policy.max_p_value:
        experiment_reasons.append("QDRANT_P95_SIGNIFICANCE_NOT_MET")
    if experiment.p99_latency_p_value > policy.max_p_value:
        experiment_reasons.append("QDRANT_P99_SIGNIFICANCE_NOT_MET")

    if (
        candidate.p95_latency_ms > policy.max_pgvector_p95_latency_ms
        or candidate.p99_latency_ms > policy.max_pgvector_p99_latency_ms
        or candidate.recall_at_k < policy.min_recall_at_k
        or candidate.ndcg_at_k < policy.min_ndcg_at_k
        or candidate.no_answer_accuracy < policy.min_no_answer_accuracy
        or candidate.abstention_precision < policy.min_abstention_precision
        or candidate.abstention_recall < policy.min_abstention_recall
    ):
        experiment_reasons.append("QDRANT_TARGETS_NOT_MET")
    if (
        recall_gain < -policy.max_quality_absolute_regression
        or ndcg_gain < -policy.max_quality_absolute_regression
    ):
        experiment_reasons.append("QDRANT_QUALITY_REGRESSION")
    if (
        experiment.quality_confidence_level < policy.min_quality_confidence_level
        or experiment.recall_difference_ci_lower
        < -policy.max_quality_absolute_regression
        or experiment.ndcg_difference_ci_lower
        < -policy.max_quality_absolute_regression
    ):
        experiment_reasons.append("QDRANT_QUALITY_NON_INFERIORITY_NOT_ESTABLISHED")
    if (
        candidate.no_answer_accuracy < baseline.no_answer_accuracy
        or candidate.abstention_precision < baseline.abstention_precision
        or candidate.abstention_recall < baseline.abstention_recall
    ):
        experiment_reasons.append("QDRANT_NO_ANSWER_REGRESSION")
    if (
        candidate.exact_version_violation_rate > 0
        or candidate.acl_violation_rate > 0
        or candidate.engine_contract_violation_rate > 0
    ):
        experiment_reasons.append("QDRANT_SAFETY_REGRESSION")
    if candidate.family_duplicate_violation_rate > 0:
        experiment_reasons.append("QDRANT_FAMILY_DUPLICATE_VIOLATION")
    if candidate.degradation_rate > baseline.degradation_rate:
        experiment_reasons.append("QDRANT_DEGRADATION_REGRESSION")
    if (
        request.qdrant_operations_readiness is None
        or not request.qdrant_operations_readiness.all_ready
    ):
        experiment_reasons.append("QDRANT_OPERATIONS_NOT_READY")

    if experiment_reasons:
        return QdrantDecisionResult(
            status="keep_pgvector",
            recommend_qdrant=False,
            reason_codes=_unique(experiment_reasons),
            evaluated_window_ids=window_ids,
            p95_relative_improvement=p95_gain,
            p99_relative_improvement=p99_gain,
            recall_absolute_improvement=recall_gain,
            ndcg_absolute_improvement=ndcg_gain,
        )

    return QdrantDecisionResult(
        status="recommend_qdrant",
        recommend_qdrant=True,
        reason_codes=["QDRANT_GATE_PASSED"],
        evaluated_window_ids=window_ids,
        p95_relative_improvement=p95_gain,
        p99_relative_improvement=p99_gain,
        recall_absolute_improvement=recall_gain,
        ndcg_absolute_improvement=ndcg_gain,
    )


__all__ = [
    "PgVectorBenchmarkWindow",
    "QDRANT_DECISION_SCHEMA_VERSION",
    "QDRANT_GATE_SCHEMA_VERSION",
    "QdrantDecisionInput",
    "QdrantDecisionPolicy",
    "QdrantDecisionResult",
    "QdrantOperationsReadiness",
    "QdrantPairedExperiment",
    "RetrievalBenchmarkMetrics",
    "decide_qdrant",
]
