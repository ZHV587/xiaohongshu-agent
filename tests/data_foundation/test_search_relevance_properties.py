from datetime import datetime, timezone
import uuid

from hypothesis import given, strategies as st
import pytest

from data_foundation.processors.embedding import EmbeddingProviderConfig
from data_foundation.retrieval import (
    EmbeddingSearchUnavailable,
    RetrievalSecurityGateError,
    RetrievalService,
    embed_query,
)
from data_foundation.search_ranker import RecallHit


def _id(seed: int) -> str:
    return str(uuid.UUID(int=seed))


def _row(seed: int, *, version: int = 1, family: str | None = None) -> dict:
    return {
        "resource_id": _id(seed),
        "resource_version": version,
        "resource_type": "generated_copy",
        "asset_kind": "copy",
        "source_kind": "user_adopted",
        "niche": "职场",
        "title": f"标题 {seed}",
        "summary": f"摘要 {seed}",
        "content_text": f"正文 {seed}",
        "quality_score": 0.9,
        "duplicate_family_id": family,
        "qualified_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "indexed_at": datetime(2026, 7, 2, tzinfo=timezone.utc),
        "source_updated_at": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }


class _Repo:
    def __init__(self, rows: list[dict], *, fail_gate: bool = False):
        self.rows = {
            (row["resource_id"], row["resource_version"]): row for row in rows
        }
        self.fail_gate = fail_gate
        self.gate_calls: list[dict] = []
        self.performance_calls: list[dict] = []

    def current_knowledge_rows(self, **kwargs):
        self.gate_calls.append(kwargs)
        if self.fail_gate:
            raise RuntimeError("postgres://user:secret@db/private")
        identities = zip(kwargs["resource_ids"], kwargs["resource_versions"])
        return [self.rows[identity] for identity in identities if identity in self.rows]

    def bulk_exact_performance_metrics(self, **kwargs):
        self.performance_calls.append(kwargs)
        return {
            (resource_id, version): []
            for resource_id, version in zip(
                kwargs["resource_ids"], kwargs["resource_versions"]
            )
        }


def _service(
    repo: _Repo,
    *,
    semantic,
    keyword,
    graph=None,
    floor: float = 0.5,
    shadow_reranker=None,
    shadow_observer=None,
) -> RetrievalService:
    return RetrievalService(
        repo,
        semantic_recall=semantic,
        keyword_recall=keyword,
        graph_expand=graph,
        relevance_floor=floor,
        shadow_reranker=shadow_reranker,
        shadow_observer=shadow_observer,
    )


def test_hybrid_mode_requires_evidence_from_both_primary_engines() -> None:
    repo = _Repo([_row(1)])
    service = _service(
        repo,
        semantic=lambda **_: [RecallHit(_id(1), 1, 0.91)],
        keyword=lambda **_: [RecallHit(_id(1), 1, 0.88)],
    )

    package = service.retrieve(
        tenant_id="default", actor_open_id="ou_user", query="职场写作"
    )

    assert package.retrieval_mode == "hybrid"
    assert package.engines_used == ["semantic", "keyword"]
    assert package.evidence[0].retrieval_sources == ["semantic", "keyword"]
    assert package.degraded_engines[0].engine == "graph"


def test_healthy_engine_without_usable_hits_does_not_mislabel_mode() -> None:
    repo = _Repo([_row(1)])
    package = _service(
        repo,
        semantic=lambda **_: [RecallHit(_id(1), 1, 0.9)],
        keyword=lambda **_: [],
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="职场")

    assert package.retrieval_mode == "semantic_only"
    assert package.engines_used == ["semantic"]
    assert not any(item.engine == "keyword" for item in package.degraded_engines)


def test_semantic_failure_degrades_safely_to_keyword_only() -> None:
    repo = _Repo([_row(1)])

    def semantic(**_):
        raise RuntimeError("Authorization: Bearer top-secret query=隐私正文")

    package = _service(
        repo,
        semantic=semantic,
        keyword=lambda **_: [RecallHit(_id(1), 1, 0.7)],
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="职场")

    assert package.retrieval_mode == "keyword_only"
    reason = package.degraded_engines[0].reason_code
    assert reason == "SEMANTIC_QUERY_FAILED_RUNTIMEERROR"
    assert "SECRET" not in reason and "隐私" not in reason


def test_low_semantic_candidates_and_no_keyword_evidence_are_insufficient() -> None:
    repo = _Repo([_row(1)])
    package = _service(
        repo,
        semantic=lambda **_: [RecallHit(_id(1), 1, 0.49)],
        keyword=lambda **_: [],
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="无关问题")

    assert package.retrieval_mode == "insufficient_relevance"
    assert package.evidence == []
    assert package.gaps


def test_zero_score_keyword_candidate_cannot_be_promoted_by_rrf() -> None:
    repo = _Repo([_row(1)])
    package = _service(
        repo,
        semantic=lambda **_: [],
        keyword=lambda **_: [RecallHit(_id(1), 1, 0.0)],
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="不命中")
    assert package.retrieval_mode == "insufficient_relevance"
    assert package.evidence == []


def test_weak_positive_keyword_candidate_below_absolute_floor_is_rejected() -> None:
    repo = _Repo([_row(1)])
    package = _service(
        repo,
        semantic=lambda **_: [],
        keyword=lambda **_: [RecallHit(_id(1), 1, 0.149)],
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="仅擦边的词")

    assert package.retrieval_mode == "insufficient_relevance"
    assert package.evidence == []


