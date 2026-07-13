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
        resource_version = int(item.payload.get("version") or item.resource_version or 0)
        if not resource_id or resource_version <= 0:
            raise PermanentProcessingError("Graph outbox payload missing resource_id/version")
        with self.conn.cursor(row_factory=dict_row) as cur:
            node = cur.execute(
                """
                select r.id::text as id, r.tenant_id, r.type,
                       coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                       rv.version as resource_version
                from resources r
                join resource_versions rv
                  on rv.tenant_id = r.tenant_id and rv.resource_id = r.id
                left join generated_copy_states gcs
                  on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
                where r.tenant_id = %s and r.id = %s and rv.version = %s
                  and r.status = 'active'
                  and (
                    (r.type = 'generated_copy' and (
                      gcs.knowledge_target_version is null
                      or rv.version = gcs.knowledge_target_version
                    ))
                    or
                    (r.type <> 'generated_copy' and rv.version = (
                      select max(latest.version) from resource_versions latest
                      where latest.tenant_id = r.tenant_id and latest.resource_id = r.id
                    ))
                  )
                """,
                (item.tenant_id, resource_id, resource_version),
            ).fetchone()
            edges = None if node is None else cur.execute(
                """
                select source_resource_id::text as source_resource_id,
                       source_resource_version,
                       target_resource_id::text as target_resource_id,
                       target_resource_version,
                       edge_type, weight, properties
                from resource_edges
                where tenant_id = %s
                  and source_resource_id = %s
                  and source_resource_version = %s
                """,
                (item.tenant_id, resource_id, resource_version),
            ).fetchall()
        await lease.assert_owned()
        if node is None:
            with self.conn.cursor(row_factory=dict_row) as cur:
                existing = cur.execute(
                    "select status from resources where tenant_id = %s and id = %s",
                    (item.tenant_id, resource_id),
                ).fetchone()
            if existing is not None and existing["status"] == "active":
                # 资源仍存在，说明这是旧候选/旧 knowledge target 的迟到 outbox；不得把图节点
                # 回退到旧版本，更不能把当前节点删掉。
                return ProcessResult(status="superseded")
            # 资源确已删除或退役时物理删除图节点及其关联边；旧版本但资源仍 active
            # 的迟到任务在上面 supersede，不能误删当前节点。
            await asyncio.to_thread(self.graph.delete_node, resource_id)
            return ProcessResult(status="superseded")
        # falkordb/redis 客户端是同步阻塞 socket I/O。与 meili 同理(见 meili.py 注释):
        # 在 async + asyncio.wait_for(outbox_timeout) 下直接阻塞会让超时失效、Falkor 卡顿冻死
        # 整个调度 cycle。故所有图写入 asyncio.to_thread 卸到工作线程。
        await asyncio.to_thread(
            self.graph.merge_node,
            {"id": node["id"], "tenant_id": node["tenant_id"],
             "type": node["type"], "title": node["title"],
             "resource_version": int(node["resource_version"])},
        )
        await asyncio.to_thread(
            self.graph.delete_outgoing_version_edges,
            source_id=node["id"],
            source_resource_version=int(node["resource_version"]),
            tenant_id=node["tenant_id"],
        )
        for e in edges:
            edge_properties = dict(e["properties"] or {})
            edge_properties.update(
                {
                    "source_resource_version": int(e["source_resource_version"]),
                    "target_resource_version": int(e["target_resource_version"]),
                }
            )
            await asyncio.to_thread(
                self.graph.merge_edge,
                source_id=e["source_resource_id"], target_id=e["target_resource_id"],
                edge_type=e["edge_type"], weight=float(e["weight"] or 1.0),
                properties=edge_properties,
                tenant_id=item.tenant_id,
            )
        return ProcessResult(status="succeeded")
