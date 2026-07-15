from data_foundation.knowledge_quality_gate import (
    KnowledgeQualityGateInput,
    evaluate_knowledge_quality_gate,
)


def _payload() -> dict:
    retrieval = {
        "dataset_id": "real-paired-2026-07",
        "query_count": 220,
        "no_answer_accuracy": 0.93,
        "exact_version_violation_count": 0,
        "acl_violation_count": 0,
        "hard_failure": False,
    }
    return {
        "schema_version": "knowledge-quality-gate-v1",
        "baseline_retrieval": {**retrieval, "ndcg_at_k": 0.70},
        "candidate_retrieval": {**retrieval, "ndcg_at_k": 0.75},
        "generation": {
            "evaluation_id": "real-blind-generation-2026-07",
            "sample_count": 130,
            "candidate_preferred_count": 72,
            "baseline_preferred_count": 48,
            "tied_count": 10,
            "workflow_completed_count": 129,
            "exact_version_violation_count": 0,
            "acl_violation_count": 0,
        },
    }


def test_real_quality_gate_requires_retrieval_gain_and_generation_preference() -> None:
    decision = evaluate_knowledge_quality_gate(
        KnowledgeQualityGateInput.model_validate(_payload())
    )
    assert decision.passed is True
    assert decision.relative_ndcg_gain == 0.071429
    assert decision.candidate_preference_rate == 0.6
    assert decision.security_violation_count == 0


def test_quality_gate_fails_closed_on_small_samples_or_security_violation() -> None:
    payload = _payload()
    payload["candidate_retrieval"]["query_count"] = 199
    payload["candidate_retrieval"]["acl_violation_count"] = 1
    payload["generation"]["sample_count"] = 119
    payload["generation"]["candidate_preferred_count"] = 60
    payload["generation"]["baseline_preferred_count"] = 49
    payload["generation"]["tied_count"] = 10
    payload["generation"]["workflow_completed_count"] = 119
    decision = evaluate_knowledge_quality_gate(
        KnowledgeQualityGateInput.model_validate(payload)
    )
    assert decision.passed is False
    assert "CANDIDATE_RETRIEVAL_SAMPLE_TOO_SMALL" in decision.reasons
    assert "GENERATION_SAMPLE_TOO_SMALL" in decision.reasons
    assert "ACL_OR_EXACT_VERSION_VIOLATION" in decision.reasons
