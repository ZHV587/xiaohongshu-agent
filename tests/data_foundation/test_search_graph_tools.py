from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import math
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from data_foundation.graph import expand_graph
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.search import _result_from_row, semantic_search


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

    def bulk_performance_metrics(self, tenant_id: str, resource_ids: list[str]):
        self.calls.append(("bulk_performance_metrics", {"tenant_id": tenant_id, "resource_ids": resource_ids}))
        return {rid: [] for rid in resource_ids}

    def readable_rows_by_ids(self, **kwargs):
        self.calls.append(("readable_by_ids", kwargs))
        ids = kwargs.get("resource_ids") or []
        versions = kwargs.get("resource_versions") or [1] * len(ids)
        rows = []
        for rid, version in zip(ids, versions):
            rows.append({
                "id": rid,
                "resource_version": version,
                "title": "露营装备",
                "summary": None,
                "type": "topic",
                "visibility": "team",
                "score": 1.0,
                "source_updated_at": None,
                "updated_at": None,
            })
        return rows

    def semantic_rows(self, **kwargs):
        self.calls.append(("semantic", kwargs))
        return [
            {
                "id": "resource-1",
                "resource_version": 1,
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
                "resource_version": 1,
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
                "resource_version": 1,
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
                "kind": "node", "id": "resource-1", "resource_version": 1,
                "title": "起点", "type": "topic", "depth": 0,
                "source_resource_id": None, "source_resource_version": None,
                "target_resource_id": None, "target_resource_version": None,
                "edge_type": None, "weight": None,
            },
            {
                "kind": "node", "id": "resource-2", "resource_version": 1,
                "title": "终点", "type": "topic", "depth": 1,
                "source_resource_id": None, "source_resource_version": None,
                "target_resource_id": None, "target_resource_version": None,
                "edge_type": None, "weight": None,
            },
            {
                "kind": "edge", "id": None, "resource_version": None,
                "title": None, "type": None, "depth": 1,
                "source_resource_id": "resource-1", "source_resource_version": 1,
                "target_resource_id": "resource-2", "target_resource_version": 1,
                "edge_type": "LINK", "weight": 0.8,
            },
            {
                "kind": "edge", "id": None, "resource_version": None,
                "title": None, "type": None, "depth": 1,
                "source_resource_id": "resource-1", "source_resource_version": 1,
                "target_resource_id": "hidden-resource", "target_resource_version": 1,
                "edge_type": "LINK", "weight": 0.8,
            },
        ]


