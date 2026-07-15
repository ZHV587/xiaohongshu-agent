from __future__ import annotations

import math
from typing import Any

from data_foundation.knowledge.models import KnowledgeDecision, KnowledgeSnapshot
from data_foundation.writing_teardown import (
    TEARDOWN_ANALYSIS_SCHEMA_VERSION,
    TEARDOWN_DETERMINISTIC_QUALITY,
)


_SIGNAL_TYPES = {
    "performance_metric",
    "generated_topic",
    "user_feedback",
    "feedback",
    "adoption_feedback",
    "revision_request",
    "writing_preference_profile",
}
_TEARDOWN_TYPES = {"writing_teardown", "explosive_teardown", "xhs_teardown"}
_TEARDOWN_REQUIRED_LIST_FIELDS = ("structure", "success_factors", "style_tags")


def _authority(*, origin: str, validation: str, provenance: str, score: float) -> dict[str, Any]:
    return {
        "origin": origin,
        "validation": validation,
        "provenance": provenance,
        "score": round(max(0.0, min(float(score), 1.0)), 4),
    }


def _quality(content_json: dict[str, Any], default: float) -> float:
    value = content_json.get("quality_score", default)
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if not math.isfinite(number):
        number = default
    # Structured teardowns use the product-facing 0..100 score while knowledge state
    # stores one normalized 0..1 scale for filtering/ranking.
    if 1.0 < number <= 100.0:
        number /= 100.0
    return round(max(0.0, min(number, 1.0)), 4)


def _decision(
    eligibility: str,
    *,
    asset_kind: str,
    source_kind: str,
    authority: dict[str, Any],
    quality: float,
    synthesis: bool,
    reason: str,
) -> KnowledgeDecision:
    return KnowledgeDecision(
        eligibility=eligibility,  # type: ignore[arg-type]
        asset_kind=asset_kind,
        source_kind=source_kind,
        source_authority=authority,
        quality_score=quality,
        eligible_for_synthesis=synthesis and eligibility == "qualified",
        reason_code=reason,
    )


