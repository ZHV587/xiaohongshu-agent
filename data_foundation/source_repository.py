from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.db import transaction
from data_foundation.models import SourceSecrets, SyncSource


class SourceRepository:
    def __init__(self, conn: Connection):
        self.conn = conn
        self.conn.row_factory = dict_row

    def register_source(
        self,
        *,
        tenant_id: str,
        source_type: str,
        name: str,
        external_id: str | None = None,
        credentials: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        schedule_seconds: int = 300,
        enabled: bool = True,
    ) -> SyncSource:
        row = self.conn.execute(
            """
            insert into sync_sources (
              tenant_id, source_type, name, external_id, credentials,
              config, enabled, schedule_seconds
            )
            values (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            on conflict (tenant_id, source_type, name)
            do update set external_id = excluded.external_id,
                          credentials = excluded.credentials,
                          config = excluded.config,
                          enabled = excluded.enabled,
                          schedule_seconds = excluded.schedule_seconds,
                          updated_at = now()
            returning *
            """,
            (
                tenant_id,
                source_type,
                name,
                external_id,
                json.dumps(credentials or {}, sort_keys=True, ensure_ascii=False),
                json.dumps(config or {}, sort_keys=True, ensure_ascii=False),
                enabled,
                schedule_seconds,
            ),
        ).fetchone()
        self.conn.commit()
        return self._source_from_row(row)

    def get_source(self, *, tenant_id: str, source_id: str) -> SyncSource:
        row = self.conn.execute(
            """
            select *
            from sync_sources
            where tenant_id = %s and id = %s
            """,
            (tenant_id, source_id),
        ).fetchone()
        if row is None:
            raise PermissionError("Sync source not found for tenant")
        return self._source_from_row(row)

    def get_source_with_secrets(
        self,
        *,
        tenant_id: str,
        source_id: str,
    ) -> tuple[SyncSource, SourceSecrets]:
        row = self.conn.execute(
            """
            select *
            from sync_sources
            where tenant_id = %s and id = %s
            """,
            (tenant_id, source_id),
        ).fetchone()
        if row is None:
            raise PermissionError("Sync source not found for tenant")
        return self._source_from_row(row), SourceSecrets(credentials=dict(row["credentials"]))

    def discover_due_tenants(self, *, limit: int) -> list[str]:
        rows = self.conn.execute(
            """
            select tenant_id
            from sync_sources
            where enabled is true
              and next_run_at <= now()
              and (lease_expires_at is null or lease_expires_at <= now())
            group by tenant_id
            order by bool_or(last_dispatched_at is null) desc,
                     min(last_dispatched_at) nulls first,
                     min(next_run_at),
                     tenant_id
            limit %s
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
        return [row["tenant_id"] for row in rows]

    def lease_due_source(
        self,
        *,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> SyncSource | None:
        with transaction(self.conn):
            row = self.conn.execute(
                """
                select id
                from sync_sources
                where tenant_id = %s
                  and enabled is true
                  and next_run_at <= now()
                  and (lease_expires_at is null or lease_expires_at <= now())
                order by last_dispatched_at nulls first, next_run_at, id
                limit 1
                for update skip locked
                """,
                (tenant_id,),
            ).fetchone()
            if row is None:
                return None
            leased = self.conn.execute(
                """
                update sync_sources
                set lease_owner = %s,
                    lease_expires_at = now() + (%s || ' seconds')::interval,
                    last_dispatched_at = now(),
                    updated_at = now()
                where tenant_id = %s and id = %s
                returning *
                """,
                (lease_owner, lease_seconds, tenant_id, row["id"]),
            ).fetchone()
        return self._source_from_row(leased)

    def renew_source(
        self,
        source_id: str,
        *,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        cursor = self.conn.execute(
            """
            update sync_sources
            set lease_expires_at = now() + (%s || ' seconds')::interval,
                updated_at = now()
            where tenant_id = %s
              and id = %s
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (lease_seconds, tenant_id, source_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def finish_source(
        self,
        source_id: str,
        *,
        tenant_id: str,
        lease_owner: str | None,
        cursor: dict[str, Any],
        next_run_after_seconds: int | None = None,
    ) -> bool:
        if lease_owner is None:
            where_lease = "and lease_owner is null"
            params = []
        else:
            where_lease = "and lease_owner = %s and lease_expires_at > now()"
            params = [lease_owner]
        delay_seconds = next_run_after_seconds
        if delay_seconds is None:
            delay_seconds = self.get_source(tenant_id=tenant_id, source_id=source_id).schedule_seconds
        cursor_result = self.conn.execute(
            f"""
            update sync_sources
            set cursor = %s::jsonb,
                next_run_at = now() + (%s || ' seconds')::interval,
                lease_owner = null,
                lease_expires_at = null,
                updated_at = now()
            where tenant_id = %s
              and id = %s
              {where_lease}
            """,
            (
                json.dumps(cursor, sort_keys=True, ensure_ascii=False),
                max(0, delay_seconds),
                tenant_id,
                source_id,
                *params,
            ),
        )
        self.conn.commit()
        return cursor_result.rowcount == 1

    def start_run(
        self,
        source_id: str,
        *,
        tenant_id: str,
        instance_id: str | None = None,
        execution_id: str | None = None,
    ) -> str:
        source = self.get_source(tenant_id=tenant_id, source_id=source_id)
        row = self.conn.execute(
            """
            insert into sync_runs (
              sync_source_id, tenant_id, source_type, instance_id, execution_id, cursor_before
            )
            values (%s, %s, %s, %s, %s, %s::jsonb)
            returning id::text as id
            """,
            (
                source.id,
                tenant_id,
                source.source_type,
                instance_id,
                execution_id,
                json.dumps(source.cursor, sort_keys=True, ensure_ascii=False),
            ),
        ).fetchone()
        self.conn.commit()
        return row["id"]

    def finish_run(
        self,
        run_id: str,
        *,
        tenant_id: str,
        status: str,
        cursor_after: dict[str, Any] | None,
        read_count: int,
        created_count: int,
        updated_count: int,
        skipped_count: int,
        failed_count: int,
        error_code: str | None,
        error_summary: str | None,
    ) -> bool:
        cursor = self.conn.execute(
            """
            update sync_runs
            set status = %s,
                cursor_after = %s::jsonb,
                read_count = %s,
                created_count = %s,
                updated_count = %s,
                skipped_count = %s,
                failed_count = %s,
                error_code = %s,
                error_summary = left(%s, 1000),
                finished_at = now()
            where tenant_id = %s and id = %s
            """,
            (
                status,
                None if cursor_after is None else json.dumps(cursor_after, sort_keys=True, ensure_ascii=False),
                read_count,
                created_count,
                updated_count,
                skipped_count,
                failed_count,
                error_code,
                error_summary,
                tenant_id,
                run_id,
            ),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def recover_stale_runs(self, *, older_than_seconds: int, limit: int) -> int:
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select id, tenant_id, sync_source_id
                from sync_runs
                where status = 'running'
                  and started_at < now() - (%s || ' seconds')::interval
                order by started_at, id
                limit %s
                for update skip locked
                """,
                (older_than_seconds, max(1, min(limit, 100))),
            ).fetchall()
            if not rows:
                return 0
            ids = [row["id"] for row in rows]
            self.conn.execute(
                """
                update sync_runs
                set status = 'stopped',
                    finished_at = now(),
                    error_code = 'STALE_SYNC_RUN',
                    error_summary = 'Recovered stale running sync run'
                where id = any(%s::uuid[])
                """,
                (ids,),
            )
            source_pairs = [(row["tenant_id"], row["sync_source_id"]) for row in rows if row["sync_source_id"]]
            for tenant_id, source_id in source_pairs:
                self.conn.execute(
                    """
                    update sync_sources
                    set lease_owner = null,
                        lease_expires_at = null,
                        updated_at = now()
                    where tenant_id = %s and id = %s
                    """,
                    (tenant_id, source_id),
                )
        return len(rows)

    @staticmethod
    def _source_from_row(row: Any) -> SyncSource:
        return SyncSource(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            source_type=row["source_type"],
            name=row["name"],
            external_id=row["external_id"],
            config=dict(row["config"]),
            enabled=row["enabled"],
            schedule_seconds=row["schedule_seconds"],
            next_run_at=row["next_run_at"],
            last_dispatched_at=row["last_dispatched_at"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            cursor=dict(row["cursor"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