def test_search_result_metadata_distinguishes_source_and_index_freshness():
    source_updated_at = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    indexed_at = datetime(2026, 6, 19, 12, 30, tzinfo=timezone.utc)

    result = _result_from_row(
        {
            "id": "resource-1",
            "resource_version": 3,
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
    assert result.metadata["resource_version"] == 3
    assert "updated_at" not in result.metadata


@pytest.mark.parametrize(("requested", "expected"), [(-2, 1), (0, 1), (8, 8), (99, 99), (150, 100)])
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
    assert [result.metadata["resource_version"] for result in results] == [1, 1]


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


def test_expand_graph_queries_falkor_and_filters_by_permission(monkeypatch):
    repo = _FakeRepository()  # readable_rows_by_ids returns all passed ids as visible
    fake_graph = MagicMock()
    fake_graph.expand.return_value = (
        [{"id": "resource-1", "resource_version": 2, "title": "起点", "type": "topic"},
         {"id": "resource-2", "resource_version": 4, "title": "终点", "type": "topic"}],
        [{
            "source": "resource-1",
            "source_resource_version": 2,
            "target": "resource-2",
            "target_resource_version": 4,
            "edge_type": "derived_from",
            "weight": 1.0,
            "properties": {"reason": "same_hook"},
        }],
    )
    monkeypatch.setenv("XHS_FALKOR_URL", "redis://127.0.0.1:6379")
    monkeypatch.setenv("XHS_FALKOR_GRAPH", "xhs")
    monkeypatch.setattr(
        "data_foundation.falkor_client.FalkorResourceGraph.from_config",
        classmethod(lambda cls, cfg: fake_graph),
    )

    graph = expand_graph(
        repo,
        tenant_id="default",
        actor_open_id="actor",
        resource_ids=["resource-1"],
        resource_versions=[2],
        edge_types=["derived_from"],
    )

    assert {n.resource_id for n in graph.nodes} == {"resource-1", "resource-2"}
    assert {n.resource_version for n in graph.nodes} == {2, 4}
    assert {(e.source_resource_id, e.target_resource_id) for e in graph.edges} == {
        ("resource-1", "resource-2")
    }
    assert graph.edges[0].source_resource_version == 2
    assert graph.edges[0].target_resource_version == 4
    assert graph.edges[0].properties == {"reason": "same_hook"}
    assert fake_graph.expand.call_args.kwargs["resource_versions"] == [2]
    assert fake_graph.expand.call_args.kwargs["edge_types"] == ["derived_from"]
    hydrate_call = next(call for call in repo.calls if call[0] == "readable_by_ids")
    assert hydrate_call[1]["resource_versions"] == [2, 4]


def test_expand_graph_filters_out_invisible_nodes(monkeypatch):
    class _PartialVisibleRepo(_FakeRepository):
        def readable_rows_by_ids(self, **kwargs):
            assert kwargs["resource_versions"] == [1, 1]
            # 只有 resource-1 可见,resource-2 被权限过滤
            return [{"id": "resource-1", "resource_version": 1,
                     "title": "起点", "summary": None, "type": "topic",
                     "visibility": "team", "score": 1.0, "source_updated_at": None, "updated_at": None}]

    repo = _PartialVisibleRepo()
    fake_graph = MagicMock()
    fake_graph.expand.return_value = (
        [{"id": "resource-1", "resource_version": 1, "title": "起点", "type": "topic"},
         {"id": "resource-2", "resource_version": 1, "title": "隐藏", "type": "topic"}],
        [{
            "source": "resource-1",
            "source_resource_version": 1,
            "target": "resource-2",
            "target_resource_version": 1,
            "edge_type": "derived_from",
            "weight": 1.0,
            "properties": {},
        }],
    )
    monkeypatch.setenv("XHS_FALKOR_URL", "redis://127.0.0.1:6379")
    monkeypatch.setattr(
        "data_foundation.falkor_client.FalkorResourceGraph.from_config",
        classmethod(lambda cls, cfg: fake_graph),
    )

    graph = expand_graph(
        repo, tenant_id="default", actor_open_id="actor",
        resource_ids=["resource-1"], resource_versions=[1],
    )

    assert {n.resource_id for n in graph.nodes} == {"resource-1"}
    # 含被过滤节点的边也被剔除
    assert graph.edges == []


def test_expand_graph_empty_start_returns_empty_without_engine_call():
    repo = _FakeRepository()

    graph = expand_graph(
        repo, tenant_id="tenant", actor_open_id="actor",
        resource_ids=[], resource_versions=[],
    )

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
        values (%s, %s, %s, %s, %s, %s, 'text-v1', %s, %s::public.vector)
        """,
        (resource.tenant_id, resource.id, resource.version, index_id, chunk_index, chunk_text, model, vector),
    )


def test_readable_rows_by_ids_filters_by_permission(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    visible = _create_resource(repo, title="露营装备", content="帐篷 天幕 炉具")
    private = _create_resource(repo, title="私有露营笔记", visibility="private", content="露营")

    rows = repo.readable_rows_by_ids(
        tenant_id="default", actor_open_id="ou_other",
        resource_ids=[private.id, visible.id],
    )

    assert [str(r["id"]) for r in rows] == [visible.id]


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
            source_resource_version=int(source.version),
            target_resource_id=target.id,
            target_resource_version=int(target.version),
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
            source_resource_version=int(source.version),
            target_resource_id=target.id,
            target_resource_version=int(target.version),
            edge_type=" ",
        )
    with pytest.raises(ValueError, match="finite"):
        repo.add_edge(
            tenant_id="default",
            source_resource_id=source.id,
            source_resource_version=int(source.version),
            target_resource_id=target.id,
            target_resource_version=int(target.version),
            edge_type="SIMILAR_TO",
            weight=math.inf,
        )


def test_get_resource_tool_distinguishes_source_and_index_freshness(monkeypatch):
    from data_foundation import tools as df_tools

    source_updated_at = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    indexed_at = datetime(2026, 6, 19, 12, 30, tzinfo=timezone.utc)
    resource = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        type="topic",
        title="露营装备",
        summary=None,
        content_text="帐篷 天幕",
        content_json={},
        version=1,
        source_updated_at=source_updated_at,
        updated_at=indexed_at,
    )

    exact_reads = []

    def get_exact(tenant_id, actor_open_id, resource_id, resource_version):
        exact_reads.append((tenant_id, actor_open_id, resource_id, resource_version))
        return resource

    @contextmanager
    def repository():
        yield SimpleNamespace(get_resource_for_knowledge=get_exact)

    monkeypatch.setattr(df_tools, "_repository", repository)

    result = df_tools.get_resource.func(resource.id, 1, config=_Config())

    assert exact_reads == [("default", "ou_owner", resource.id, 1)]
    assert result["resource"]["version"] == 1
    assert result["resource"]["source_updated_at"] == source_updated_at.isoformat()
    assert result["resource"]["indexed_at"] == indexed_at.isoformat()
    assert "updated_at" not in result["resource"]


def test_get_resource_tool_rejects_non_uuid_without_db_hit(monkeypatch):
    """P1 回归:LLM 传幻觉 id/标题(非 UUID)时返回 not found,不得让 22P02 invalid uuid
    冒泡;且不应触达 repo(where r.id=%s 会在 PG 侧 cast 崩)。"""
    from data_foundation import tools as df_tools

    called = {"hit": False}

    @contextmanager
    def repository():
        called["hit"] = True
        yield SimpleNamespace(get_resource=lambda *_a: None)

    monkeypatch.setattr(df_tools, "_repository", repository)

    for bad in ("generated-1", "露营装备", "", "not-a-uuid"):
        result = df_tools.get_resource.func(bad, 1, config=_Config())
        assert result == {"ok": False, "error": "Resource not found or not permitted"}
    assert called["hit"] is False  # 非法 id 在进 repo 前就被挡下


@pytest.mark.parametrize("bad_version", [None, 0, -1, True, 1.5, "1"])
def test_get_resource_tool_rejects_missing_or_invalid_exact_version(monkeypatch, bad_version):
    from data_foundation import tools as df_tools

    @contextmanager
    def repository():
        pytest.fail("invalid exact versions must be rejected before opening the repository")
        yield

    monkeypatch.setattr(df_tools, "_repository", repository)
    with pytest.raises(ValueError, match="resource_version"):
        df_tools.get_resource.func(
            "11111111-1111-1111-1111-111111111111",
            bad_version,
            config=_Config(),
        )
