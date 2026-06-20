from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import math
from types import SimpleNamespace

import pytest

from data_foundation.graph import expand_graph
from data_foundation.repository import ResourceRepository
from data_foundation.search import _result_from_row, keyword_search, semantic_search


class _User:
    identity = "ou_owner"


class _ServerInfo:
    user = _User()


class _Config:
    server_info = _ServerInfo()


class _FakeRepository:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.active_index = None

    def active_embedding_index(self, tenant_id: str):
        self.calls.append(("active_index", {"tenant_id": tenant_id}))
        return self.active_index

    def keyword_rows(self, **kwargs):
        self.calls.append(("keyword", kwargs))
        return [
            {
                "id": "resource-1",
                "title": "露营装备",
                "summary": None,
                "type": "topic",
                "visibility": "team",
                "score": 0.75,
            }
        ]

    def semantic_rows(self, **kwargs):
        self.calls.append(("semantic", kwargs))
        return [
            {
                "id": "resource-1",
                "title": "露营装备",
                "summary": None,
                "type": "topic",
                "visibility": "team",
                "score": 0.6,
                "chunk_index": 0,
                "chunk_text": "弱匹配",
            },
            {
                "id": "resource-1",
                "title": "露营装备",
                "summary": None,
                "type": "topic",
                "visibility": "team",
                "score": 0.9,
                "chunk_index": 1,
                "chunk_text": "强匹配",
            },
            {
                "id": "resource-2",
                "title": "厨房收纳",
                "summary": None,
                "type": "topic",
                "visibility": "team",
                "score": 0.7,
                "chunk_index": 0,
                "chunk_text": "次匹配",
            },
        ]

    def graph_rows(self, **kwargs):
        self.calls.append(("graph", kwargs))
        return [
            {
                "kind": "node",
                "id": "resource-1",
                "title": "起点",
                "type": "topic",
                "depth": 0,
                "source_resource_id": None,
                "target_resource_id": None,
                "edge_type": None,
                "weight": None,
            },
            {
                "kind": "node",
                "id": "resource-2",
                "title": "终点",
                "type": "topic",
                "depth": 1,
                "source_resource_id": None,
                "target_resource_id": None,
                "edge_type": None,
                "weight": None,
            },
            {
                "kind": "edge",
                "id": None,
                "title": None,
                "type": None,
                "depth": 1,
                "source_resource_id": "resource-1",
                "target_resource_id": "resource-2",
                "edge_type": "LINK",
                "weight": 0.8,
            },
            {
                "kind": "edge",
                "id": None,
                "title": None,
                "type": None,
                "depth": 1,
                "source_resource_id": "resource-1",
                "target_resource_id": "hidden-resource",
                "edge_type": "LINK",
                "weight": 0.8,
            }
        ]


def test_search_result_metadata_distinguishes_source_and_index_freshness():
    source_updated_at = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    indexed_at = datetime(2026, 6, 19, 12, 30, tzinfo=timezone.utc)

    result = _result_from_row(
        {
            "id": "resource-1",
            "title": "露营装备",
            "summary": None,
            "type": "topic",
            "visibility": "team",
            "score": 0.75,
            "source_updated_at": source_updated_at,
            "updated_at": indexed_at,
        }
    )

    assert result.metadata["source_updated_at"] == source_updated_at.isoformat()
    assert result.metadata["indexed_at"] == indexed_at.isoformat()
    assert "updated_at" not in result.metadata


def test_keyword_search_empty_query_returns_empty_without_database_call():
    repo = _FakeRepository()

    assert keyword_search(repo, tenant_id="tenant", actor_open_id="actor", query="  ") == []
    assert repo.calls == []


@pytest.mark.parametrize(("requested", "expected"), [(-2, 1), (0, 1), (8, 8), (99, 20)])
def test_keyword_search_clamps_limit(requested, expected):
    repo = _FakeRepository()

    results = keyword_search(
        repo,
        tenant_id="tenant",
        actor_open_id="actor",
        query="露营",
        limit=requested,
    )

    assert results[0].resource_id == "resource-1"
    assert repo.calls[0][1]["limit"] == expected


