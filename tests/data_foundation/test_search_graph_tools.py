from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import math
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.fernet import Fernet

from data_foundation.graph import expand_graph
from data_foundation.processors.embedding import EmbeddingProviderConfig
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
        rows = []
        for rid in ids:
            rows.append({
                "id": rid,
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
                "kind": "node", "id": "resource-1", "title": "起点", "type": "topic", "depth": 0,
                "source_resource_id": None, "target_resource_id": None, "edge_type": None, "weight": None,
            },
            {
                "kind": "node", "id": "resource-2", "title": "终点", "type": "topic", "depth": 1,
                "source_resource_id": None, "target_resource_id": None, "edge_type": None, "weight": None,
            },
            {
                "kind": "edge", "id": None, "title": None, "type": None, "depth": 1,
                "source_resource_id": "resource-1", "target_resource_id": "resource-2",
                "edge_type": "LINK", "weight": 0.8,
            },
            {
                "kind": "edge", "id": None, "title": None, "type": None, "depth": 1,
                "source_resource_id": "resource-1", "target_resource_id": "hidden-resource",
                "edge_type": "LINK", "weight": 0.8,
            },
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


def test_expand_graph_queries_falkor_and_filters_by_permission(monkeypatch):
    repo = _FakeRepository()  # readable_rows_by_ids returns all passed ids as visible
    fake_graph = MagicMock()
    fake_graph.expand.return_value = (
        [{"id": "resource-1", "title": "起点", "type": "topic"},
         {"id": "resource-2", "title": "终点", "type": "topic"}],
        [{"source": "resource-1", "target": "resource-2", "edge_type": "derived_from", "weight": 1.0}],
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
        hops=2,
        edge_types=["derived_from"],
    )

    assert {n.resource_id for n in graph.nodes} == {"resource-1", "resource-2"}
    assert {(e.source_resource_id, e.target_resource_id) for e in graph.edges} == {
        ("resource-1", "resource-2")
    }
    # hops 透传(clamp 在 1..3)
    assert fake_graph.expand.call_args.kwargs["hops"] == 2
    assert fake_graph.expand.call_args.kwargs["edge_types"] == ["derived_from"]


def test_expand_graph_filters_out_invisible_nodes(monkeypatch):
    class _PartialVisibleRepo(_FakeRepository):
        def readable_rows_by_ids(self, **kwargs):
            # 只有 resource-1 可见,resource-2 被权限过滤
            return [{"id": "resource-1", "title": "起点", "summary": None, "type": "topic",
                     "visibility": "team", "score": 1.0, "source_updated_at": None, "updated_at": None}]

    repo = _PartialVisibleRepo()
    fake_graph = MagicMock()
    fake_graph.expand.return_value = (
        [{"id": "resource-1", "title": "起点", "type": "topic"},
         {"id": "resource-2", "title": "隐藏", "type": "topic"}],
        [{"source": "resource-1", "target": "resource-2", "edge_type": "derived_from", "weight": 1.0}],
    )
    monkeypatch.setenv("XHS_FALKOR_URL", "redis://127.0.0.1:6379")
    monkeypatch.setattr(
        "data_foundation.falkor_client.FalkorResourceGraph.from_config",
        classmethod(lambda cls, cfg: fake_graph),
    )

    graph = expand_graph(repo, tenant_id="default", actor_open_id="actor", resource_ids=["resource-1"])

    assert {n.resource_id for n in graph.nodes} == {"resource-1"}
    # 含被过滤节点的边也被剔除
    assert graph.edges == []


def test_expand_graph_empty_start_returns_empty_without_engine_call():
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


def test_tools_reject_missing_identity():
    from data_foundation.tools import search_resources

    with pytest.raises(PermissionError, match="Missing LangGraph user identity"):
        search_resources.func("露营", config=None)


def test_search_tool_returns_structured_json(monkeypatch):
    from data_foundation import tools as df_tools

    repo = _FakeRepository()

    @contextmanager
    def repository():
        yield repo

    fake_index = MagicMock()
    fake_index.search.return_value = [("resource-1", 0.9)]
    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setenv("XHS_MEILI_URL", "http://127.0.0.1:7700")
    monkeypatch.setenv("XHS_MEILI_KEY", "k")
    monkeypatch.setattr(
        "data_foundation.meili_client.MeiliResourceIndex.from_config",
        classmethod(lambda cls, cfg: fake_index),
    )

    result = df_tools.search_resources.func("露营", limit=10, config=_Config())

    assert result["ok"] is True
    assert result["results"][0]["resource_id"] == "resource-1"
    assert result["results"][0]["title"] == "露营装备"
    assert "content_text" not in result["results"][0]
    fake_index.search.assert_called_once()


def test_search_tool_returns_error_when_meili_unavailable(monkeypatch):
    from data_foundation import tools as df_tools

    monkeypatch.delenv("XHS_MEILI_URL", raising=False)
    monkeypatch.delenv("XHS_MEILI_KEY", raising=False)

    result = df_tools.search_resources.func("露营", limit=10, config=_Config())

    assert result["ok"] is False
    assert result["error"] == "MEILI_UNAVAILABLE"


def test_semantic_search_tool_falls_back_to_fulltext_when_no_active_index(monkeypatch):
    from data_foundation import tools as df_tools

    repo = _FakeRepository()

    @contextmanager
    def repository():
        yield repo

    fake_index = MagicMock()
    fake_index.search.return_value = [("resource-9", 0.5)]
    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setenv("XHS_MEILI_URL", "http://127.0.0.1:7700")
    monkeypatch.setenv("XHS_MEILI_KEY", "k")
    monkeypatch.setattr(
        "data_foundation.meili_client.MeiliResourceIndex.from_config",
        classmethod(lambda cls, cfg: fake_index),
    )
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
    assert result["results"][0]["resource_id"] == "resource-9"


def test_semantic_search_tool_uses_active_index_historical_profile(monkeypatch, tmp_path):
    from config_center import ConfigCenter
    from data_foundation import tools as df_tools

    path = tmp_path / "config-center.enc"
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("XHS_CONFIG_CENTER_PATH", str(path))
    monkeypatch.setenv("XHS_CONFIG_ENCRYPTION_KEY", key)
    center = ConfigCenter(path=path, encryption_key=key)
    first = center.save(
        actor_open_id="ou_admin",
        updates={
            "XHS_EMBEDDING_BASE_URL": "https://old.example/v1",
            "XHS_EMBEDDING_API_KEY": "old-key",
            "XHS_EMBEDDING_MODEL": "model-a",
            "XHS_EMBEDDING_DIMENSIONS": "1536",
            "XHS_EMBEDDING_BATCH_SIZE": "32",
            "XHS_EMBEDDING_TIMEOUT_SECONDS": "11",
        },
    )
    center.save(
        actor_open_id="ou_admin",
        updates={
            "XHS_EMBEDDING_BASE_URL": "https://new.example/v1",
            "XHS_EMBEDDING_API_KEY": "new-key",
            "XHS_EMBEDDING_MODEL": "model-b",
        },
    )
    repo = _FakeRepository()
    repo.active_index = SimpleNamespace(
        embedding_model="model-a",
        dimensions=1536,
        config_version=first.version,
    )

    @contextmanager
    def repository():
        yield repo

    captured = {}

    def embed(query, *, config, query_instruction):
        captured["query"] = query
        captured["config"] = config
        captured["query_instruction"] = query_instruction
        return [0.1] * 1536

    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setattr(df_tools, "_embed_query", embed)

    result = df_tools.semantic_search_resources.func("露营", top_k=10, config=_Config())

    assert result["ok"] is True
    assert result["mode"] == "semantic"
    assert captured["query"] == "露营"
    assert captured["config"].model == "model-a"
    assert captured["config"].base_url == "https://old.example/v1"
    assert captured["config"].api_key == "old-key"
    assert captured["config"].timeout_seconds == 11.0
    # model-a 非 Qwen3 → 无指令前缀(检索期策略从当前配置解析,当前未显式配置)
    assert captured["query_instruction"] is None
    assert [call[0] for call in repo.calls] == ["active_index", "semantic", "bulk_performance_metrics"]


def test_semantic_search_empty_candidates_falls_back_to_fulltext(monkeypatch):
    """P1 回归:active index 存在但语义候选集为空(典型:刚 save 后 embedding 还没补,
    而 meili 已可命中),必须降级到全文,**不得**误报 insufficient_relevance。"""
    from data_foundation import tools as df_tools

    repo = _FakeRepository()
    repo.active_index = SimpleNamespace(
        embedding_model="model-a", dimensions=1536, config_version="v1",
    )
    # 语义候选为空
    monkeypatch.setattr(repo, "semantic_rows", lambda **kw: [])

    @contextmanager
    def repository():
        yield repo

    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setattr(
        df_tools, "_embedding_query_config_for_index",
        lambda idx: SimpleNamespace(model="model-a", base_url="x", api_key="k",
                                    dimensions=1536, timeout_seconds=10, state="enabled"),
    )
    monkeypatch.setattr(df_tools, "_embed_query", lambda *a, **k: [0.1] * 1536)
    # 全文降级路径:让 search_resources 返回有结果
    monkeypatch.setattr(
        df_tools.search_resources, "func",
        lambda query, limit=10, config=None: {"ok": True, "results": [{"resource_id": "r-fts"}]},
    )

    result = df_tools.semantic_search_resources.func("露营", top_k=10, config=_Config())

    assert result["ok"] is True
    assert result["mode"] == "keyword_fallback"
    assert result["fallback_reason"] == "NO_SEMANTIC_CANDIDATES"
    assert result["results"] == [{"resource_id": "r-fts"}]


def test_embed_query_sends_requested_dimensions(monkeypatch):
    from data_foundation import tools as df_tools

    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.1] * 1536}]}

    def post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setenv("XHS_EMBEDDING_BASE_URL", "https://embedding.example/v1")
    monkeypatch.setenv("XHS_EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setattr(df_tools.httpx, "post", post)

    vector = df_tools._embed_query(
        "露营",
        config=EmbeddingProviderConfig(
            base_url="https://embedding.example/v1",
            api_key="embedding-key",
            model="embedding-model",
            config_version="cfg-active",
            dimensions=1536,
            timeout_seconds=13.0,
        ),
        query_instruction=None,
    )

    assert len(vector) == 1536
    assert captured["url"] == "https://embedding.example/v1/embeddings"
    assert captured["json"] == {
        "model": "embedding-model",
        "input": ["露营"],
        "dimensions": 1536,
    }
    assert captured["timeout"] == 13.0


def test_embed_query_injects_instruction_prefix_when_provided(monkeypatch):
    from data_foundation import tools as df_tools

    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.1] * 1536}]}

    def post(url, **kwargs):
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(df_tools.httpx, "post", post)

    df_tools._embed_query(
        "露营装备",
        config=EmbeddingProviderConfig(
            base_url="https://e/v1", api_key="k", model="Qwen/Qwen3-Embedding-4B",
            config_version="cfg", dimensions=1536,
        ),
        query_instruction="Instruct: 找小红书素材\nQuery: {query}",
    )
    # 指令前缀被注入,query 占位符被替换;裸 query 不再直接作为 input
    assert captured["json"]["input"] == ["Instruct: 找小红书素材\nQuery: 露营装备"]


