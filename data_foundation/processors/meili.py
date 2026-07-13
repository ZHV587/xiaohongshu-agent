from __future__ import annotations

import asyncio
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.engine_config import MeiliConfig
from data_foundation.meili_client import MeiliResourceIndex
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


class MeiliProcessor:
    topic = "meili_index"
    max_reconcile_passes = 4

    def __init__(self, conn: Connection, *, index: MeiliResourceIndex | None, config: MeiliConfig):
        self.conn = conn
        self.index = index
        self.config = config
        self._index_ensured = False

    def state(self) -> ProcessorState:
        if self.config.state != "enabled" or self.index is None:
            return ProcessorState(
                topic=self.topic,
                status="disabled",
                config_version=None,
                reason_code="MEILI_CONFIG_MISSING",
            )
        return ProcessorState(
            topic=self.topic,
            status="active",
            config_version=None,
            reason_code=None,
        )

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        if self.config.state != "enabled" or self.index is None:
            raise PermanentProcessingError("Meili config is missing")
        resource_id = str(item.payload.get("resource_id") or item.resource_id or "")
        resource_version = int(item.payload.get("version") or item.resource_version or 0)
        if not resource_id or resource_version <= 0:
            raise PermanentProcessingError("Meili outbox payload missing resource_id/version")

        # Meili is keyed by stable resource_id, so every exact-version task is a
        # resource-level reconciliation request. Reading only the task's historical
        # version would let an older task overwrite or delete a newer current document.
        desired = self._load_current_document(
            tenant_id=item.tenant_id,
            resource_id=resource_id,
        )
        for _attempt in range(self.max_reconcile_passes):
            await lease.assert_owned()
            if desired is None:
                await asyncio.to_thread(self.index.delete, resource_id)
            else:
                await self._ensure_index(lease)
                await asyncio.to_thread(self.index.upsert, desired)

            # External writes are not atomic with PostgreSQL. Re-read the single
            # current gate after Meili acknowledges the operation; if the desired
            # state changed while I/O was in flight, repair it in this same lease.
            await lease.assert_owned()
            observed = self._load_current_document(
                tenant_id=item.tenant_id,
                resource_id=resource_id,
            )
            if observed == desired:
                return ProcessResult(
                    status="succeeded" if observed is not None else "superseded"
                )
            desired = observed

        # Continuous churn is transient. Failing preserves this row for normal retry;
        # every committed classification also owns a distinct generation row, so a
        # final state cannot be swallowed by this processing item.
        raise RuntimeError("MEILI_RECONCILE_UNSTABLE")

    async def _ensure_index(self, lease: LeaseGuard) -> None:
        if self._index_ensured:
            return
        await asyncio.to_thread(self.index.ensure_index)
        await lease.assert_owned()
        self._index_ensured = True

    def _load_current_document(
        self,
        *,
        tenant_id: str,
        resource_id: str,
    ) -> dict[str, Any] | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                select target.resource_id::text as id, target.tenant_id,
                       target.resource_type as type, target.title, target.summary,
                       target.content_text, target.resource_version
                from current_knowledge_targets target
                where target.tenant_id = %s
                  and target.resource_id = %s
                """,
                (tenant_id, resource_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "resource_id": row["id"],
            "tenant_id": row["tenant_id"],
            "type": row["type"],
            "title": row["title"],
            "summary": row["summary"],
            "content_text": row["content_text"],
            "resource_version": int(row["resource_version"]),
        }
