from __future__ import annotations

import threading
from typing import Any

import falkordb

from data_foundation.engine_config import FalkorConfig


# 模块级 FalkorDB 连接缓存:按 url 复用底层连接(redis),避免每次工具调用/每 cycle
# 新建 redis 连接累积。select_graph 轻量,每次按 graph_name 取。
_db_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()

# 已建过索引的 graph 集合(按 "url::graph_name" 记),保证每进程只 CREATE INDEX 一次。
# FalkorDB 的 CREATE INDEX 幂等失败会抛"already indexed",这里用集合先挡掉重复调用,
# 真跑到时也 try/except 兜住,双保险。
_indexed_graphs: set[str] = set()


def _reset_db_cache() -> None:
    with _cache_lock:
        _db_cache.clear()
        _indexed_graphs.clear()


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
        inst = cls(graph=db.select_graph(config.graph_name))
        inst._ensure_indexes(cache_key=f"{config.url}::{config.graph_name}")
        return inst

    def _ensure_indexes(self, *, cache_key: str) -> None:
        """幂等建 Resource 节点的 range 索引(id / tenant_id)。

        根因:此前图库无任何索引 —— 每次 merge_node/merge_edge(按 {id} MERGE)与 expand
        (按 s.id IN $ids + tenant 过滤)都退化成全标签扫描,节点一多就线性变慢。id 是所有
        MERGE/MATCH 的锚点、tenant_id 是 expand/count 的过滤键,给这两者建索引把点查从 O(N)
        降到近 O(1),是最直接的提速。首次连接时建一次,进程内缓存不再重复尝试。
        """
        with _cache_lock:
            if cache_key in _indexed_graphs:
                return
        for stmt in (
            "CREATE INDEX FOR (r:Resource) ON (r.id)",
            "CREATE INDEX FOR (r:Resource) ON (r.tenant_id)",
        ):
            try:
                self.graph.query(stmt)
            except Exception:
                # 已存在 / 旧版语法差异等 —— 索引是纯优化,建不上不影响功能,静默跳过。
                pass
        with _cache_lock:
            _indexed_graphs.add(cache_key)

    def merge_node(self, node: dict[str, Any]) -> None:
        resource_version = node.get("resource_version")
        if (
            not isinstance(resource_version, int)
            or isinstance(resource_version, bool)
            or resource_version <= 0
        ):
            raise ValueError("resource_version must be a positive integer")
        self.graph.query(
            "MERGE (r:Resource {id: $id}) "
            "SET r.tenant_id=$tenant_id, r.type=$type, r.title=$title, "
            "r.resource_version=$resource_version",
            {"id": node["id"], "tenant_id": node.get("tenant_id"),
             "type": node.get("type"), "title": node.get("title"),
             "resource_version": resource_version},
        )

    def merge_edge(self, *, source_id: str, target_id: str, edge_type: str,
                   weight: float, properties: dict[str, Any], tenant_id: str) -> None:
        # source 节点应已 merge_node;target 仅占位 MERGE(后续其任务补属性)。
        # 占位节点必须立刻带上 tenant_id:expand/count 全部按 tenant 过滤,没有 tenant 的
        # 占位节点在其补属性任务跑完前是"隐形"的 —— 无向遍历也永远召不回(线上曾积累 12 个)。
        # ON CREATE SET 只在新建时写,不会覆盖已 merge_node 节点的真实属性。
        self.graph.query(
            """
            MERGE (s:Resource {id: $sid})
            ON CREATE SET s.tenant_id = $tenant
            MERGE (t:Resource {id: $tid})
            ON CREATE SET t.tenant_id = $tenant
            MERGE (s)-[e:REL {edge_type: $etype}]->(t)
            SET e.weight = $weight
            """,
            {"sid": source_id, "tid": target_id, "etype": edge_type, "weight": weight,
             "tenant": tenant_id},
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
        # 无向遍历(-[:REL*1..hops]-,不再限定 ->):素材关联是双向语义(同垂类/同选题/仿写自
        # 等),原先只沿 -> 方向扩展,会漏掉"只作为关联目标"的节点(它们的入边邻居永远召不回)。
        # 无向后,从种子出发正反向邻居都能被扩展到,显著提召回;边仍按其存储的 source/target
        # 原方向返回(startNode/endNode 给的是关系本身的两端,不因无向匹配而翻转)。
        rows = self.graph.query(
            f"""
            MATCH p = (s:Resource)-[:REL*1..{hops}]-(t:Resource)
            WHERE s.id IN $ids AND s.tenant_id = $tenant AND t.tenant_id = $tenant
            WITH p {et_clause}
            UNWIND relationships(p) as rel
            RETURN startNode(rel).id, startNode(rel).title, startNode(rel).type,
                   startNode(rel).resource_version,
                   endNode(rel).id, endNode(rel).title, endNode(rel).type,
                   endNode(rel).resource_version,
                   rel.edge_type, rel.weight
            """,
            params,
        ).result_set
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for r in rows:
            sid, stitle, stype, sversion, tid, ttitle, ttype, tversion, etype, weight = r
            nodes[sid] = {
                "id": sid, "title": stitle, "type": stype,
                "resource_version": sversion,
            }
            nodes[tid] = {
                "id": tid, "title": ttitle, "type": ttype,
                "resource_version": tversion,
            }
            key = (sid, tid, etype)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append({"source": sid, "target": tid, "edge_type": etype,
                              "weight": float(weight or 1.0)})
        return list(nodes.values()), edges
