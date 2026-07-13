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
        if not isinstance(properties, dict):
            raise ValueError("edge properties must be an object")
        edge_properties = dict(properties)
        for field in ("source_resource_version", "target_resource_version"):
            value = edge_properties.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
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
            MERGE (s)-[e:REL {
              edge_type: $etype,
              source_resource_version: $source_version,
              target_resource_version: $target_version
            }]->(t)
            SET e += $properties,
                e.edge_type = $etype,
                e.weight = $weight
            """,
            {"sid": source_id, "tid": target_id, "etype": edge_type, "weight": weight,
             "tenant": tenant_id,
             "source_version": edge_properties["source_resource_version"],
             "target_version": edge_properties["target_resource_version"],
             "properties": edge_properties},
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

    def delete_outgoing_version_edges(
        self, *, source_id: str, source_resource_version: int, tenant_id: str
    ) -> None:
        """Remove one exact source version's materialized edges before reconciliation."""
        self.graph.query(
            """
            MATCH (s:Resource {id: $id})-[rel:REL]->()
            WHERE s.tenant_id = $tenant
              AND (
                rel.source_resource_version = $version
                OR rel.source_resource_version IS NULL
              )
            DELETE rel
            """,
            {
                "id": source_id,
                "tenant": tenant_id,
                "version": source_resource_version,
            },
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

    def expand(self, *, resource_ids: list[str], resource_versions: list[int],
               edge_types: list[str] | None, tenant_id: str) -> tuple[list[dict], list[dict]]:
        if len(resource_ids) != len(resource_versions):
            raise ValueError("resource_versions must align with resource_ids")
        if any(not isinstance(version, int) or isinstance(version, bool) or version <= 0
               for version in resource_versions):
            raise ValueError("resource_versions must contain positive integers")
        params: dict[str, Any] = {
            "ids": resource_ids,
            "versions": resource_versions,
            "tenant": tenant_id,
        }
        et_clause = ""
        if edge_types:
            et_clause = "AND rel.edge_type IN $etypes"
            params["etypes"] = edge_types
        # 图节点仍承载稳定 resource 身份，关系属性承载不可变版本身份。因此扩展入口必须是
        # (id, version) 对，并只沿种子这一精确端点版本的一跳关系走；若只按 id 起步，会把同一
        # 资源其它历史版本的边混进当前证据。多跳会在中间节点产生同样歧义，统一检索层负责按需
        # 逐跳调用并重新做 PG 资格/ACL 校验。
        rows = self.graph.query(
            f"""
            UNWIND range(0, size($ids) - 1) AS i
            MATCH (s:Resource)-[rel:REL]-(t:Resource)
            WHERE s.id = $ids[i]
              AND s.tenant_id = $tenant AND t.tenant_id = $tenant
              AND rel.source_resource_version IS NOT NULL
              AND rel.target_resource_version IS NOT NULL
              AND (
                (startNode(rel).id = s.id AND rel.source_resource_version = $versions[i])
                OR
                (endNode(rel).id = s.id AND rel.target_resource_version = $versions[i])
              )
              {et_clause}
            RETURN startNode(rel).id, startNode(rel).title, startNode(rel).type,
                   rel.source_resource_version,
                   endNode(rel).id, endNode(rel).title, endNode(rel).type,
                   rel.target_resource_version,
                   rel.edge_type, rel.weight, properties(rel)
            """,
            params,
        ).result_set
        nodes: dict[tuple[str, int], dict] = {}
        edges: list[dict] = []
        seen_edges: set[tuple[str, int | None, str, int | None, str]] = set()
        for r in rows:
            (
                sid, stitle, stype, sversion,
                tid, ttitle, ttype, tversion,
                etype, weight, raw_properties,
            ) = r
            nodes[(sid, int(sversion))] = {
                "id": sid, "title": stitle, "type": stype,
                "resource_version": sversion,
            }
            nodes[(tid, int(tversion))] = {
                "id": tid, "title": ttitle, "type": ttype,
                "resource_version": tversion,
            }
            relationship_properties = dict(raw_properties or {})
            relationship_properties.pop("edge_type", None)
            relationship_properties.pop("weight", None)
            source_edge_version = relationship_properties.get("source_resource_version")
            target_edge_version = relationship_properties.get("target_resource_version")
            for field, value in (
                ("source_resource_version", source_edge_version),
                ("target_resource_version", target_edge_version),
            ):
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    raise ValueError(f"Falkor relationship missing exact {field}")
            key = (sid, source_edge_version, tid, target_edge_version, etype)
            if key not in seen_edges:
                seen_edges.add(key)
                edges.append(
                    {
                        "source": sid,
                        "source_resource_version": source_edge_version,
                        "target": tid,
                        "target_resource_version": target_edge_version,
                        "edge_type": etype,
                        "weight": float(weight or 1.0),
                        "properties": relationship_properties,
                    }
                )
        return list(nodes.values()), edges
