"""统一知识检索公开契约测试。"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from data_foundation.evidence import (
    EngineDegradation,
    EvidenceItem,
    EvidencePackage,
    RetrievalFilters,
)


def _item(**over) -> dict:
    base = {
        "resource_id": "00000000-0000-0000-0000-000000000001",
        "resource_version": 1,
        "type": "generated_copy",
        "asset_kind": "copy",
        "source_kind": "user_adopted",
        "niche": "职场",
        "title": "标题",
        "summary": "摘要",
        "source_updated_at": "未知",
        "indexed_at": "2026-07-13T00:00:00+00:00",
        "score": 0.8,
        "relevance": 0.9,
        "freshness": 0.7,
        "quality": 0.85,
        "performance": 0.4,
        "retrieval_sources": ["semantic"],
        "why_selected": "语义召回且质量较高",
    }
    base.update(over)
    return base


def test_evidence_item_is_complete_exact_and_forbids_guessed_fields() -> None:
    item = EvidenceItem(**_item())
    assert item.resource_version == 1
    assert item.source_updated_at == "未知"
    assert item.retrieval_sources == ["semantic"]
    assert not hasattr(item, "why_relevant")

    with pytest.raises(ValidationError):
        EvidenceItem(**_item(updated_at="2026-07-13T00:00:00Z"))


@pytest.mark.parametrize("resource_version", [None, 0, -1, True, 1.5])
def test_evidence_item_requires_exact_positive_resource_version(resource_version) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(**_item(resource_version=resource_version))


@pytest.mark.parametrize(
    "field,value",
    [
        ("score", -0.01),
        ("relevance", 1.01),
        ("freshness", -1),
        ("quality", 2),
        ("performance", -0.5),
    ],
)
def test_all_evidence_scores_are_unit_interval(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(**_item(**{field: value}))


@pytest.mark.parametrize(
    "value",
    ["not-a-date", "2026-07-13T00:00:00", "2026/07/13 00:00:00Z", ""],
)
def test_evidence_timestamps_require_timezone_or_unknown(value: str) -> None:
    with pytest.raises(ValidationError):
        EvidenceItem(**_item(indexed_at=value))


@pytest.mark.parametrize(
    "mode,sources,engines",
    [
        ("hybrid", ["semantic", "keyword"], ["semantic", "keyword"]),
        ("semantic_only", ["semantic"], ["semantic"]),
        ("keyword_only", ["keyword"], ["keyword"]),
        ("semantic_only", ["semantic", "graph"], ["semantic", "graph"]),
    ],
)
def test_success_modes_match_actual_evidence_sources(mode, sources, engines) -> None:
    package = EvidencePackage(
        retrieval_mode=mode,
        evidence=[EvidenceItem(**_item(retrieval_sources=sources))],
        engines_used=engines,
    )
    assert package.retrieval_mode == mode


@pytest.mark.parametrize(
    "mode,sources,engines",
    [
        ("hybrid", ["semantic"], ["semantic", "keyword"]),
        ("semantic_only", ["semantic", "keyword"], ["semantic", "keyword"]),
        ("keyword_only", ["semantic"], ["semantic"]),
        ("semantic_only", ["semantic", "graph"], ["semantic"]),
        ("semantic_only", ["semantic"], ["semantic", "keyword"]),
    ],
)
def test_mode_or_engine_source_mismatch_is_rejected(mode, sources, engines) -> None:
    with pytest.raises(ValidationError):
        EvidencePackage(
            retrieval_mode=mode,
            evidence=[EvidenceItem(**_item(retrieval_sources=sources))],
            engines_used=engines,
        )


def test_insufficient_relevance_requires_empty_evidence_and_nonblank_gap() -> None:
    package = EvidencePackage(
        retrieval_mode="insufficient_relevance",
        evidence=[],
        engines_used=["semantic", "keyword"],
        gaps="库内没有通过相关度与权限门的内容",
    )
    assert package.evidence == []

    with pytest.raises(ValidationError):
        EvidencePackage(
            retrieval_mode="insufficient_relevance",
            evidence=[EvidenceItem(**_item())],
            gaps="无",
        )
    with pytest.raises(ValidationError):
        EvidencePackage(retrieval_mode="insufficient_relevance", gaps="   ")


def test_engine_cannot_be_used_and_degraded_simultaneously() -> None:
    with pytest.raises(ValidationError):
        EvidencePackage(
            retrieval_mode="semantic_only",
            evidence=[EvidenceItem(**_item())],
            engines_used=["semantic"],
            degraded_engines=[
                EngineDegradation(engine="semantic", reason_code="TIMEOUT")
            ],
        )


def test_retrieval_filters_normalize_values_and_forbid_unknown_keys() -> None:
    filters = RetrievalFilters.model_validate(
        {
            "asset_kinds": [" copy ", "copy"],
            "source_kinds": ["user_adopted"],
            "niches": ["职场"],
            "min_quality": 0.8,
            "updated_after": "2026-07-01T00:00:00Z",
        }
    )
    assert filters.asset_kinds == ["copy"]
    assert filters.updated_after is not None
    assert filters.updated_after.utcoffset().total_seconds() == 0
    with pytest.raises(ValidationError):
        RetrievalFilters.model_validate({"visibility": "private"})


@settings(max_examples=80)
@given(
    score=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
    quality=st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False),
)
def test_evidence_package_round_trip_is_stable(score: float, quality: float) -> None:
    package = EvidencePackage(
        retrieval_mode="semantic_only",
        evidence=[EvidenceItem(**_item(score=score, quality=quality))],
        engines_used=["semantic"],
    )
    again = EvidencePackage.model_validate(package.model_dump(mode="json"))
    assert again == package
