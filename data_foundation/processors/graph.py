from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.engine_config import FalkorConfig
from data_foundation.falkor_client import FalkorResourceGraph
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


class GraphProcessor:
    topic = "graph_ingest"

    def __init__(self, conn: Connection, *, graph: FalkorResourceGraph | None, config: FalkorConfig):
        self.conn = conn
        self.conn.row_factory = dict_row
        self.graph = graph
        self.config = config

    def state(self) -> ProcessorState:
        if self.config.state != "enabled" or self.graph is None:
            return ProcessorState(topic=self.topic, status="disabled",
                                  config_version=None, reason_code="FALKOR_CONFIG_MISSING")
        return ProcessorState(topic=self.topic, status="active", config_version=None, reason_code=None)

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        if self.config.state != "enabled" or self.graph is None:
            raise PermanentProcessingError("Falkor config is missing")
        resource_id = str(item.payload.get("resource_id") or item.resource_id or "")
        if not resource_id:
            raise PermanentProcessingError("Graph outbox payload missing resource_id")
        node = self.conn.execute(
            "select id::text as id, tenant_id, type, title from resources where tenant_id=%s and id=%s",
            (item.tenant_id, resource_id),
        ).fetchone()
        if node is None:
            return ProcessResult(status="superseded")
        edges = self.conn.execute(
            """
            select source_resource_id::text as source_resource_id,
                   target_resource_id::text as target_resource_id,
                   edge_type, weight, properties
            from resource_edges
            where tenant_id = %s and source_resource_id = %s
            """,
            (item.tenant_id, resource_id),
        ).fetchall()
        await lease.assert_owned()
        self.graph.merge_node({"id": node["id"], "tenant_id": node["tenant_id"],
                               "type": node["type"], "title": node["title"]})
        for e in edges:
            self.graph.merge_edge(source_id=e["source_resource_id"], target_id=e["target_resource_id"],
                                  edge_type=e["edge_type"], weight=float(e["weight"] or 1.0),
                                  properties=dict(e["properties"] or {}))
        return ProcessResult(status="succeeded")
