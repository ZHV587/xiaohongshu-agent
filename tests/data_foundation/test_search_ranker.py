from __future__ import annotations
import pytest
from datetime import datetime, timezone, timedelta
from data_foundation.search_ranker import (
    DEFAULT_RELEVANCE_FLOOR,
    WEIGHT_FRESHNESS,
    WEIGHT_PERFORMANCE,
    WEIGHT_RELEVANCE,
    WEIGHT_TYPE,
    rank_evidence,
)


def test_weights_sum_to_one():
    assert abs((WEIGHT_RELEVANCE + WEIGHT_FRESHNESS + WEIGHT_TYPE + WEIGHT_PERFORMANCE) - 1.0) < 1e-9
    assert WEIGHT_RELEVANCE == 0.70
    assert WEIGHT_FRESHNESS == 0.15
    assert WEIGHT_TYPE == 0.10
    assert WEIGHT_PERFORMANCE == 0.05


def test_default_relevance_floor_value():
    assert DEFAULT_RELEVANCE_FLOOR == 0.50


def test_score_kind_is_required_keyword_only():
    with pytest.raises(TypeError):
        # score_kind 无默认值,必须显式传入
        rank_evidence("default", [], performance_data={})  # type: ignore[call-arg]


def test_invalid_score_kind_raises():
    with pytest.raises(ValueError):
        rank_evidence("default", [], performance_data={}, score_kind="bogus")


def _doc(resource_id, title, score, *, days_old=0, rtype="doc"):
    updated = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    return {
        "resource_id": resource_id,
        "title": title,
        "summary": "s",
        "score": score,
        "metadata": {
            "type": rtype,
            "visibility": "private",
            "source_updated_at": updated,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        },
    }


def test_cosine_relevance_is_absolute_not_normalized():
    """score_kind='cosine':relevance 等于绝对余弦(clamp 0~1),不随候选集最大值归一化。"""
    raw_results = [
        _doc("res-1", "露营装备挑选指南", 0.9),
        _doc("res-2", "露营装备挑选指南", 0.8),  # 标题模糊重复,应被去重
        _doc("res-3", "如何搭建一个坚固的帐篷", 0.5, days_old=10),
    ]
    res = rank_evidence("default", raw_results, performance_data={}, limit=10, score_kind="cosine")

    assert len(res) == 2  # res-2 去重
    assert res[0]["resource_id"] == "res-1"
    assert res[1]["resource_id"] == "res-3"

    # 关键:res-1 relevance == 0.9(绝对余弦),而非旧的归一化 1.0
    assert res[0]["rank_signals"]["relevance"] == 0.9
    assert res[1]["rank_signals"]["relevance"] == 0.5
    # freshness:res-3 源端 10 天前 → e^(-0.5) ≈ 0.6065
    assert abs(res[1]["rank_signals"]["freshness"] - 0.6065) < 0.001


def test_freshness_handles_naive_source_timestamp():
    """source_updated_at 无时区(naive,外部同步常见)时,时效分应正常按 UTC 计算,
    而不是因 naive/aware 相减抛 TypeError 被吞掉、静默退化成固定 0.7。"""
    naive_10d = (datetime.now(timezone.utc) - timedelta(days=10)).replace(tzinfo=None).isoformat()
    doc = {
        "resource_id": "res-naive",
        "title": "无时区时间戳的资源",
        "summary": "s",
        "score": 0.5,
        "metadata": {"type": "doc", "visibility": "private", "source_updated_at": naive_10d},
    }
    res = rank_evidence("default", [doc], performance_data={}, limit=10, score_kind="cosine")
    # 10 天前 → e^(-0.5) ≈ 0.6065,绝不能是退化默认值 0.7
    assert abs(res[0]["rank_signals"]["freshness"] - 0.6065) < 0.001


def test_cosine_relevance_clamped_to_unit_interval():
    raw_results = [_doc("a", "标题A", 1.2), _doc("b", "标题B", -0.1)]
    res = rank_evidence("default", raw_results, performance_data={}, limit=10, score_kind="cosine")
    rel = {r["resource_id"]: r["rank_signals"]["relevance"] for r in res}
    assert rel["a"] == 1.0   # 夹紧上界
    assert rel["b"] == 0.0   # 夹紧下界


def test_bm25_relevance_is_candidate_set_normalized():
    """score_kind='bm25':保留候选集内归一化(无固定上界)。"""
    raw_results = [_doc("a", "标题A", 4.0), _doc("b", "标题B", 2.0)]
    res = rank_evidence("default", raw_results, performance_data={}, limit=10, score_kind="bm25")
    rel = {r["resource_id"]: r["rank_signals"]["relevance"] for r in res}
    assert rel["a"] == 1.0     # 4.0 / 4.0
    assert rel["b"] == 0.5     # 2.0 / 4.0


def test_rank_evidence_incorporates_performance_log_score():
    """效果分对数归一化(去饱和):engagement=500 → log10(501)/log10(1+1e6)。"""
    import math
    from data_foundation.search_ranker import P_SCORE_LOG_CAP

    raw_results = [_doc("res-1", "爆款文案1", 0.5, rtype="generated_copy")]
    performance_data = {
        "res-1": [{"metrics": {"likes": 200, "collects": 100, "comments": 20}}]
        # engagement = 200 + 2*100 + 5*20 = 500
    }
    res = rank_evidence("default", raw_results, performance_data=performance_data, limit=10, score_kind="cosine")
    assert len(res) == 1
    expected = math.log10(1.0 + 500) / math.log10(1.0 + P_SCORE_LOG_CAP)
    assert abs(res[0]["rank_signals"]["performance"] - expected) < 0.0001


def test_rank_evidence_performance_not_saturated_for_viral():
    """万级与十万级爆款效果分不同(旧 tanh 会都 ≈1.0)。"""
    r1 = rank_evidence("default", [_doc("a", "爆款A", 0.5)],
                       {"a": [{"metrics": {"likes": 10_000}}]}, score_kind="cosine")
    r2 = rank_evidence("default", [_doc("b", "爆款B", 0.5)],
                       {"b": [{"metrics": {"likes": 300_000}}]}, score_kind="cosine")
    p1 = r1[0]["rank_signals"]["performance"]
    p2 = r2[0]["rank_signals"]["performance"]
    assert p1 < p2 <= 1.0
    assert p1 < 1.0  # 万级未饱和到上界


def test_empty_results_returns_empty():
    assert rank_evidence("default", [], performance_data={}, score_kind="cosine") == []
