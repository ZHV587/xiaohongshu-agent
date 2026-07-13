from __future__ import annotations

import asyncio

from psycopg import Connection

from data_foundation.knowledge.service import KnowledgeService
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


class KnowledgeEnrichProcessor:
    topic = "knowledge_enrich"

    def __init__(
        self,
        conn: Connection,
        *,
        service: KnowledgeService | None = None,
    ):
        self.conn = conn
        self.service = service or KnowledgeService(conn)

    def state(self) -> ProcessorState:
        return ProcessorState(
            topic=self.topic,
            status="active",
            config_version="knowledge-enrich-v1",
            reason_code=None,
        )

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        resource_id = str(item.payload.get("resource_id") or item.resource_id or "")
        resource_version = int(item.payload.get("version") or item.resource_version or 0)
        if not resource_id or resource_version <= 0:
            raise PermanentProcessingError(
                "Knowledge outbox payload missing resource_id/version"
            )
        await lease.assert_owned()
        result = await asyncio.to_thread(
            self.service.enrich_exact_version,
            tenant_id=item.tenant_id,
            resource_id=resource_id,
            resource_version=resource_version,
        )
        await lease.assert_owned()
        return ProcessResult(
            status="superseded" if result.status == "superseded" else "succeeded"
        )