@pytest.mark.parametrize(("requested", "expected"), [(-2, 1), (0, 1), (8, 8), (99, 20)])
def test_semantic_search_clamps_limit(requested, expected):
    repo = _FakeRepository()

    semantic_search(
        repo,
        tenant_id="tenant",
        actor_open_id="actor",
        embedding=[0.0] * 1536,
        embedding_model="test",
        top_k=requested,
    )

    assert repo.calls[0][1]["top_k"] == expected


def test_semantic_search_keeps_best_chunk_once_per_resource():
    repo = _FakeRepository()

    results = semantic_search(
        repo,
        tenant_id="tenant",
        actor_open_id="actor",
        embedding=[0.0] * 1536,
        embedding_model="test",
        top_k=10,
    )

    assert [result.resource_id for result in results] == ["resource-1", "resource-2"]
    assert results[0].metadata["chunk_text"] == "强匹配"


@pytest.mark.parametrize("embedding", [[0.0] * 1535, [0.0] * 1537, [math.nan] * 1536, [math.inf] * 1536])
def test_semantic_search_rejects_invalid_embedding(embedding):
    repo = _FakeRepository()

    with pytest.raises(ValueError, match="1536 finite"):
        semantic_search(
            repo,
            tenant_id="tenant",
            actor_open_id="actor",
            embedding=embedding,
            embedding_model="test",
        )

    assert repo.calls == []


def test_semantic_search_rejects_blank_embedding_model():
    repo = _FakeRepository()

    with pytest.raises(ValueError, match="Embedding model"):
        semantic_search(
            repo,
            tenant_id="tenant",
            actor_open_id="actor",
            embedding=[0.0] * 1536,
            embedding_model="  ",
        )

    assert repo.calls == []


@pytest.mark.parametrize(("requested", "expected"), [(-1, 1), (0, 1), (2, 2), (10, 3)])
def test_expand_graph_clamps_hops_and_parameterizes_edge_types(requested, expected):
    repo = _FakeRepository()

    graph = expand_graph(
        repo,
        tenant_id="tenant",
        actor_open_id="actor",
        resource_ids=["resource-1"],
        hops=requested,
        edge_types=["SIMILAR_TO"],
    )

    assert graph.nodes[0].depth == 0
    assert {(edge.source_resource_id, edge.target_resource_id) for edge in graph.edges} == {
        ("resource-1", "resource-2")
    }
    assert repo.calls[0][1]["hops"] == expected
    assert repo.calls[0][1]["edge_types"] == ["SIMILAR_TO"]


def test_expand_graph_empty_start_returns_empty_without_database_call():
    repo = _FakeRepository()

    graph = expand_graph(repo, tenant_id="tenant", actor_open_id="actor", resource_ids=[])

    assert graph.nodes == []
    assert graph.edges == []
    assert repo.calls == []


def _create_resource(
    repo: ResourceRepository,
    *,
    tenant_id: str = "default",
    owner: str = "ou_owner",
    title: str,
    visibility: str = "team",
    content: str = "",
):
    return repo.upsert_resource(
        tenant_id=tenant_id,
        actor_open_id=owner,
        resource_type="topic",
        title=title,
        content_text=content,
        content_json={},
        visibility=visibility,
        owner_open_id=owner,
    )


def _create_embedding_index(conn, *, tenant_id: str = "default", model: str = "test") -> str:
    return str(
        conn.execute(
            """
            insert into embedding_indexes
              (tenant_id, embedding_model, config_version, dimensions, chunker_version, status, activated_at)
            values (%s, %s, '2026-06-20T10:00:00Z-test', 1536, 'text-v1', 'active', now())
            returning id
            """,
            (tenant_id, model),
        ).fetchone()["id"]
    )


