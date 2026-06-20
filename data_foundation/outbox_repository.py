from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.db import transaction
from data_foundation.models import OutboxItem


class OutboxRepository:
    def __init__(self, conn: Connection):
        self.conn = conn
        self.conn.row_factory = dict_row

    def enqueue(
        self,
        *,
        tenant_id: str,
        topic: str,
        dedupe_key: str,
        payload: dict[str, Any],
        resource_id: str | None = None,
        resource_version: int | None = None,
        event_id: str | None = None,
    ) -> OutboxItem:
        row = self.conn.execute(
            """
            insert into resource_outbox (
              tenant_id, resource_id, resource_version, event_id, topic, dedupe_key, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict(tenant_id, dedupe_key) do update set dedupe_key = excluded.dedupe_key
            returning *
            """,
            (
                tenant_id,
                resource_id,
                resource_version,
                event_id,
                topic,
                dedupe_key,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ),
        ).fetchone()
        self.conn.commit()
        return self._item_from_row(row)

    def lease_ready(
        self,
        *,
        tenant_id: str,
        topics: list[str],
        lease_owner: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[OutboxItem]:
        if not topics:
            return []
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select id
                from resource_outbox
                where tenant_id = %s
                  and topic = any(%s::text[])
                  and status in ('pending', 'retry')
                  and next_attempt_at <= now()
                order by next_attempt_at, created_at, id
                limit %s
                for update skip locked
                """,
                (tenant_id, topics, batch_size),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return []
            leased = self.conn.execute(
                """
                update resource_outbox
                set status = 'processing',
                    attempts = attempts + 1,
                    lease_owner = %s,
                    lease_expires_at = now() + (%s || ' seconds')::interval,
                    updated_at = now()
                where id = any(%s::uuid[])
                returning *
                """,
                (lease_owner, lease_seconds, ids),
            ).fetchall()
        return [self._item_from_row(row) for row in leased]

    def renew(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        cursor = self.conn.execute(
            """
            update resource_outbox
            set lease_expires_at = now() + (%s || ' seconds')::interval,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (lease_seconds, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def complete(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        status: str,
    ) -> bool:
        if status not in {"succeeded", "superseded"}:
            raise ValueError("Outbox completion status must be succeeded or superseded")
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = %s,
                lease_owner = null,
                lease_expires_at = null,
                error_code = null,
                error_summary = null,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (status, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def fail(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        error_code: str,
        error_summary: str,
        max_attempts: int = 8,
    ) -> bool:
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = case when attempts >= %s then 'dead' else 'retry' end,
                next_attempt_at = now() + (least(attempts * attempts, 300) || ' seconds')::interval,
                lease_owner = null,
                lease_expires_at = null,
                error_code = %s,
                error_summary = left(%s, 1000),
                dead_at = case when attempts >= %s then now() else dead_at end,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (max_attempts, error_code, error_summary, max_attempts, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def recover_expired(self, *, limit: int) -> int:
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select id
                from resource_outbox
                where status = 'processing'
                  and lease_expires_at < now()
                order by lease_expires_at, id
                limit %s
                for update skip locked
                """,
                (limit,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return 0
            cursor = self.conn.execute(
                """
                update resource_outbox
                set status = 'retry',
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                where id = any(%s::uuid[])
                """,
                (ids,),
            )
        return cursor.rowcount

    def block_item(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        reason_code: str,
    ) -> bool:
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = 'blocked',
                error_code = %s,
                error_summary = %s,
                lease_owner = null,
                lease_expires_at = null,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (reason_code, reason_code, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def unblock_available(self, *, tenant_id: str, topic: str) -> int:
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = 'pending',
                error_code = null,
                error_summary = null,
                next_attempt_at = now(),
                updated_at = now()
            where topic = %s
              and tenant_id = %s
              and status = 'blocked'
            """,
            (topic, tenant_id),
        )
        self.conn.commit()
        return cursor.rowcount

    @staticmethod
    def _item_from_row(row: Any) -> OutboxItem:
        return OutboxItem(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            resource_id=None if row["resource_id"] is None else str(row["resource_id"]),
            resource_version=row["resource_version"],
            topic=row["topic"],
            dedupe_key=row["dedupe_key"],
            payload=dict(row["payload"]),
            status=row["status"],
            attempts=row["attempts"],
            next_attempt_at=row["next_attempt_at"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            error_code=row["error_code"],
            error_summary=row["error_summary"],
            dead_at=row["dead_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
