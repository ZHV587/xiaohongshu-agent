from __future__ import annotations

from data_foundation.models import GraphEdge, GraphExpansion, GraphNode


def expand_graph(
    repo,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_ids: list[str],
    hops: int = 1,
    edge_types: list[str] | None = None,
) -> GraphExpansion:
    safe_ids = [r.strip() for r in resource_ids if r.strip()]
    if not safe_ids:
        return GraphExpansion(nodes=[], edges=[])
    safe_edge_types = [e.strip() for e in edge_types if e.strip()] if edge_types else None

    from data_foundation.engine_config import falkor_config_from_env
    from data_foundation.falkor_client import FalkorResourceGraph

    cfg = falkor_config_from_env()
    if cfg.state != "enabled":
        raise RuntimeError("FALKOR_UNAVAILABLE")
    graph = FalkorResourceGraph.from_config(cfg)
    raw_nodes, raw_edges = graph.expand(
        resource_ids=safe_ids,
        hops=min(max(int(hops), 1), 3),
        edge_types=safe_edge_types,
        tenant_id=tenant_id,
    )
    # 回 Postgres 过权限:只保留 actor 可见的节点
    node_ids = [n["id"] for n in raw_nodes]
    visible = {
        str(row["id"])
        for row in repo.readable_rows_by_ids(
            tenant_id=tenant_id, actor_open_id=actor_open_id, resource_ids=node_ids
        )
    }
    nodes = [
        GraphNode(resource_id=n["id"], title=n["title"], type=n["type"], depth=0)
        for n in raw_nodes
        if n["id"] in visible
    ]
    edges = [
        GraphEdge(
            source_resource_id=e["source"],
            target_resource_id=e["target"],
            edge_type=e["edge_type"],
            weight=e["weight"],
        )
        for e in raw_edges
        if e["source"] in visible and e["target"] in visible
    ]
    return GraphExpansion(nodes=nodes, edges=edges)
