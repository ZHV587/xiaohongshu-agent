from unittest.mock import MagicMock
from data_foundation.falkor_client import FalkorResourceGraph


def _graph_with():
    g = MagicMock()
    return FalkorResourceGraph(graph=g), g


def test_merge_node_uses_merge_with_id():
    fg, g = _graph_with()
    fg.merge_node({"id": "r1", "tenant_id": "default", "type": "feishu_base_record", "title": "T"})
    cypher, params = g.query.call_args[0][0], g.query.call_args[0][1]
    assert "MERGE" in cypher and ":Resource" in cypher
    assert params["id"] == "r1" and params["title"] == "T"


def test_merge_edge_merges_both_endpoints_as_placeholder():
    fg, g = _graph_with()
    fg.merge_edge(source_id="a", target_id="b", edge_type="derived_from", weight=1.0, properties={})
    cypher, params = g.query.call_args[0][0], g.query.call_args[0][1]
    # 两端都 MERGE(target 占位)+ 边 MERGE,共 >=3 个 MERGE
    assert cypher.count("MERGE") >= 3
    # edge_type 作参数传入(变长路径查询用统一 :REL 标签 + edge_type 属性)
    assert params["etype"] == "derived_from"
    assert params["sid"] == "a" and params["tid"] == "b"


def test_expand_returns_nodes_and_edges():
    fg, g = _graph_with()
    g.query.return_value.result_set = [
        ["a", "T-a", "feishu_base_record", "b", "T-b", "feishu_base_record", "derived_from", 1.0]
    ]
    nodes, edges = fg.expand(resource_ids=["a"], hops=1, edge_types=None, tenant_id="default")
    assert any(n["id"] == "a" for n in nodes)
    assert any(e["source"] == "a" and e["target"] == "b" for e in edges)


def test_from_config_reuses_underlying_db_for_same_config(monkeypatch):
    import data_foundation.falkor_client as fc
    fc._reset_db_cache()
    created = []

    class _FakeDB:
        @classmethod
        def from_url(cls, url):
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
