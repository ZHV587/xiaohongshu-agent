from unittest.mock import MagicMock
import pytest
from data_foundation.falkor_client import FalkorResourceGraph


def _graph_with():
    g = MagicMock()
    return FalkorResourceGraph(graph=g), g


def test_merge_node_uses_merge_with_id():
    fg, g = _graph_with()
    fg.merge_node({
        "id": "r1", "tenant_id": "default", "type": "feishu_base_record",
        "title": "T", "resource_version": 3,
    })
    cypher, params = g.query.call_args[0][0], g.query.call_args[0][1]
    assert "MERGE" in cypher and ":Resource" in cypher
    assert params["id"] == "r1" and params["title"] == "T"
    assert "r.resource_version=$resource_version" in cypher
    assert params["resource_version"] == 3


def test_merge_edge_merges_both_endpoints_as_placeholder():
    fg, g = _graph_with()
    fg.merge_edge(source_id="a", target_id="b", edge_type="derived_from", weight=1.0,
                  properties={"source_resource_version": 2, "target_resource_version": 4},
                  tenant_id="default")
    cypher, params = g.query.call_args[0][0], g.query.call_args[0][1]
    # 两端都 MERGE(target 占位)+ 边 MERGE,共 >=3 个 MERGE
    assert cypher.count("MERGE") >= 3
    # edge_type 作参数传入(变长路径查询用统一 :REL 标签 + edge_type 属性)
    assert params["etype"] == "derived_from"
    assert params["sid"] == "a" and params["tid"] == "b"
    assert params["source_version"] == 2 and params["target_version"] == 4
    assert "source_resource_version: $source_version" in cypher


def test_merge_edge_placeholder_nodes_get_tenant_on_create():
    """占位节点必须 ON CREATE SET tenant_id:expand/count 都按 tenant 过滤,无 tenant 的
    占位节点在补属性任务跑完前永远召不回(线上曾积累 12 个"隐形"节点)。"""
    fg, g = _graph_with()
    fg.merge_edge(source_id="a", target_id="b", edge_type="derived_from", weight=1.0,
                  properties={"source_resource_version": 2, "target_resource_version": 4},
                  tenant_id="default")
    cypher, params = g.query.call_args[0][0], g.query.call_args[0][1]
    # 两端各带一次 ON CREATE SET(只在新建时写,不覆盖已有真实属性)
    assert cypher.count("ON CREATE SET") == 2


def test_delete_outgoing_version_edges_is_exact_and_tenant_scoped():
    fg, g = _graph_with()

    fg.delete_outgoing_version_edges(
        source_id="a", source_resource_version=3, tenant_id="default"
    )

    cypher, params = g.query.call_args[0]
    assert "rel.source_resource_version = $version" in cypher
    assert "rel.source_resource_version IS NULL" in cypher
    assert "s.tenant_id = $tenant" in cypher
    assert params == {"id": "a", "tenant": "default", "version": 3}
    assert "tenant_id = $tenant" in cypher
    assert params["tenant"] == "default"


def test_expand_returns_nodes_and_edges():
    fg, g = _graph_with()
    g.query.return_value.result_set = [
        [
            "a", "T-a", "feishu_base_record", 2,
            "b", "T-b", "feishu_base_record", 4,
            "derived_from", 1.0,
            {
                "edge_type": "derived_from",
                "weight": 1.0,
                "source_resource_version": 2,
                "target_resource_version": 4,
                "reason": "same_hook",
            },
        ]
    ]
    nodes, edges = fg.expand(
        resource_ids=["a"], resource_versions=[2], edge_types=None, tenant_id="default"
    )
    assert any(n["id"] == "a" for n in nodes)
    assert next(n for n in nodes if n["id"] == "a")["resource_version"] == 2
    edge = next(e for e in edges if e["source"] == "a" and e["target"] == "b")
    assert edge["source_resource_version"] == 2
    assert edge["target_resource_version"] == 4
    assert edge["properties"] == {
        "source_resource_version": 2,
        "target_resource_version": 4,
        "reason": "same_hook",
    }


def test_expand_is_undirected_and_scoped_to_exact_seed_version():
    """一跳遍历无向，但入口必须用关系端点版本锁定，不得混入同 ID 的历史版本边。"""
    fg, g = _graph_with()
    g.query.return_value.result_set = []
    fg.expand(resource_ids=["a"], resource_versions=[3], edge_types=None, tenant_id="default")
    cypher, params = g.query.call_args[0]
    assert "-[rel:REL]-" in cypher
    assert "]->" not in cypher
    assert "rel.source_resource_version = $versions[i]" in cypher
    assert "rel.target_resource_version = $versions[i]" in cypher
    assert "rel.source_resource_version IS NOT NULL" in cypher
    assert "rel.target_resource_version IS NOT NULL" in cypher
    assert params["versions"] == [3]


