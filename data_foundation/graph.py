from __future__ import annotations

from data_foundation.models import GraphEdge, GraphExpansion, GraphNode
from data_foundation.repository import ResourceRepository


def expand_graph(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_ids: list[str],
    hops: int = 1,
    edge_types: list[str] | None = None,
) -> GraphExpansion:
    safe_resource_ids = [resource_id.strip() for resource_id in resource_ids if resource_id.strip()]
    safe_edge_types = None
    if edge_types is not None:
        safe_edge_types = [edge_type.strip() for edge_type in edge_types if edge_type.strip()]
    if not safe_resource_ids:
        return GraphExpansion(nodes=[], edges=[])
    rows = repo.graph_rows(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        resource_ids=safe_resource_ids,
        hops=min(max(int(hops), 1), 3),
        edge_types=safe_edge_types,
    )
    nodes = [
        GraphNode(
            resource_id=str(row["id"]),
            title=row["title"],
            type=row["type"],
            depth=int(row["depth"]),
        )
        for row in rows
        if row["kind"] == "node"
    ]
    visible_resource_ids = {node.resource_id for node in nodes}
    edges = [
        GraphEdge(
            source_resource_id=str(row["source_resource_id"]),
            target_resource_id=str(row["target_resource_id"]),
            edge_type=row["edge_type"],
            weight=float(row["weight"]),
        )
        for row in rows
        if row["kind"] == "edge"
        and str(row["source_resource_id"]) in visible_resource_ids
        and str(row["target_resource_id"]) in visible_resource_ids
    ]
    return GraphExpansion(nodes=nodes, edges=edges)
