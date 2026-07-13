"""EvidencePackage 契约测试(retrieval-flow-consolidation)。"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from data_foundation.evidence import EvidenceItem, EvidencePackage


def _item(**over) -> dict:
    base = {
        "resource_id": "r1",
        "resource_version": 1,
        "title": "标题",
        "summary": "摘要",
        "source_updated_at": "未知",
        "indexed_at": "2026-06-25T00:00:00Z",
        "score": 0.8,
        "why_selected": "相关度高",
    }
    base.update(over)
    return base


def test_evidence_item_uses_why_selected_not_why_relevant():
    item = EvidenceItem(**_item())
    assert hasattr(item, "why_selected")
    assert not hasattr(item, "why_relevant")
    # 时效字段恒为字符串
    assert isinstance(item.source_updated_at, str)
    assert isinstance(item.indexed_at, str)


@pytest.mark.parametrize("resource_version", [None, 0, -1])
def test_evidence_item_requires_exact_positive_resource_version(resource_version):
    with pytest.raises(ValidationError):
        EvidenceItem(**_item(resource_version=resource_version))


def test_semantic_package_with_evidence_ok():
    pkg = EvidencePackage(retrieval_mode="semantic", evidence=[EvidenceItem(**_item())])
    assert pkg.retrieval_mode == "semantic"
    assert len(pkg.evidence) == 1


def test_invalid_retrieval_mode_rejected():
    with pytest.raises(ValidationError):
        EvidencePackage(retrieval_mode="bogus")  # type: ignore[arg-type]


def test_insufficient_relevance_requires_empty_evidence_and_gaps():
    # 合法:空 evidence + 非空 gaps
    ok = EvidencePackage(retrieval_mode="insufficient_relevance", evidence=[], gaps="库内无相关内容")
    assert ok.evidence == [] and ok.gaps

    # 非法:insufficient_relevance 却带 evidence
    with pytest.raises(ValidationError):
        EvidencePackage(
            retrieval_mode="insufficient_relevance",
            evidence=[EvidenceItem(**_item())],
            gaps="x",
        )
    # 非法:insufficient_relevance 但 gaps 为空
    with pytest.raises(ValidationError):
        EvidencePackage(retrieval_mode="insufficient_relevance", evidence=[], gaps=None)
    with pytest.raises(ValidationError):
        EvidencePackage(retrieval_mode="insufficient_relevance", evidence=[], gaps="   ")


# --- 属性测试:核心不变量 ---

_modes = st.sampled_from(["semantic", "keyword_fallback", "insufficient_relevance"])


@settings(max_examples=150)
@given(
    mode=_modes,
    n=st.integers(min_value=0, max_value=4),
    gaps=st.one_of(st.none(), st.text(max_size=20)),
)
def test_insufficient_relevance_invariant(mode, n, gaps):
    """insufficient_relevance ⟺ (evidence==[] ∧ gaps 非空);其余 mode 不受该约束。"""
    evidence = [EvidenceItem(**_item(resource_id=f"r{i}")) for i in range(n)]
    if mode == "insufficient_relevance":
        valid = (n == 0) and bool(gaps and gaps.strip())
        if valid:
            pkg = EvidencePackage(retrieval_mode=mode, evidence=evidence, gaps=gaps)
            assert pkg.evidence == [] and pkg.gaps
        else:
            with pytest.raises(ValidationError):
                EvidencePackage(retrieval_mode=mode, evidence=evidence, gaps=gaps)
    else:
        # semantic / keyword_fallback:任意 evidence 数量与 gaps 均可
        pkg = EvidencePackage(retrieval_mode=mode, evidence=evidence, gaps=gaps)
        assert pkg.retrieval_mode == mode
        assert len(pkg.evidence) == n


@settings(max_examples=80)
@given(n=st.integers(min_value=0, max_value=4))
def test_round_trip_stable(n):
    evidence = [EvidenceItem(**_item(resource_id=f"r{i}")) for i in range(n)]
    pkg = EvidencePackage(retrieval_mode="semantic", evidence=evidence, gaps=None)
    again = EvidencePackage(**pkg.model_dump())
    assert again.model_dump() == pkg.model_dump()
    # 时效字段 round-trip 仍为字符串
    for e in again.evidence:
        assert isinstance(e.source_updated_at, str) and isinstance(e.indexed_at, str)