def test_semantic_search_tool_returns_insufficient_relevance_below_floor(monkeypatch):
    from data_foundation import tools as df_tools

    class _LowScoreRepo(_FakeRepository):
        def semantic_rows(self, **kwargs):
            self.calls.append(("semantic", kwargs))
            return [{
                "id": "resource-1", "title": "护肤", "summary": None, "type": "topic",
                "visibility": "team", "score": 0.46, "chunk_index": 0, "chunk_text": "弱匹配",
            }]

    repo = _LowScoreRepo()
    repo.active_index = SimpleNamespace(embedding_model="model-a", dimensions=1536, config_version="cfg")

    @contextmanager
    def repository():
        yield repo

    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setattr(df_tools, "_embedding_query_config_for_index",
                        lambda idx: EmbeddingProviderConfig(base_url="https://e/v1", api_key="k",
                                                            model="model-a", config_version="cfg", dimensions=1536))
    monkeypatch.setattr(df_tools, "_embed_query", lambda *a, **k: [0.1] * 1536)
    monkeypatch.setattr("data_foundation.config.current_relevance_floor", lambda: 0.50)
    monkeypatch.setattr("data_foundation.config.resolve_query_instruction", lambda model: None)

    result = df_tools.semantic_search_resources.func("露营装备", top_k=10, config=_Config())

    assert result["ok"] is True
    assert result["mode"] == "insufficient_relevance"
    assert result["results"] == []
    assert result["top_score"] == 0.46
    assert result["threshold"] == 0.50
    # 未降级到全文(不调用 bulk_performance_metrics / readable_by_ids)
    assert [c[0] for c in repo.calls] == ["active_index", "semantic"]


