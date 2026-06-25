"""rank_evidence 效果分去饱和测试(feishu-performance-metrics)。

根因:tanh((likes+2collects+5comments)/500) 对万级对标爆款全部饱和到 ≈1.0,
爆款间无区分。改对数归一化后须跨 10²~10⁶ 单调可分、∈[0,1]、无指标→0。
"""
import math

from hypothesis import given, strategies as st

from data_foundation.search_ranker import (
    WEIGHT_FRESHNESS,
    WEIGHT_PERFORMANCE,
    WEIGHT_RELEVANCE,
    WEIGHT_TYPE,
    rank_evidence,
)


def _result(rid: str, score: float = 0.6):
    return {
        "resource_id": rid,
        "title": f"t-{rid}",
        "summary": "s",
        "score": score,
        "metadata": {"type": "feishu_base_record"},
    }


def _perf(likes=0, collects=0, comments=0):
    return [{"metrics": {"likes": likes, "collects": collects, "comments": comments}}]


def _p_score_of(rid, perf):
    ranked = rank_evidence("default", [_result(rid)], {rid: perf}, score_kind="cosine")
    return ranked[0]["rank_signals"]["performance"]


def test_weights_sum_to_one():
    assert abs(WEIGHT_RELEVANCE + WEIGHT_FRESHNESS + WEIGHT_TYPE + WEIGHT_PERFORMANCE - 1.0) < 1e-9


def test_no_metrics_zero():
    assert _p_score_of("a", []) == 0.0
    assert _p_score_of("a", _perf()) == 0.0  # engagement=0


def test_monotonic_across_magnitudes():
    p100 = _p_score_of("a", _perf(likes=100))
    p10k = _p_score_of("b", _perf(likes=10_000))
    p1m = _p_score_of("c", _perf(likes=1_000_000))
    assert 0.0 < p100 < p10k < p1m <= 1.0


def test_viral_no_longer_saturated_to_same_value():
    """万级与十万级爆款不再同分(旧 tanh 会都 ≈1.0)。"""
    p1 = _p_score_of("a", _perf(likes=10_000, collects=10_000))
    p2 = _p_score_of("b", _perf(likes=300_000, collects=200_000))
    assert p2 > p1
    assert p1 < 1.0  # 万级未顶到上界


def test_bounded_unit_interval():
    huge = _p_score_of("a", _perf(likes=10**9, collects=10**9, comments=10**9))
    assert 0.0 <= huge <= 1.0


@given(
    likes=st.integers(min_value=0, max_value=10**7),
    collects=st.integers(min_value=0, max_value=10**7),
    comments=st.integers(min_value=0, max_value=10**6),
)
def test_property_bounded_and_zero_iff_no_engagement(likes, collects, comments):
    p = _p_score_of("x", _perf(likes=likes, collects=collects, comments=comments))
    assert 0.0 <= p <= 1.0
    engagement = likes + 2 * collects + 5 * comments
    assert (p == 0.0) == (engagement == 0)


@given(
    e1=st.integers(min_value=0, max_value=10**6),
    e2=st.integers(min_value=0, max_value=10**6),
)
def test_property_monotonic_in_engagement(e1, e2):
    p1 = _p_score_of("a", _perf(likes=e1))
    p2 = _p_score_of("b", _perf(likes=e2))
    if e1 < e2:
        assert p1 <= p2
