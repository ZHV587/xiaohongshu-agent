from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.engine_config import MeiliConfig
from data_foundation.meili_client import (
    MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION,
    MeiliResourceIndex,
)
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
                       target.content_text, target.resource_version,
                       target.asset_kind, target.source_kind, target.quality_score,
                       target.normalized_text,
                       target.metadata || coalesce(enrichment.payload, '{}'::jsonb)
                         as metadata,
                       target.qualified_at
                from current_knowledge_targets target
                left join lateral (
                  select knowledge_enrichments.payload
                  from knowledge_enrichments
                  where knowledge_enrichments.tenant_id = target.tenant_id
                    and knowledge_enrichments.resource_id = target.resource_id
                    and knowledge_enrichments.resource_version = target.resource_version
                    and knowledge_enrichments.enrichment_type = 'deterministic_metadata'
                  order by knowledge_enrichments.created_at desc,
                           knowledge_enrichments.id desc
                  limit 1
                ) enrichment on true
                where target.tenant_id = %s
                  and target.resource_id = %s
                """,
                (tenant_id, resource_id),
            ).fetchone()
        if row is None:
            return None
        metadata = row["metadata"] if isinstance(row["metadata"], dict) else {}
        qualified_at = row["qualified_at"]
        if (
            not isinstance(qualified_at, datetime)
            or qualified_at.tzinfo is None
            or qualified_at.utcoffset() is None
        ):
            raise RuntimeError("current knowledge target has invalid qualified_at")

        def clean_text(value: Any, *, max_length: int = 128) -> str | None:
            if not isinstance(value, str):
                return None
            text = value.strip()
            return text[:max_length] if text else None

        def clean_list(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            result: list[str] = []
            seen: set[str] = set()
            for item in value:
                text = clean_text(item)
                if text and text not in seen:
                    seen.add(text)
                    result.append(text)
                if len(result) >= 50:
                    break
            return result

        return {
            "resource_id": row["id"],
            "tenant_id": row["tenant_id"],
            "type": row["type"],
            "title": row["title"],
            "summary": row["summary"],
            "content_text": row["content_text"],
            "resource_version": int(row["resource_version"]),
            "asset_kind": row["asset_kind"],
            "source_kind": row["source_kind"],
            "niche": clean_text(metadata.get("niche")),
            "quality_score": float(row["quality_score"]),
            "qualified_at_epoch": int(qualified_at.timestamp()),
            "normalized_text": row["normalized_text"],
            "tags": clean_list(metadata.get("tags")),
            "hook_types": clean_list(metadata.get("hook_types")),
            "cta_types": clean_list(metadata.get("cta_types")),
            "structure_tags": clean_list(metadata.get("structure_tags")),
            "style_tags": clean_list(metadata.get("style_tags")),
            "success_factors": clean_list(metadata.get("success_factors")),
            "index_schema_version": MEILI_KNOWLEDGE_INDEX_SCHEMA_VERSION,
        }
