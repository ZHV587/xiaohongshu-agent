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
        self.conn = conn
        self.conn.row_factory = dict_row
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
        if not resource_id:
            raise PermanentProcessingError("Meili outbox payload missing resource_id")
        row = self.conn.execute(
            """
            select id::text as id, tenant_id, type, title, summary, content_text
            from resources where tenant_id = %s and id = %s
            """,
            (item.tenant_id, resource_id),
        ).fetchone()
        if row is None:
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
            },
        )
        return ProcessResult(status="succeeded")