def test_expand_keeps_same_relationship_type_for_distinct_exact_versions():
    fg, g = _graph_with()
    base = [
        "a", "A", "generated_copy", 3,
        "b", "B", "xhs_note", 5,
        "imitated_from", 1.0,
    ]
    g.query.return_value.result_set = [
        [*base, {"source_resource_version": 3, "target_resource_version": 5}],
    ]

    _nodes, edges = fg.expand(
        resource_ids=["a"], resource_versions=[3],
        edge_types=["imitated_from"], tenant_id="default"
    )

    assert [
        (edge["source_resource_version"], edge["target_resource_version"])
        for edge in edges
    ] == [(3, 5)]


def test_expand_rejects_relationship_without_exact_endpoint_versions():
    fg, g = _graph_with()
    g.query.return_value.result_set = [[
        "a", "A", "generated_copy", 1,
        "b", "B", "xhs_note", 1,
        "derived_from", 1.0,
        {"source_resource_version": 1},
    ]]

    with pytest.raises(ValueError, match="target_resource_version"):
        fg.expand(
            resource_ids=["a"], resource_versions=[1], edge_types=None, tenant_id="default"
        )


def test_expand_rejects_missing_or_misaligned_seed_versions():
    fg, _g = _graph_with()
    with pytest.raises(ValueError, match="align"):
        fg.expand(resource_ids=["a"], resource_versions=[], edge_types=None, tenant_id="default")
    with pytest.raises(ValueError, match="positive"):
        fg.expand(resource_ids=["a"], resource_versions=[0], edge_types=None, tenant_id="default")


def test_ensure_indexes_runs_once_per_graph(monkeypatch):
    """索引创建幂等且进程内只执行一次:同一 url::graph 第二次 from_config 不再发 CREATE INDEX。"""
    import data_foundation.falkor_client as fc
    fc._reset_db_cache()

    class _FakeDB:
        def __init__(self):
            self.graph = MagicMock()

        @classmethod
        def from_url(cls, url, **kwargs):
            inst = cls()
            return inst

        def select_graph(self, name):
            return self.graph

    monkeypatch.setattr(fc.falkordb, "FalkorDB", _FakeDB)
    from data_foundation.engine_config import FalkorConfig
    cfg = FalkorConfig(state="enabled", url="redis://idx:6379", graph_name="xhs")
    first = fc.FalkorResourceGraph.from_config(cfg)
    create_calls = [c for c in first.graph.query.call_args_list if "CREATE INDEX" in c[0][0]]
    assert len(create_calls) == 2, "id 与 tenant_id 各一条 range 索引"
    fc.FalkorResourceGraph.from_config(cfg)
    create_calls_after = [c for c in first.graph.query.call_args_list if "CREATE INDEX" in c[0][0]]
    assert len(create_calls_after) == 2, "第二次取实例不重复建索引"


def test_hnsw_ef_search_width_bounds():
    """ef_search 边界:下限 64(top_k 小时),4×top_k(中段),上限 400(极端 top_k)。"""
    from data_foundation.repositories.resource import hnsw_ef_search_width
    assert hnsw_ef_search_width(1) == 64
    assert hnsw_ef_search_width(16) == 64
    assert hnsw_ef_search_width(25) == 100
    assert hnsw_ef_search_width(100) == 400
    assert hnsw_ef_search_width(500) == 400


def test_from_config_reuses_underlying_db_for_same_config(monkeypatch):
    import data_foundation.falkor_client as fc
    fc._reset_db_cache()
    created = []

    class _FakeDB:
        @classmethod
        def from_url(cls, url, **kwargs):
            created.append(url)
            inst = MagicMock()
            return inst

    monkeypatch.setattr(fc.falkordb, "FalkorDB", _FakeDB)
    from data_foundation.engine_config import FalkorConfig
    cfg = FalkorConfig(state="enabled", url="redis://x:6379", graph_name="xhs")
    fc.FalkorResourceGraph.from_config(cfg)
    fc.FalkorResourceGraph.from_config(cfg)
    # 同 url:底层 FalkorDB 连接只建一次
    assert len(created) == 1
    # 不同 url:新建
    fc.FalkorResourceGraph.from_config(FalkorConfig(state="enabled", url="redis://y:6379", graph_name="xhs"))
    assert len(created) == 2
