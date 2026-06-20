from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.db import transaction
from data_foundation.errors import build_error_aggregate_key, classify_error
from data_foundation.models import ServiceExecution


@dataclass(frozen=True)
class ServiceInstance:
    instance_id: str
    deployment_id: str
    component: str
    config_version: str | None
    started_at: datetime
    heartbeat_at: datetime
    stopped_at: datetime | None
    created_at: datetime


class TelemetryRepository:
    def __init__(self, conn: Connection):
        self.conn = conn
        self.conn.row_factory = dict_row

    def register_instance(
        self,
        *,
        component: str,
        instance_id: str,
        deployment_id: str,
        config_version: str | None = None,
    ) -> ServiceInstance:
        row = self.conn.execute(
            """
            insert into service_instances (
              instance_id, deployment_id, component, config_version
            )
            values (%s, %s, %s, %s)
            on conflict (instance_id)
            do update set deployment_id = excluded.deployment_id,
                          component = excluded.component,
                          config_version = excluded.config_version,
                          heartbeat_at = now(),
                          stopped_at = null
            returning *
            """,
            (instance_id, deployment_id, component, config_version),
        ).fetchone()
        self.conn.commit()
        return self._instance_from_row(row)

    def heartbeat(self, *, component: str, instance_id: str, deployment_id: str) -> bool:
        cursor = self.conn.execute(
            """
            update service_instances
            set heartbeat_at = now()
            where component = %s
              and instance_id = %s
              and deployment_id = %s
              and stopped_at is null
            """,
            (component, instance_id, deployment_id),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def stop_instance(self, *, component: str, instance_id: str, deployment_id: str) -> bool:
        cursor = self.conn.execute(
            """
            update service_instances
            set stopped_at = now(),
                heartbeat_at = now()
            where component = %s
              and instance_id = %s
              and deployment_id = %s
              and stopped_at is null
            """,
            (component, instance_id, deployment_id),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def instance(self, *, component: str, instance_id: str) -> ServiceInstance:
        row = self.conn.execute(
            """
            select *
            from service_instances
            where component = %s and instance_id = %s
            """,
            (component, instance_id),
        ).fetchone()
        if row is None:
            raise KeyError("service instance not found")
        return self._instance_from_row(row)

    def start_execution(
        self,
        *,
        component: str,
        instance_id: str,
        tenant_id: str | None,
        operation: str,
        config_version: str | None = None,
    ) -> str:
        row = self.conn.execute(
            """
            insert into service_executions (
              component, instance_id, tenant_id, operation, status, config_version
            )
            values (%s, %s, %s, %s, 'running', %s)
            returning id::text as id
            """,
            (component, instance_id, tenant_id, operation, config_version),
        ).fetchone()
        self.conn.commit()
        return row["id"]

    def finish_execution(
        self,
        execution_id: str,
        *,
        tenant_id: str | None,
        status: str,
        processed_count: int = 0,
        succeeded_count: int = 0,
        failed_count: int = 0,
        error: BaseException | None = None,
        error_code: str | None = None,
        error_summary: str | None = None,
    ) -> bool:
        classification = None
        if error is not None or error_code or error_summary:
            classification = classify_error(
                error,
                message=error_summary or error_code,
                component="telemetry_repository",
                operation="finish_execution",
            )
        cursor = self.conn.execute(
            """
            update service_executions
            set status = %s,
                finished_at = now(),
                processed_count = %s,
                succeeded_count = %s,
                failed_count = %s,
                duration_ms = greatest(0, floor(extract(epoch from (now() - started_at)) * 1000)::int),
                error_code = %s,
                error_summary = %s
            where id = %s
              and tenant_id is not distinct from %s
              and status = 'running'
              and finished_at is null
            """,
            (
                status,
                processed_count,
                succeeded_count,
                failed_count,
                error_code or (classification.error_code if classification else None),
                classification.error_summary if classification else None,
                execution_id,
                tenant_id,
            ),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def execution(self, execution_id: str, *, tenant_id: str | None) -> ServiceExecution:
        row = self.conn.execute(
            """
            select *
            from service_executions
            where id = %s
              and tenant_id is not distinct from %s
            """,
            (execution_id, tenant_id),
        ).fetchone()
        if row is None:
            raise KeyError("service execution not found")
        return self._execution_from_row(row)

    def aggregate_and_delete_old_errors(self, *, older_than: datetime, limit: int) -> int:
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select *
                from service_executions
                where finished_at < %s
                  and error_code is not null
                order by finished_at, id
                limit %s
                for update skip locked
                """,
                (older_than, max(1, min(limit, 1000))),
            ).fetchall()
            if not rows:
                return 0

            for row in rows:
                window_started_at, window_ended_at, tenant_id, component, operation, error_code = (
                    build_error_aggregate_key(
                        classify_error(message=row["error_code"]),
                        occurred_at=row["finished_at"],
                        tenant_id=row["tenant_id"],
                        component=row["component"],
                        operation=row["operation"],
                    )
                )
                self.conn.execute(
                    """
                    insert into service_error_aggregates (
                      window_started_at, window_ended_at, tenant_id, component,
                      operation, error_code, error_count
                    )
                    values (%s, %s, %s, %s, %s, %s, 1)
                    on conflict (
                      window_started_at, window_ended_at, tenant_id, component, operation, error_code
                    )
                    do update set error_count = service_error_aggregates.error_count + 1
                    """,
                    (window_started_at, window_ended_at, tenant_id, component, operation, error_code),
                )

            ids = [row["id"] for row in rows]
            self.conn.execute(
                "delete from service_executions where id = any(%s::uuid[])",
                (ids,),
            )
        return len(rows)

    @staticmethod
    def _instance_from_row(row: Any) -> ServiceInstance:
        return ServiceInstance(
            instance_id=row["instance_id"],
            deployment_id=row["deployment_id"],
            component=row["component"],
            config_version=row["config_version"],
            started_at=row["started_at"],
            heartbeat_at=row["heartbeat_at"],
            stopped_at=row["stopped_at"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _execution_from_row(row: Any) -> ServiceExecution:
        return ServiceExecution(
            id=str(row["id"]),
            component=row["component"],
            instance_id=row["instance_id"],
            tenant_id=row["tenant_id"],
            operation=row["operation"],
            status=row["status"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            processed_count=row["processed_count"],
            succeeded_count=row["succeeded_count"],
            failed_count=row["failed_count"],
            duration_ms=row["duration_ms"],
            error_code=row["error_code"],
            error_summary=row["error_summary"],
            config_version=row["config_version"],
        )
