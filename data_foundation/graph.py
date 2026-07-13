from __future__ import annotations

from data_foundation.models import GraphEdge, GraphExpansion, GraphNode


def expand_graph(
    repo,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_ids: list[str],
    resource_versions: list[int],
    edge_types: list[str] | None = None,
) -> GraphExpansion:
    safe_ids = [r.strip() for r in resource_ids if r.strip()]
    if len(resource_ids) != len(resource_versions) or len(safe_ids) != len(resource_ids):
        raise ValueError("resource_ids and resource_versions must be aligned exact identities")
    if any(not isinstance(version, int) or isinstance(version, bool) or version <= 0
           for version in resource_versions):
        raise ValueError("resource_versions must contain positive integers")
    if not safe_ids:
        return GraphExpansion(nodes=[], edges=[])
    seed_identities = set(zip(safe_ids, resource_versions))
    safe_edge_types = [e.strip() for e in edge_types if e.strip()] if edge_types else None

    from data_foundation.engine_config import falkor_config_from_env
    from data_foundation.falkor_client import FalkorResourceGraph

    cfg = falkor_config_from_env()
    if cfg.state != "enabled":
        raise RuntimeError("FALKOR_UNAVAILABLE")
    graph = FalkorResourceGraph.from_config(cfg)
    raw_nodes, raw_edges = graph.expand(
        resource_ids=safe_ids,
        resource_versions=resource_versions,
        edge_types=safe_edge_types,
        tenant_id=tenant_id,
    )
    # 回 Postgres 过权限:只保留 actor 可见的节点
    node_ids = [n["id"] for n in raw_nodes]
    node_versions = [int(n["resource_version"]) for n in raw_nodes]
    hydrated = {
        (str(row["id"]), int(row["resource_version"])): row
        for row in repo.readable_rows_by_ids(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_ids=node_ids,
            resource_versions=node_versions,
        )
    }
    nodes = [
        GraphNode(
            resource_id=n["id"],
            resource_version=int(n["resource_version"]),
            title=hydrated[(n["id"], int(n["resource_version"]))]["title"],
            type=hydrated[(n["id"], int(n["resource_version"]))]["type"],
            depth=0 if (n["id"], int(n["resource_version"])) in seed_identities else 1,
        )
        for n in raw_nodes
        if (n["id"], int(n["resource_version"])) in hydrated
    ]
    edges = [
        GraphEdge(
            source_resource_id=e["source"],
            source_resource_version=int(e["source_resource_version"]),
            target_resource_id=e["target"],
            target_resource_version=int(e["target_resource_version"]),
            edge_type=e["edge_type"],
            weight=e["weight"],
            properties=dict(e.get("properties") or {}),
        )
        for e in raw_edges
        if (
            (e["source"], int(e["source_resource_version"])) in hydrated
            and (e["target"], int(e["target_resource_version"])) in hydrated
        )
    ]
    return GraphExpansion(nodes=nodes, edges=edges)
