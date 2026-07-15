"""知识增强上线前的真实配对评测门。

输入只包含聚合指标，不接收或保存用户查询、文案正文与模型响应。真实标注和盲测数据必须
由生产采样产生；本模块只负责不可绕过的样本量、检索质量、安全与工作流门槛。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RetrievalQualitySnapshot(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    dataset_id: str = Field(min_length=1)
    query_count: int = Field(ge=0, strict=True)
    ndcg_at_k: float | None = Field(default=None, ge=0.0, le=1.0)
    no_answer_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    exact_version_violation_count: int = Field(ge=0, strict=True)
    acl_violation_count: int = Field(ge=0, strict=True)
    hard_failure: bool = False


class GenerationQualitySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evaluation_id: str = Field(min_length=1)
    sample_count: int = Field(ge=0, strict=True)
    candidate_preferred_count: int = Field(ge=0, strict=True)
    baseline_preferred_count: int = Field(ge=0, strict=True)
    tied_count: int = Field(ge=0, strict=True)
    workflow_completed_count: int = Field(ge=0, strict=True)
    exact_version_violation_count: int = Field(ge=0, strict=True)
    acl_violation_count: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def _validate_counts(self) -> "GenerationQualitySnapshot":
        if (
            self.candidate_preferred_count
            + self.baseline_preferred_count
            + self.tied_count
            != self.sample_count
        ):
            raise ValueError("generation preference counts must equal sample_count")
        if self.workflow_completed_count > self.sample_count:
            raise ValueError("workflow_completed_count cannot exceed sample_count")
        return self

    @property
    def decisive_count(self) -> int:
        return self.candidate_preferred_count + self.baseline_preferred_count

    @property
    def candidate_preference_rate(self) -> float | None:
        return (
            self.candidate_preferred_count / self.decisive_count
            if self.decisive_count
            else None
        )

    @property
    def workflow_completion_rate(self) -> float | None:
        return (
            self.workflow_completed_count / self.sample_count
            if self.sample_count
            else None
        )


class KnowledgeQualityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_retrieval_queries: int = Field(default=200, ge=200, strict=True)
    min_generation_samples: int = Field(default=120, ge=120, strict=True)
    min_relative_ndcg_gain: float = Field(default=0.05, ge=0.05, le=1.0)
    min_no_answer_accuracy: float = Field(default=0.90, ge=0.90, le=1.0)
    min_candidate_preference_rate: float = Field(default=0.55, ge=0.55, le=1.0)
    min_workflow_completion_rate: float = Field(default=0.98, ge=0.98, le=1.0)


class KnowledgeQualityGateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["knowledge-quality-gate-v1"] = "knowledge-quality-gate-v1"
    baseline_retrieval: RetrievalQualitySnapshot
    candidate_retrieval: RetrievalQualitySnapshot
    generation: GenerationQualitySnapshot
    policy: KnowledgeQualityPolicy = Field(default_factory=KnowledgeQualityPolicy)

    @model_validator(mode="after")
    def _validate_paired_retrieval(self) -> "KnowledgeQualityGateInput":
        if self.baseline_retrieval.dataset_id != self.candidate_retrieval.dataset_id:
            raise ValueError("baseline and candidate must use the same retrieval dataset")
        return self


class KnowledgeQualityGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["knowledge-quality-gate-decision-v1"] = (
        "knowledge-quality-gate-decision-v1"
    )
    passed: bool
    reasons: list[str]
    retrieval_query_count: int
    generation_sample_count: int
    relative_ndcg_gain: float | None
    no_answer_accuracy: float | None
    candidate_preference_rate: float | None
    workflow_completion_rate: float | None
    security_violation_count: int


def evaluate_knowledge_quality_gate(
    payload: KnowledgeQualityGateInput,
) -> KnowledgeQualityGateDecision:
    policy = payload.policy
    baseline = payload.baseline_retrieval
    candidate = payload.candidate_retrieval
    generation = payload.generation
    reasons: list[str] = []

    if baseline.query_count < policy.min_retrieval_queries:
        reasons.append("BASELINE_RETRIEVAL_SAMPLE_TOO_SMALL")
    if candidate.query_count < policy.min_retrieval_queries:
        reasons.append("CANDIDATE_RETRIEVAL_SAMPLE_TOO_SMALL")
    if generation.sample_count < policy.min_generation_samples:
        reasons.append("GENERATION_SAMPLE_TOO_SMALL")

    relative_ndcg_gain = None
    if baseline.ndcg_at_k is None or candidate.ndcg_at_k is None:
        reasons.append("NDCG_MISSING")
    elif baseline.ndcg_at_k <= 0:
        reasons.append("BASELINE_NDCG_NOT_COMPARABLE")
    else:
        relative_ndcg_gain = (
            candidate.ndcg_at_k - baseline.ndcg_at_k
        ) / baseline.ndcg_at_k
        if relative_ndcg_gain < policy.min_relative_ndcg_gain:
            reasons.append("NDCG_RELATIVE_GAIN_BELOW_TARGET")

    if (
        candidate.no_answer_accuracy is None
        or candidate.no_answer_accuracy < policy.min_no_answer_accuracy
    ):
        reasons.append("NO_ANSWER_ACCURACY_BELOW_TARGET")

    preference_rate = generation.candidate_preference_rate
    if (
        preference_rate is None
        or preference_rate < policy.min_candidate_preference_rate
    ):
        reasons.append("GENERATION_PREFERENCE_RATE_BELOW_TARGET")
    workflow_rate = generation.workflow_completion_rate
    if (
        workflow_rate is None
        or workflow_rate < policy.min_workflow_completion_rate
    ):
        reasons.append("WORKFLOW_COMPLETION_RATE_BELOW_TARGET")

    security_violations = sum(
        (
            baseline.exact_version_violation_count,
            baseline.acl_violation_count,
            candidate.exact_version_violation_count,
            candidate.acl_violation_count,
            generation.exact_version_violation_count,
            generation.acl_violation_count,
        )
    )
    if security_violations:
        reasons.append("ACL_OR_EXACT_VERSION_VIOLATION")
    if baseline.hard_failure or candidate.hard_failure:
        reasons.append("RETRIEVAL_REPORT_HARD_FAILURE")

    return KnowledgeQualityGateDecision(
        passed=not reasons,
        reasons=reasons,
        retrieval_query_count=candidate.query_count,
        generation_sample_count=generation.sample_count,
        relative_ndcg_gain=(
            None if relative_ndcg_gain is None else round(relative_ndcg_gain, 6)
        ),
        no_answer_accuracy=candidate.no_answer_accuracy,
        candidate_preference_rate=(
            None if preference_rate is None else round(preference_rate, 6)
        ),
        workflow_completion_rate=(
            None if workflow_rate is None else round(workflow_rate, 6)
        ),
        security_violation_count=security_violations,
    )


__all__ = [
    "GenerationQualitySnapshot",
    "KnowledgeQualityGateDecision",
    "KnowledgeQualityGateInput",
    "KnowledgeQualityPolicy",
    "RetrievalQualitySnapshot",
    "evaluate_knowledge_quality_gate",
]
