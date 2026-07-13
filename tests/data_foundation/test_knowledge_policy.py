from dataclasses import replace

from data_foundation.knowledge.models import KnowledgeSnapshot
from data_foundation.knowledge.policy import classify_knowledge_asset


def _snapshot(**overrides):
    base = KnowledgeSnapshot(
        tenant_id="tenant-a",
        resource_id="11111111-1111-1111-1111-111111111111",
        resource_version=1,
        resource_type="feishu_doc",
        status="active",
        visibility="private",
        owner_open_id="ou_owner",
        title="标题",
        content_text="正文",
        content_json={},
    )
    return replace(base, **overrides)


def test_generated_copy_requires_exact_lifecycle_knowledge_target():
    candidate = _snapshot(
        resource_type="generated_copy",
        lifecycle_status="candidate",
        knowledge_target_version=None,
    )
    adopted = replace(
        candidate,
        lifecycle_status="adopted",
        knowledge_target_version=1,
    )

    rejected = classify_knowledge_asset(candidate, normalized_text="正文")
    qualified = classify_knowledge_asset(adopted, normalized_text="正文")

    assert rejected.eligibility == "rejected"
    assert rejected.reason_code == "GENERATED_COPY_NOT_KNOWLEDGE_TARGET"
    assert qualified.eligibility == "qualified"
    assert qualified.source_kind == "user_adopted"
    assert qualified.eligible_for_synthesis is True


def test_session_snapshot_requires_kind_and_explicit_confirmation():
    unconfirmed = _snapshot(
        resource_type="session_snapshot",
        content_json={"snapshot_kind": "positioning"},
    )
    confirmed = replace(
        unconfirmed,
        confirmation_metadata={
            "confirmed": True,
            "confirmed_by": "ou_owner",
            "snapshot_kind": "positioning",
        },
    )

    assert classify_knowledge_asset(unconfirmed, normalized_text="定位事实").asset_kind == "signal"
    decision = classify_knowledge_asset(confirmed, normalized_text="定位事实")
    assert decision.eligibility == "qualified"
    assert decision.asset_kind == "strategy_fact"


def test_writing_pattern_requires_three_distinct_families_and_exact_edges():
    content = {
        "source_family_ids": ["f1", "f2", "f3", "f3"],
        "synthesis_threshold": 3,
    }
    insufficient = _snapshot(
        resource_type="writing_pattern",
        content_json=content,
        synthesis_family_count=2,
    )
    sufficient = replace(insufficient, synthesis_family_count=3)

    assert classify_knowledge_asset(insufficient, normalized_text="模式").eligibility == "rejected"
    decision = classify_knowledge_asset(sufficient, normalized_text="模式")
    assert decision.eligibility == "qualified"
    assert decision.asset_kind == "pattern"


def test_metrics_topics_and_anchor_are_never_writing_knowledge():
    for resource_type in (
        "performance_metric",
        "generated_topic",
        "revision_request",
        "writing_preference_profile",
        "knowledge_anchor",
    ):
        decision = classify_knowledge_asset(
            _snapshot(resource_type=resource_type),
            normalized_text="有正文也不能当案例",
        )
        assert decision.eligibility == "rejected"
        assert decision.eligible_for_synthesis is False


def test_teardown_quality_is_normalized_from_product_scale():
    decision = classify_knowledge_asset(
        _snapshot(
            resource_type="writing_teardown",
            content_json={"quality_score": 82},
            teardown_source_count=1,
        ),
        normalized_text="结构化拆解",
    )

    assert decision.eligibility == "qualified"
    assert decision.quality_score == 0.82


def test_session_snapshot_cannot_self_confirm_in_model_authored_content():
    spoofed = _snapshot(
        resource_type="session_snapshot",
        content_json={
            "confirmed": True,
            "confirmed_by": "ou_owner",
            "snapshot_kind": "positioning",
        },
    )

    decision = classify_knowledge_asset(spoofed, normalized_text="模型自报确认")

    assert decision.eligibility == "rejected"
    assert decision.reason_code == "SESSION_SNAPSHOT_NOT_CONFIRMED"


def test_teardown_requires_one_exact_source_edge():
    missing = _snapshot(
        resource_type="writing_teardown",
        content_json={"quality_score": 0.82},
        teardown_source_count=0,
    )
    ambiguous = replace(missing, teardown_source_count=2)

    for snapshot in (missing, ambiguous):
        decision = classify_knowledge_asset(snapshot, normalized_text="结构化拆解")
        assert decision.eligibility == "rejected"
        assert decision.reason_code == "TEARDOWN_REQUIRES_ONE_EXACT_SOURCE"
