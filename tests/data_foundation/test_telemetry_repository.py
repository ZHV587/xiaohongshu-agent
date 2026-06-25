from __future__ import annotations

import re
import importlib.resources
from datetime import datetime, timedelta, timezone
import data_foundation.db

# Monkeypatch pgvector migrations to run on local Postgres
def patched_apply_migrations(conn):
    schema_sql = importlib.resources.files("data_foundation").joinpath("schema.sql").read_text(encoding="utf-8")
    schema_sql = schema_sql.replace("create extension if not exists vector with schema public;", "")
    schema_sql = schema_sql.replace("embedding public.vector(1536) not null", "embedding double precision[] not null")
    schema_sql = re.sub(
        r"create index if not exists idx_resource_embeddings_vector\s+on resource_embeddings using ivfflat[^;]+;",
        "",
        schema_sql
    )
    conn.execute(schema_sql)

data_foundation.db._apply_migrations = patched_apply_migrations

from data_foundation.repositories.telemetry import TelemetryRepository


def test_heartbeat_is_scoped_to_instance_and_deployment(migrated_conn):
    repo = TelemetryRepository()
    repo.register_instance(
        component="scheduler",
        instance_id="i1",
        deployment_id="d1",
        config_version="v1",
        conn=migrated_conn,
    )
    before = repo.instance(component="scheduler", instance_id="i1", conn=migrated_conn).heartbeat_at

    assert repo.heartbeat(component="scheduler", instance_id="i1", deployment_id="wrong", conn=migrated_conn) is False
    assert repo.instance(component="scheduler", instance_id="i1", conn=migrated_conn).heartbeat_at == before

    assert repo.heartbeat(component="scheduler", instance_id="i1", deployment_id="d1", conn=migrated_conn) is True
    current = repo.instance(component="scheduler", instance_id="i1", conn=migrated_conn)
    assert current.deployment_id == "d1"
    assert current.config_version == "v1"
    assert current.heartbeat_at >= before


def test_finish_execution_redacts_secrets_and_only_finishes_running(migrated_conn):
    repo = TelemetryRepository()
    repo.register_instance(component="scheduler", instance_id="i1", deployment_id="d1", conn=migrated_conn)
    execution_id = repo.start_execution(
        component="scheduler",
        instance_id="i1",
        tenant_id="tenant-a",
        operation="outbox_cycle",
        config_version="cfg",
        conn=migrated_conn,
    )

    assert repo.finish_execution(
        execution_id,
        tenant_id="tenant-a",
        status="failed",
        processed_count=3,
        succeeded_count=1,
        failed_count=2,
        error=RuntimeError("password=secret-token"),
        conn=migrated_conn,
    ) is True
    execution = repo.execution(execution_id, tenant_id="tenant-a", conn=migrated_conn)
    assert execution.status == "failed"
    assert execution.processed_count == 3
    assert execution.error_code == "internal_error"
    assert "secret-token" not in execution.error_summary
    assert "password=<redacted>" in execution.error_summary

    assert repo.finish_execution(
        execution_id,
        tenant_id="tenant-a",
        status="succeeded",
        conn=migrated_conn,
    ) is False
    assert repo.execution(execution_id, tenant_id="tenant-a", conn=migrated_conn).status == "failed"


def test_stop_instance_marks_stopped_without_deleting_history(migrated_conn):
    repo = TelemetryRepository()
    repo.register_instance(component="scheduler", instance_id="i1", deployment_id="d1", conn=migrated_conn)

    assert repo.stop_instance(component="scheduler", instance_id="i1", deployment_id="d1", conn=migrated_conn) is True
    stopped = repo.instance(component="scheduler", instance_id="i1", conn=migrated_conn)
    assert stopped.stopped_at is not None


from psycopg.rows import dict_row

def test_aggregate_and_delete_old_errors_preserves_error_facts(migrated_conn):
    repo = TelemetryRepository()
    repo.register_instance(component="scheduler", instance_id="i1", deployment_id="d1", conn=migrated_conn)
    first = repo.start_execution(
        component="scheduler",
        instance_id="i1",
        tenant_id="tenant-a",
        operation="embedding_generate",
        conn=migrated_conn,
    )
    second = repo.start_execution(
        component="scheduler",
        instance_id="i1",
        tenant_id="tenant-a",
        operation="embedding_generate",
        conn=migrated_conn,
    )
    for execution_id in (first, second):
        repo.finish_execution(
            execution_id,
            tenant_id="tenant-a",
            status="failed",
            error=TimeoutError("request timed out"),
            conn=migrated_conn,
        )
    old_time = datetime.now(timezone.utc) - timedelta(days=120)
    migrated_conn.execute(
        """
        update service_executions
        set finished_at = %s, started_at = %s
        where id = any(%s::uuid[])
        """,
        (old_time, old_time, [first, second]),
    )
    migrated_conn.commit()

    assert repo.aggregate_and_delete_old_errors(older_than=old_time + timedelta(days=1), limit=10, conn=migrated_conn) == 2
    with migrated_conn.cursor(row_factory=dict_row) as cursor:
        aggregate = cursor.execute(
            """
            select tenant_id, component, operation, error_code, error_count
            from service_error_aggregates
            """
        ).fetchone()
    assert aggregate["tenant_id"] == "tenant-a"
    assert aggregate["component"] == "scheduler"
    assert aggregate["operation"] == "embedding_generate"
    assert aggregate["error_code"] == "timeout"
    assert aggregate["error_count"] == 2
    with migrated_conn.cursor(row_factory=dict_row) as cursor:
        assert cursor.execute("select count(*) as count from service_executions").fetchone()["count"] == 0
