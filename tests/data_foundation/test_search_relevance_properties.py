"""属性测试(Hypothesis):retrieval-relevance-overhaul 的正确性属性。

覆盖设计 Testing Strategy 的方向:
- Property 2:余弦 relevance 与候选集无关(绝对相关度不被抹除)
- Property 1:闸门单调性(数据不足必明说)
- Property 3 / Property 6:口径隔离 / 降级语义保持
"""
from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from hypothesis import given, settings
from hypothesis import strategies as st

from data_foundation import tools as df_tools
from data_foundation.processors.embedding import EmbeddingProviderConfig
from data_foundation.search_ranker import rank_evidence


def _clamp(x: float) -> float:
    return min(max(x, 0.0), 1.0)


def _items(scores: list[float]) -> list[dict]:
    # 每条唯一标题/ID,避免标题模糊去重影响"逐条 relevance"断言
    return [
        {
            "resource_id": f"r{i}",
            "title": f"标题-{i}",
            "summary": "s",
            "score": s,
            "metadata": {"type": "doc", "visibility": "team"},
        }
        for i, s in enumerate(scores)
    ]


# --- Property 2:余弦 relevance == clamp(自身分数, 0, 1),不随候选集最大值变化 ---
@settings(max_examples=200)
@given(st.lists(st.floats(min_value=-5.0, max_value=5.0, allow_nan=False, allow_infinity=False),
                min_size=1, max_size=8))
def test_cosine_relevance_is_absolute_and_independent_of_candidate_set(scores):
    items = _items(scores)
    ranked = rank_evidence("default", items, performance_data={}, limit=100, score_kind="cosine")
    rel_by_id = {r["resource_id"]: r["rank_signals"]["relevance"] for r in ranked}
    for i, s in enumerate(scores):
        # rank_signals.relevance 以 4 位四舍五入存储
        assert rel_by_id[f"r{i}"] == round(_clamp(s), 4)


# --- Property 3:BM25 路径候选集内归一化,且永不被绝对相关度下限闸门作用(不会因分数低而清空)---
@settings(max_examples=150)
@given(st.lists(st.floats(min_value=0.001, max_value=100.0, allow_nan=False, allow_infinity=False),
                min_size=1, max_size=8))
def test_bm25_path_normalizes_and_is_never_gated_by_floor(scores):
    items = _items(scores)
    ranked = rank_evidence("default", items, performance_data={}, limit=100, score_kind="bm25")
    # 唯一标题 → 不去重,全部保留(BM25 不施加绝对下限,即便分数都远低于 0.5)
    assert len(ranked) == len(items)
    max_raw = max(scores)
    rel_by_id = {r["resource_id"]: r["rank_signals"]["relevance"] for r in ranked}
    for i, s in enumerate(scores):
        assert rel_by_id[f"r{i}"] == round(s / max_raw, 4)


# ---------- 工具级闸门:夹具 ----------
class _User:
    identity = "ou_owner"


class _Config:
    server_info = SimpleNamespace(user=_User())


class _GateRepo:
    def __init__(self, top_score: float):
        self._top = top_score
        self.calls: list[str] = []
        self.active_index = SimpleNamespace(embedding_model="model-a", dimensions=1536, config_version="cfg")

    def active_embedding_index(self, tenant_id):
        self.calls.append("active_index")
        return self.active_index

    def semantic_rows(self, **kwargs):
        self.calls.append("semantic")
        return [{
            "id": "resource-1", "title": "x", "summary": None, "type": "topic",
            "visibility": "team", "score": self._top, "chunk_index": 0, "chunk_text": "c",
        }]

    def bulk_performance_metrics(self, tenant_id, resource_ids):
        self.calls.append("perf")
        return {rid: [] for rid in resource_ids}


def _run_gate(monkeypatch, top_score: float, floor: float):
    repo = _GateRepo(top_score)

    @contextmanager
    def repository():
        yield repo

    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setattr(
        df_tools, "_embedding_query_config_for_index",
        lambda idx: EmbeddingProviderConfig(base_url="https://e/v1", api_key="k",
                                            model="model-a", config_version="cfg", dimensions=1536),
    )
    monkeypatch.setattr(df_tools, "_embed_query", lambda *a, **k: [0.1] * 1536)
    monkeypatch.setattr("data_foundation.config.resolve_query_instruction", lambda model: None)
    monkeypatch.setattr("data_foundation.config.current_relevance_floor", lambda: floor)
    return df_tools.semantic_search_resources.func("q", top_k=3, config=_Config()), repo


# --- Property 1:闸门单调性 —— top_score < floor 当且仅当返回 insufficient_relevance ---
@settings(max_examples=150, deadline=None)
@given(st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False))
def test_gate_monotonic_around_floor(monkeypatch_factory_score):
    # pytest 的 monkeypatch 不能直接用于 @given;用 hypothesis 内建上下文逐例打补丁
    from _pytest.monkeypatch import MonkeyPatch
    score = monkeypatch_factory_score
    floor = 0.5
    mp = MonkeyPatch()
    try:
        out, repo = _run_gate(mp, score, floor)
    finally:
        mp.undo()
    if score < floor:
        assert out["mode"] == "insufficient_relevance"
        assert out["results"] == []
        assert out["threshold"] == floor
        # 数据不足:不降级到全文(不查 perf / 不进 BM25)
        assert "perf" not in repo.calls
    else:
        assert out["mode"] == "semantic"


# --- Property 6:降级语义保持 —— 无 active 索引恒走 keyword_fallback,不被误判为 insufficient ---
@settings(max_examples=50, deadline=None)
@given(st.text(min_size=1, max_size=12).filter(lambda s: s.strip()))
def test_no_active_index_always_keyword_fallback(query):
    from _pytest.monkeypatch import MonkeyPatch

    class _NoIndexRepo:
        def active_embedding_index(self, tenant_id):
            return None

    mp = MonkeyPatch()
    try:
        @contextmanager
        def repository():
            yield _NoIndexRepo()

        mp.setattr(df_tools, "_repository", repository)
        # 全文降级走 search_resources;此处让 Meili 不可用,得到确定的 keyword_fallback
        mp.delenv("XHS_MEILI_URL", raising=False)
        mp.delenv("XHS_MEILI_KEY", raising=False)
        out = df_tools.semantic_search_resources.func(query, top_k=3, config=_Config())
    finally:
        mp.undo()
    assert out["mode"] == "keyword_fallback"
    assert out["mode"] != "insufficient_relevance"


def test_rank_evidence_tolerates_non_numeric_metrics():
    """P2 回归:performance_metric 含字符串等脏值(如 "1.2万")时,rank_evidence 不得崩,
    脏值按 0 计、排序照常完成。"""
    items = _items([0.9, 0.8])
    dirty_perf = {
        "r0": [{"metrics": {"likes": "1.2万", "collects": None, "comments": "abc"}}],
        "r1": [{"metrics": {"likes": 100, "collects": 5, "comments": 2}}],
    }
    ranked = rank_evidence("default", items, performance_data=dirty_perf, limit=10, score_kind="cosine")
    assert len(ranked) == 2  # 没崩
    by_id = {r["resource_id"]: r for r in ranked}
    # r0 脏值按 0 计 → performance 信号为 0;r1 正常数值 → performance 信号 > 0
    assert by_id["r0"]["rank_signals"]["performance"] == 0.0
    assert by_id["r1"]["rank_signals"]["performance"] > 0.0
