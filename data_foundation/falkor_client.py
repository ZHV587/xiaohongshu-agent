from __future__ import annotations

import threading
from typing import Any

import falkordb

from data_foundation.engine_config import FalkorConfig


# 模块级 FalkorDB 连接缓存:按 url 复用底层连接(redis),避免每次工具调用/每 cycle
# 新建 redis 连接累积。select_graph 轻量,每次按 graph_name 取。
_db_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()


def _reset_db_cache() -> None:
    with _cache_lock:
        _db_cache.clear()


def _get_db(url: str) -> Any:
    with _cache_lock:
        db = _db_cache.get(url)
        if db is None:
            # socket_timeout/socket_connect_timeout(秒):redis-py 默认 None=无限阻塞。
            # 防 Falkor 卡顿/网络分区时工作线程永久阻塞(即便已 to_thread,无超时仍会占死线程
            # 并卡住整个 outbox 重试)。给硬上限,卡死的连接抛超时后由 outbox 重试回收。
            db = falkordb.FalkorDB.from_url(url, socket_timeout=30, socket_connect_timeout=10)
            _db_cache[url] = db
        return db


class FalkorResourceGraph:
    def __init__(self, *, graph: Any):
        self.graph = graph

    @classmethod
    def from_config(cls, config: FalkorConfig) -> "FalkorResourceGraph":
        db = _get_db(config.url)
        return cls(graph=db.select_graph(config.graph_name))

    def merge_node(self, node: dict[str, Any]) -> None:
        self.graph.query(
            "MERGE (r:Resource {id: $id}) SET r.tenant_id=$tenant_id, r.type=$type, r.title=$title",
            {"id": node["id"], "tenant_id": node.get("tenant_id"),
             "type": node.get("type"), "title": node.get("title")},
        )

    def merge_edge(self, *, source_id: str, target_id: str, edge_type: str,
                   weight: float, properties: dict[str, Any]) -> None:
        # source 节点应已 merge_node;target 仅占位 MERGE(后续其任务补属性)
        self.graph.query(
            """
            MERGE (s:Resource {id: $sid})
            MERGE (t:Resource {id: $tid})
            MERGE (s)-[e:REL {edge_type: $etype}]->(t)
            SET e.weight = $weight
            """,
            {"sid": source_id, "tid": target_id, "etype": edge_type, "weight": weight},
        )

    def delete_node(self, resource_id: str) -> None:
        """物理删除资源节点及其所有关联边(资源已从核心库消失时调用),使图谱与核心库一致。

        DETACH DELETE 会连同该节点的入/出边一并删除,避免遗留悬挂边。节点不存在时为无操作(幂等),
        故重复删除安全。
        """
        self.graph.query(
            "MATCH (r:Resource {id: $id}) DETACH DELETE r",
            {"id": resource_id},
        )

    def count(self, *, tenant_id: str) -> int:
        """按 tenant 统计图中 Resource 节点数(对账用)。"""
        rows = self.graph.query(
            "MATCH (r:Resource {tenant_id: $t}) RETURN count(r)",
            {"t": tenant_id},
        ).result_set
        if rows and rows[0]:
            return int(rows[0][0] or 0)
        return 0

    def expand(self, *, resource_ids: list[str], hops: int, edge_types: list[str] | None,
               tenant_id: str) -> tuple[list[dict], list[dict]]:
        params: dict[str, Any] = {"ids": resource_ids, "tenant": tenant_id}
        et_clause = ""
        if edge_types:
            et_clause = "WHERE all(rel IN relationships(p) WHERE rel.edge_type IN $etypes)"
            params["etypes"] = edge_types
        rows = self.graph.query(
            f"""
            MATCH p = (s:Resource)-[:REL*1..{hops}]->(t:Resource)
            WHERE s.id IN $ids AND s.tenant_id = $tenant AND t.tenant_id = $tenant
            WITH p {et_clause}
            UNWIND relationships(p) as rel
            RETURN startNode(rel).id, startNode(rel).title, startNode(rel).type,
                   endNode(rel).id, endNode(rel).title, endNode(rel).type,
                   rel.edge_type, rel.weight
            """,
            params,
        ).result_set
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for r in rows:
            sid, stitle, stype, tid, ttitle, ttype, etype, weight = r
            nodes[sid] = {"id": sid, "title": stitle, "type": stype}
            nodes[tid] = {"id": tid, "title": ttitle, "type": ttype}
            key = (sid, tid, etype)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"source": sid, "target": tid, "edge_type": etype,
                              "weight": float(weight or 1.0)})
        return list(nodes.values()), edges
