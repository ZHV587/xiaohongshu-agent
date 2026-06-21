from __future__ import annotations

from typing import Any

import falkordb

from data_foundation.engine_config import FalkorConfig


class FalkorResourceGraph:
    def __init__(self, *, graph: Any):
        self.graph = graph

    @classmethod
    def from_config(cls, config: FalkorConfig) -> "FalkorResourceGraph":
        client = falkordb.FalkorDB.from_url(config.url)
        return cls(graph=client.select_graph(config.graph_name))

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
