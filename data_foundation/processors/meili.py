from __future__ import annotations

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
        await lease.assert_owned()
        self.index.upsert({
            "resource_id": row["id"],
            "tenant_id": row["tenant_id"],
            "type": row["type"],
            "title": row["title"],
            "summary": row["summary"],
            "content_text": row["content_text"],
        })
        return ProcessResult(status="succeeded")
