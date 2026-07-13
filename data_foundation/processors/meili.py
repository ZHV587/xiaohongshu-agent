from __future__ import annotations

import asyncio

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.engine_config import MeiliConfig
from data_foundation.meili_client import MeiliResourceIndex
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


class MeiliProcessor:
    topic = "meili_index"

    def __init__(self, conn: Connection, *, index: MeiliResourceIndex | None, config: MeiliConfig):
        # 不改写共享连接的 row_factory(会污染其它共用该连接、依赖默认/hybrid 行格式的组件);
        # 本处理器所需的 dict 行按查询用 cursor(row_factory=dict_row) 局部声明。
        self.conn = conn
        self.index = index
        self.config = config
        self._index_ensured = False

    def state(self) -> ProcessorState:
        if self.config.state != "enabled" or self.index is None:
            return ProcessorState(topic=self.topic, status="disabled",
                                  config_version=None, reason_code="MEILI_CONFIG_MISSING")
        return ProcessorState(topic=self.topic, status="active", config_version=None, reason_code=None)

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        if self.config.state != "enabled" or self.index is None:
            raise PermanentProcessingError("Meili config is missing")
        resource_id = str(item.payload.get("resource_id") or item.resource_id or "")
        resource_version = int(item.payload.get("version") or item.resource_version or 0)
        if not resource_id or resource_version <= 0:
            raise PermanentProcessingError("Meili outbox payload missing resource_id/version")
        with self.conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                select r.id::text as id, r.tenant_id, r.type,
                       coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                       r.summary, rv.content_text, rv.version as resource_version
                from resources r
                join resource_versions rv
                  on rv.tenant_id = r.tenant_id
                 and rv.resource_id = r.id
                 and rv.version = %s
                left join generated_copy_states gcs
                  on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
                where r.tenant_id = %s and r.id = %s
                  and (
                    (r.type = 'generated_copy' and gcs.knowledge_target_version = rv.version)
                    or
                    (r.type <> 'generated_copy' and rv.version = (
                      select max(latest.version) from resource_versions latest
                      where latest.tenant_id = r.tenant_id and latest.resource_id = r.id
                    ))
                  )
                """,
                (resource_version, item.tenant_id, resource_id),
            ).fetchone()
        if row is None:
            with self.conn.cursor(row_factory=dict_row) as cur:
                exists = cur.execute(
                    "select 1 from resources where tenant_id = %s and id = %s",
                    (item.tenant_id, resource_id),
                ).fetchone()
            if exists is not None:
                # 资源仍在，但这条 outbox 指向旧版本、普通候选或已被新采纳版本替代。
                # 绝不能删除当前 Meili 文档，也不能回退索引到错误快照。
                return ProcessResult(status="superseded")
            # 资源确已从核心库消失才物理删除索引文档。
            await lease.assert_owned()
            await asyncio.to_thread(self.index.delete, resource_id)
            return ProcessResult(status="superseded")
        # 确保索引 settings(filterable/searchable)就位,且只在本实例首次写入前调一次。
        # Meili update settings 幂等;这保证容器/数据卷重建后 settings 自动恢复,
        # 不依赖部署期手动 ensure_index(否则 search 的 tenant_id filter 会因未声明 filterable 而失败)。
        # meilisearch 客户端是同步阻塞 I/O(requests 系)。本方法是 async 且跑在
        # asyncio.wait_for(outbox_timeout) 之下:若直接在事件循环线程阻塞 socket,
        # wait_for 的超时回调跑不动 → 超时形同虚设,Meili 卡顿会冻死整个调度 cycle。
        # 故 ensure_index/upsert 一律 asyncio.to_thread 卸到工作线程。
        if not self._index_ensured:
            await asyncio.to_thread(self.index.ensure_index)
            self._index_ensured = True
        await lease.assert_owned()
        await asyncio.to_thread(
            self.index.upsert,
            {
                "resource_id": row["id"],
                "tenant_id": row["tenant_id"],
                "type": row["type"],
                "title": row["title"],
                "summary": row["summary"],
                "content_text": row["content_text"],
                "resource_version": int(row["resource_version"]),
            },
        )
        return ProcessResult(status="succeeded")
