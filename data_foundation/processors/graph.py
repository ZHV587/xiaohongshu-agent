from __future__ import annotations

import asyncio

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.engine_config import FalkorConfig
from data_foundation.falkor_client import FalkorResourceGraph
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


class GraphProcessor:
    topic = "graph_ingest"

    def __init__(self, conn: Connection, *, graph: FalkorResourceGraph | None, config: FalkorConfig):
        # 不改写共享连接的 row_factory(会污染其它共用该连接的组件);dict 行按查询用
        # cursor(row_factory=dict_row) 局部声明。
        self.conn = conn
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
        with self.conn.cursor(row_factory=dict_row) as cur:
            node = cur.execute(
                "select id::text as id, tenant_id, type, title from resources where tenant_id=%s and id=%s",
                (item.tenant_id, resource_id),
            ).fetchone()
            edges = None if node is None else cur.execute(
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
        if node is None:
            # 资源已从核心库消失:物理删除图节点及其关联边,使图谱与核心库一致,
            # 否则已删资源会永久驻留图谱形成脏数据。DETACH DELETE 幂等,可安全重试。
            await asyncio.to_thread(self.graph.delete_node, resource_id)
            return ProcessResult(status="superseded")
        # falkordb/redis 客户端是同步阻塞 socket I/O。与 meili 同理(见 meili.py 注释):
        # 在 async + asyncio.wait_for(outbox_timeout) 下直接阻塞会让超时失效、Falkor 卡顿冻死
        # 整个调度 cycle。故所有图写入 asyncio.to_thread 卸到工作线程。
        await asyncio.to_thread(
            self.graph.merge_node,
            {"id": node["id"], "tenant_id": node["tenant_id"],
             "type": node["type"], "title": node["title"]},
        )
        for e in edges:
            await asyncio.to_thread(
                self.graph.merge_edge,
                source_id=e["source_resource_id"], target_id=e["target_resource_id"],
                edge_type=e["edge_type"], weight=float(e["weight"] or 1.0),
                properties=dict(e["properties"] or {}),
                tenant_id=item.tenant_id,
            )
        return ProcessResult(status="succeeded")