def test_filters_reach_keyword_prefilter_and_postgres_final_gate() -> None:
    repo = _Repo([_row(1)])
    keyword_calls: list[dict] = []

    def keyword(**kwargs):
        keyword_calls.append(kwargs)
        return [RecallHit(_id(1), 1, 0.8)]

    package = _service(repo, semantic=lambda **_: [], keyword=keyword).retrieve(
        tenant_id="default",
        actor_open_id="ou_user",
        query="职场",
        filters={
            "asset_kinds": ["copy"],
            "source_kinds": ["user_adopted"],
            "niches": ["职场"],
            "min_quality": 0.8,
            "updated_after": "2026-07-01T00:00:00Z",
        },
    )

    assert package.retrieval_mode == "keyword_only"
    assert keyword_calls[0]["filters"]["updated_after"].endswith("Z")
    gate = repo.gate_calls[0]
    assert gate["asset_kinds"] == ["copy"]
    assert gate["source_kinds"] == ["user_adopted"]
    assert gate["niches"] == ["职场"]
    assert gate["min_quality"] == pytest.approx(0.8)
    assert gate["updated_after"].tzinfo is not None


def test_graph_neighbors_are_rechecked_by_same_postgres_gate() -> None:
    repo = _Repo([_row(1), _row(2)])

    def graph(**_):
        return {
            "edges": [
                {
                    "source": _id(1),
                    "source_resource_version": 1,
                    "target": _id(2),
                    "target_resource_version": 1,
                    "weight": 0.9,
                },
                {
                    "source": _id(1),
                    "source_resource_version": 1,
                    "target": _id(3),
                    "target_resource_version": 1,
                    "weight": 0.99,
                },
            ]
        }

    package = _service(
        repo,
        semantic=lambda **_: [RecallHit(_id(1), 1, 0.9)],
        keyword=lambda **_: [],
        graph=graph,
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="职场")

    identities = {
        (item.resource_id, item.resource_version) for item in package.evidence
    }
    assert (_id(2), 1) in identities
    assert (_id(3), 1) not in identities
    assert len(repo.gate_calls) == 2
    assert repo.gate_calls[1]["resource_ids"] == [_id(3), _id(2)]
    assert "graph" in package.engines_used


def test_postgres_gate_failure_fails_closed() -> None:
    repo = _Repo([_row(1)], fail_gate=True)
    service = _service(
        repo,
        semantic=lambda **_: [RecallHit(_id(1), 1, 0.9)],
        keyword=lambda **_: [],
    )
    with pytest.raises(RetrievalSecurityGateError) as exc_info:
        service.retrieve(
            tenant_id="default", actor_open_id="ou_user", query="职场"
        )
    assert str(exc_info.value) == "POSTGRES_KNOWLEDGE_GATE_FAILED"
    assert "secret" not in str(exc_info.value).lower()


def test_shadow_reranker_never_changes_online_evidence_order() -> None:
    repo = _Repo([_row(1), _row(2)])
    observations = []
    package = _service(
        repo,
        semantic=lambda **_: [
            RecallHit(_id(1), 1, 0.9),
            RecallHit(_id(2), 1, 0.8),
        ],
        keyword=lambda **_: [],
        shadow_reranker=lambda **_: [(_id(2), 1), (_id(1), 1)],
        shadow_observer=lambda **kwargs: observations.append(kwargs),
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="职场")

    assert [item.resource_id for item in package.evidence] == [_id(1), _id(2)]
    assert observations[0]["observation"].shadow_order[0] == (_id(2), 1)
    assert observations[0]["task_type"] == "general"


@given(score=st.floats(min_value=-1, max_value=1, allow_nan=False, allow_infinity=False))
def test_semantic_floor_is_monotonic(score: float) -> None:
    repo = _Repo([_row(1)])
    package = _service(
        repo,
        semantic=lambda **_: [RecallHit(_id(1), 1, score)],
        keyword=lambda **_: [],
        floor=0.5,
    ).retrieve(tenant_id="default", actor_open_id="ou_user", query="q")
    assert bool(package.evidence) is (score >= 0.5)


class _Response:
    status_code = 200

    def __init__(self, dimensions: int):
        self.dimensions = dimensions

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"data": [{"embedding": [0.1] * self.dimensions}]}


def test_embed_query_uses_instruction_and_requested_dimensions() -> None:
    calls: list[dict] = []
    config = EmbeddingProviderConfig(
        state="enabled",
        reason_code=None,
        base_url="https://embedding.invalid/v1",
        api_key="secret",
        model="text-embedding",
        config_version="test",
        dimensions=3,
        timeout_seconds=12.0,
        batch_size=8,
    )

    def post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return _Response(3)

    vector = embed_query(
        "露营",
        config=config,
        query_instruction="检索：{query}",
        post=post,
    )

    assert vector == [0.1, 0.1, 0.1]
    assert calls[0]["json"]["input"] == ["检索：露营"]
    assert calls[0]["json"]["dimensions"] == 3


def test_embed_query_rejects_wrong_dimensions_without_exposing_payload() -> None:
    config = EmbeddingProviderConfig(
        state="enabled",
        reason_code=None,
        base_url="https://embedding.invalid/v1",
        api_key="secret",
        model="text-embedding",
        config_version="test",
        dimensions=3,
        timeout_seconds=12.0,
        batch_size=8,
    )
    with pytest.raises(EmbeddingSearchUnavailable) as exc_info:
        embed_query(
            "隐私查询",
            config=config,
            query_instruction=None,
            post=lambda *_, **__: _Response(2),
        )
    assert str(exc_info.value) == "EMBEDDING_QUERY_BAD_DIMENSIONS"