def _insert_embedding(
    conn,
    *,
    resource,
    index_id: str,
    chunk_index: int,
    chunk_text: str,
    embedding: list[float],
    model: str = "test",
) -> None:
    vector = "[" + ",".join(str(float(value)) for value in embedding) + "]"
    conn.execute(
        """
        insert into resource_embeddings
          (tenant_id, resource_id, resource_version, embedding_index_id,
           chunk_index, chunk_text, chunker_version, embedding_model, embedding)
        values (%s, %s, %s, %s, %s, %s, 'text-v1', %s, %s::vector)
        """,
        (resource.tenant_id, resource.id, resource.version, index_id, chunk_index, chunk_text, model, vector),
    )


def test_keyword_search_filters_by_query_tenant_and_permission(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    _create_resource(repo, title="露营装备", content="帐篷 天幕 炉具")
    _create_resource(repo, title="私有露营笔记", visibility="private", content="露营")
    _create_resource(repo, tenant_id="other", title="其他租户露营", content="露营")

    results = keyword_search(repo, tenant_id="default", actor_open_id="ou_other", query="露营", limit=10)

    assert [item.title for item in results] == ["露营装备"]
    assert results[0].score > 0


def test_semantic_search_returns_best_chunk_once_per_resource(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first = _create_resource(repo, title="露营装备")
    second = _create_resource(repo, title="厨房收纳")
    query = [1.0] + [0.0] * 1535
    index_id = _create_embedding_index(migrated_conn)
    _insert_embedding(migrated_conn, resource=first, index_id=index_id, chunk_index=0, chunk_text="差匹配", embedding=[0.0, 1.0] + [0.0] * 1534)
    _insert_embedding(migrated_conn, resource=first, index_id=index_id, chunk_index=1, chunk_text="最佳匹配", embedding=query)
    _insert_embedding(migrated_conn, resource=second, index_id=index_id, chunk_index=0, chunk_text="次佳匹配", embedding=[0.8, 0.2] + [0.0] * 1534)

    results = semantic_search(
        repo,
        tenant_id="default",
        actor_open_id="ou_owner",
        embedding=query,
        embedding_model="test",
        top_k=20,
    )

    assert [item.resource_id for item in results] == [first.id, second.id]
    assert results[0].metadata["chunk_text"] == "最佳匹配"


def test_add_edge_rejects_cross_tenant_endpoint(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    source = _create_resource(repo, title="起点")
    target = _create_resource(repo, tenant_id="other", title="异租户终点")

    with pytest.raises(PermissionError):
        repo.add_edge(
            tenant_id="default",
            source_resource_id=source.id,
            target_resource_id=target.id,
            edge_type="SIMILAR_TO",
        )


def test_add_edge_validates_edge_type_and_weight(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    source = _create_resource(repo, title="起点")
    target = _create_resource(repo, title="终点")

    with pytest.raises(ValueError, match="Edge type"):
        repo.add_edge(
            tenant_id="default",
            source_resource_id=source.id,
            target_resource_id=target.id,
            edge_type=" ",
        )
    with pytest.raises(ValueError, match="finite"):
        repo.add_edge(
            tenant_id="default",
            source_resource_id=source.id,
            target_resource_id=target.id,
            edge_type="SIMILAR_TO",
            weight=math.inf,
        )


def test_expand_graph_is_cycle_safe_deduplicated_and_permission_filtered(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    start = _create_resource(repo, title="起点")
    middle = _create_resource(repo, title="中点")
    end = _create_resource(repo, title="终点")
    hidden = _create_resource(repo, title="隐藏", visibility="private")
    for source, target, edge_type in [
        (start, middle, "LINK"),
        (middle, end, "LINK"),
        (end, start, "LINK"),
        (middle, hidden, "LINK"),
        (start, hidden, "IGNORED"),
    ]:
        repo.add_edge(
            tenant_id="default",
            source_resource_id=source.id,
            target_resource_id=target.id,
            edge_type=edge_type,
        )

    graph = expand_graph(
        repo,
        tenant_id="default",
        actor_open_id="ou_other",
        resource_ids=[start.id],
        hops=3,
        edge_types=["LINK"],
    )

    assert {node.resource_id: node.depth for node in graph.nodes} == {start.id: 0, middle.id: 1, end.id: 2}
    assert {(edge.source_resource_id, edge.target_resource_id) for edge in graph.edges} == {
        (start.id, middle.id),
        (middle.id, end.id),
    }


def test_expand_graph_invisible_start_returns_nothing(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    hidden = _create_resource(repo, title="隐藏起点", visibility="private")
    target = _create_resource(repo, title="可见终点")
    repo.add_edge(
        tenant_id="default",
        source_resource_id=hidden.id,
        target_resource_id=target.id,
        edge_type="LINK",
    )

    graph = expand_graph(
        repo,
        tenant_id="default",
        actor_open_id="ou_other",
        resource_ids=[hidden.id],
    )

    assert graph.nodes == []
    assert graph.edges == []


def test_tools_reject_missing_identity():
    from data_foundation.tools import search_resources

    with pytest.raises(PermissionError, match="Missing LangGraph user identity"):
        search_resources.func("露营", config=None)


def test_search_tool_returns_structured_json(monkeypatch, migrated_conn):
    from data_foundation import tools as df_tools

    repo = ResourceRepository(migrated_conn)
    repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="topic",
        title="露营装备",
        content_text="帐篷 天幕",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )

    @contextmanager
    def repository():
        yield ResourceRepository(migrated_conn)

    monkeypatch.setattr(df_tools, "_repository", repository)

    result = df_tools.search_resources.func("露营", limit=10, config=_Config())

    assert result["ok"] is True
    assert result["results"][0]["title"] == "露营装备"
    assert "content_text" not in result["results"][0]


def test_semantic_search_tool_falls_back_to_keyword_when_no_active_index(monkeypatch):
    from data_foundation import tools as df_tools

    repo = _FakeRepository()

    @contextmanager
    def repository():
        yield repo

    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setenv("LLM_API_KEY", "must-not-be-used")
    monkeypatch.setattr(
        df_tools,
        "_embed_query",
        lambda *_args, **_kwargs: pytest.fail("semantic fallback must not call embedding provider"),
        raising=False,
    )

    result = df_tools.semantic_search_resources.func("露营", top_k=10, config=_Config())

    assert result["ok"] is True
    assert result["mode"] == "keyword_fallback"
    assert result["fallback_reason"] == "NO_ACTIVE_EMBEDDING_INDEX"
    assert [call[0] for call in repo.calls] == ["active_index", "keyword"]


def test_semantic_search_tool_requires_explicit_embedding_base_url(monkeypatch):
    from data_foundation import tools as df_tools

    repo = _FakeRepository()
    repo.active_index = SimpleNamespace(embedding_model="embedding-model")

    @contextmanager
    def repository():
        yield repo

    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setenv("XHS_EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.delenv("XHS_EMBEDDING_BASE_URL", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://chat.example/v1")

    result = df_tools.semantic_search_resources.func("露营", top_k=10, config=_Config())

    assert result["ok"] is True
    assert result["mode"] == "keyword_fallback"
    assert result["fallback_reason"] == "EMBEDDING_QUERY_CONFIG_MISSING"
    assert [call[0] for call in repo.calls] == ["active_index", "keyword"]


def test_get_resource_tool_distinguishes_source_and_index_freshness(monkeypatch):
    from data_foundation import tools as df_tools

    source_updated_at = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    indexed_at = datetime(2026, 6, 19, 12, 30, tzinfo=timezone.utc)
    resource = SimpleNamespace(
        id="resource-1",
        type="topic",
        title="露营装备",
        summary=None,
        content_text="帐篷 天幕",
        content_json={},
        version=1,
        source_updated_at=source_updated_at,
        updated_at=indexed_at,
    )

    @contextmanager
    def repository():
        yield SimpleNamespace(get_resource=lambda *_args: resource)

    monkeypatch.setattr(df_tools, "_repository", repository)

    result = df_tools.get_resource.func(resource.id, config=_Config())

    assert result["resource"]["source_updated_at"] == source_updated_at.isoformat()
    assert result["resource"]["indexed_at"] == indexed_at.isoformat()
    assert "updated_at" not in result["resource"]