def test_semantic_search_tool_floor_is_configurable(monkeypatch):
    from data_foundation import tools as df_tools

    class _MidScoreRepo(_FakeRepository):
        def semantic_rows(self, **kwargs):
            self.calls.append(("semantic", kwargs))
            return [{
                "id": "resource-1", "title": "护肤", "summary": None, "type": "topic",
                "visibility": "team", "score": 0.60, "chunk_index": 0, "chunk_text": "匹配",
            }]

    repo = _MidScoreRepo()
    repo.active_index = SimpleNamespace(embedding_model="model-a", dimensions=1536, config_version="cfg")

    @contextmanager
    def repository():
        yield repo

    monkeypatch.setattr(df_tools, "_repository", repository)
    monkeypatch.setattr(df_tools, "_embedding_query_config_for_index",
                        lambda idx: EmbeddingProviderConfig(base_url="https://e/v1", api_key="k",
                                                            model="model-a", config_version="cfg", dimensions=1536))
    monkeypatch.setattr(df_tools, "_embed_query", lambda *a, **k: [0.1] * 1536)
    monkeypatch.setattr("data_foundation.config.resolve_query_instruction", lambda model: None)

    # 阈值 0.50:0.60 >= 0.50 → semantic
    monkeypatch.setattr("data_foundation.config.current_relevance_floor", lambda: 0.50)
    assert df_tools.semantic_search_resources.func("护肤", top_k=10, config=_Config())["mode"] == "semantic"

    # 配置覆盖阈值到 0.70:0.60 < 0.70 → insufficient_relevance(按当前配置生效)
    monkeypatch.setattr("data_foundation.config.current_relevance_floor", lambda: 0.70)
    out = df_tools.semantic_search_resources.func("护肤", top_k=10, config=_Config())
    assert out["mode"] == "insufficient_relevance"
    assert out["threshold"] == 0.70


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

    @contextmanager
    def repository():
        yield SimpleNamespace(get_resource=lambda *_args: resource)

    monkeypatch.setattr(df_tools, "_repository", repository)

    result = df_tools.get_resource.func(resource.id, config=_Config())

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
        result = df_tools.get_resource.func(bad, config=_Config())
        assert result == {"ok": False, "error": "Resource not found or not permitted"}
    assert called["hit"] is False  # 非法 id 在进 repo 前就被挡下