def classify_knowledge_asset(
    snapshot: KnowledgeSnapshot,
    *,
    normalized_text: str,
) -> KnowledgeDecision:
    """Deterministic qualification policy; never infers adoption or evidence."""
    resource_type = snapshot.resource_type
    content = snapshot.content_json or {}
    empty = not normalized_text

    if snapshot.status != "active":
        return _decision(
            "rejected", asset_kind="inactive", source_kind="resource_status",
            authority=_authority(
                origin="system", validation="inactive", provenance="resource", score=0.0
            ),
            quality=0.0, synthesis=False, reason="INACTIVE_RESOURCE_NOT_KNOWLEDGE",
        )

    if resource_type in _SIGNAL_TYPES:
        return _decision(
            "rejected", asset_kind="signal", source_kind="behavior_signal",
            authority=_authority(origin="system", validation="observed", provenance="resource_event", score=0.6),
            quality=0.0, synthesis=False, reason="SIGNAL_NOT_WRITING_EXAMPLE",
        )

    if resource_type == "session_snapshot":
        confirmation = snapshot.confirmation_metadata or {}
        # 正文由模型生成，不能自证“用户已确认”。只信经过写权限校验后落进
        # knowledge_asset_states.metadata.confirmation 的审计事实。
        confirmed = confirmation.get("confirmed") is True and bool(
            str(confirmation.get("confirmed_by") or "").strip()
        )
        snapshot_kind = str(confirmation.get("snapshot_kind") or "").strip()
        if not confirmed or not snapshot_kind or empty:
            return _decision(
                "rejected", asset_kind="signal", source_kind="session_snapshot",
                authority=_authority(origin="user", validation="unconfirmed", provenance="session", score=0.3),
                quality=0.0, synthesis=False, reason="SESSION_SNAPSHOT_NOT_CONFIRMED",
            )
        return _decision(
            "qualified", asset_kind="strategy_fact", source_kind="user_confirmed",
            authority=_authority(origin="user", validation="confirmed", provenance="session", score=0.9),
            quality=_quality(content, 0.75), synthesis=False, reason="CONFIRMED_STRATEGY_FACT",
        )

    if resource_type == "generated_copy":
        if snapshot.knowledge_target_version != snapshot.resource_version:
            return _decision(
                "rejected", asset_kind="signal", source_kind="agent_candidate",
                authority=_authority(origin="agent", validation="unadopted", provenance="generation", score=0.1),
                quality=0.0, synthesis=False, reason="GENERATED_COPY_NOT_KNOWLEDGE_TARGET",
            )
        if empty:
            return _decision(
                "rejected", asset_kind="copy", source_kind="user_adopted",
                authority=_authority(origin="agent", validation="adopted", provenance="lifecycle", score=0.8),
                quality=0.0, synthesis=False, reason="EMPTY_CONTENT",
            )
        published = snapshot.lifecycle_status in {"published", "measured"}
        return _decision(
            "qualified", asset_kind="copy",
            source_kind="published_copy" if published else "user_adopted",
            authority=_authority(
                origin="agent", validation="published" if published else "adopted",
                provenance="lifecycle", score=0.95 if published else 0.85,
            ),
            quality=_quality(content, 0.85 if published else 0.75),
            synthesis=True, reason="EXPLICIT_LIFECYCLE_TARGET",
        )

    if resource_type == "writing_pattern":
        raw_family_ids = content.get("source_family_ids")
        family_ids = {
            str(item).strip() for item in raw_family_ids
            if str(item).strip()
        } if isinstance(raw_family_ids, list) else set()
        try:
            threshold = int(content.get("synthesis_threshold", 0))
        except (TypeError, ValueError):
            threshold = 0
        qualified = (
            not empty
            and threshold >= 3
            and len(family_ids) >= threshold
            and snapshot.synthesis_family_count >= threshold
        )
        return _decision(
            "qualified" if qualified else "rejected",
            asset_kind="pattern", source_kind="synthesized_pattern",
            authority=_authority(
                origin="derived", validation="multi_family" if qualified else "insufficient_evidence",
                provenance="synthesized_from_edges", score=0.85 if qualified else 0.1,
            ),
            quality=_quality(content, 0.8 if qualified else 0.0), synthesis=False,
            reason="MULTI_FAMILY_SYNTHESIS" if qualified else "PATTERN_NEEDS_THREE_EXACT_FAMILIES",
        )

    if empty:
        return _decision(
            "rejected", asset_kind="source_material", source_kind="imported",
            authority=_authority(origin="external", validation="unknown", provenance="resource", score=0.2),
            quality=0.0, synthesis=False, reason="EMPTY_CONTENT",
        )

    if resource_type in _TEARDOWN_TYPES:
        if snapshot.teardown_source_count != 1:
            return _decision(
                "rejected", asset_kind="teardown", source_kind="writing_teardown",
                authority=_authority(
                    origin="derived", validation="missing_exact_source",
                    provenance="teardown_of_edge", score=0.1,
                ),
                quality=0.0, synthesis=False, reason="TEARDOWN_REQUIRES_ONE_EXACT_SOURCE",
            )
        structured = (
            content.get("analysis_schema_version") == TEARDOWN_ANALYSIS_SCHEMA_VERSION
            and content.get("analysis_kind") == "writing_teardown"
            and content.get("metadata_provenance") == "model_analysis_exact_source"
            and all(
                isinstance(content.get(field), str) and content[field].strip()
                for field in ("niche", "hook", "cta")
            )
            and all(
                isinstance(content.get(field), list)
                and any(isinstance(item, str) and item.strip() for item in content[field])
                for field in _TEARDOWN_REQUIRED_LIST_FIELDS
            )
        )
        if not structured:
            return _decision(
                "rejected", asset_kind="teardown", source_kind="writing_teardown",
                authority=_authority(
                    origin="derived", validation="invalid_schema",
                    provenance="teardown_payload", score=0.1,
                ),
                quality=0.0, synthesis=False, reason="TEARDOWN_SCHEMA_INCOMPLETE",
            )
        return _decision(
            "qualified", asset_kind="teardown", source_kind="writing_teardown",
            authority=_authority(origin="derived", validation="structured", provenance="exact_source", score=0.85),
            # 模型自评不能作为知识资格分；结构完整 + 唯一 exact source 使用固定、可复现质量。
            quality=TEARDOWN_DETERMINISTIC_QUALITY,
            synthesis=True,
            reason="STRUCTURED_TEARDOWN",
        )

    if resource_type == "xhs_online_note":
        return _decision(
            "qualified", asset_kind="source_material", source_kind="benchmark_adopted",
            authority=_authority(origin="external", validation="user_adopted", provenance="online_note", score=0.85),
            quality=_quality(content, 0.75), synthesis=True, reason="ADOPTED_BENCHMARK",
        )

    synced = bool(snapshot.mapping_systems) or resource_type in {"feishu_doc", "feishu_base_record"}
    return _decision(
        "qualified", asset_kind="source_material",
        source_kind="workspace_sync" if synced else "imported",
        authority=_authority(
            origin="workspace" if synced else "external",
            validation="synced" if synced else "unverified",
            provenance="resource_mapping" if synced else "resource",
            score=0.7 if synced else 0.5,
        ),
        quality=_quality(content, 0.65 if synced else 0.5),
        synthesis=True, reason="NONEMPTY_SOURCE_MATERIAL",
    )
