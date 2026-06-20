from __future__ import annotations

from datetime import datetime, timedelta, timezone

from data_foundation.telemetry_repository import TelemetryRepository


def test_heartbeat_is_scoped_to_instance_and_deployment(migrated_conn):
    repo = TelemetryRepository(migrated_conn)
    repo.register_instance(
        component="scheduler",
        instance_id="i1",
        deployment_id="d1",
        config_version="v1",
    )
    before = repo.instance(component="scheduler", instance_id="i1").heartbeat_at

    assert repo.heartbeat(component="scheduler", instance_id="i1", deployment_id="wrong") is False
    assert repo.instance(component="scheduler", instance_id="i1").heartbeat_at == before

    assert repo.heartbeat(component="scheduler", instance_id="i1", deployment_id="d1") is True
    current = repo.instance(component="scheduler", instance_id="i1")
    assert current.deployment_id == "d1"
    assert current.config_version == "v1"
    assert current.heartbeat_at >= before


def test_finish_execution_redacts_secrets_and_only_finishes_running(migrated_conn):
    repo = TelemetryRepository(migrated_conn)
    repo.register_instance(component="scheduler", instance_id="i1", deployment_id="d1")
    execution_id = repo.start_execution(
        component="scheduler",
        instance_id="i1",
        tenant_id="tenant-a",
        operation="outbox_cycle",
        config_version="cfg",
    )

    assert repo.finish_execution(
        execution_id,
        tenant_id="tenant-a",
        status="failed",
        processed_count=3,
        succeeded_count=1,
        failed_count=2,
        error=RuntimeError("password=secret-token"),
    ) is True
    execution = repo.execution(execution_id, tenant_id="tenant-a")
    assert execution.status == "failed"
    assert execution.processed_count == 3
    assert execution.error_code == "internal_error"
    assert "secret-token" not in execution.error_summary
    assert "password=<redacted>" in execution.error_summary

    assert repo.finish_execution(
        execution_id,
        tenant_id="tenant-a",
        status="succeeded",
    ) is False
    assert repo.execution(execution_id, tenant_id="tenant-a").status == "failed"


def test_stop_instance_marks_stopped_without_deleting_history(migrated_conn):
    repo = TelemetryRepository(migrated_conn)
    repo.register_instance(component="scheduler", instance_id="i1", deployment_id="d1")

    assert repo.stop_instance(component="scheduler", instance_id="i1", deployment_id="d1") is True
    stopped = repo.instance(component="scheduler", instance_id="i1")
    assert stopped.stopped_at is not None


def test_aggregate_and_delete_old_errors_preserves_error_facts(migrated_conn):
    repo = TelemetryRepository(migrated_conn)
    repo.register_instance(component="scheduler", instance_id="i1", deployment_id="d1")
    first = repo.start_execution(
        component="scheduler",
        instance_id="i1",
        tenant_id="tenant-a",
        operation="embedding_generate",
    )
    second = repo.start_execution(
        component="scheduler",
        instance_id="i1",
        tenant_id="tenant-a",
        operation="embedding_generate",
    )
    for execution_id in (first, second):
        repo.finish_execution(
            execution_id,
            tenant_id="tenant-a",
            status="failed",
            error=TimeoutError("request timed out"),
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

    assert repo.aggregate_and_delete_old_errors(older_than=old_time + timedelta(days=1), limit=10) == 2
    aggregate = migrated_conn.execute(
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
    assert migrated_conn.execute("select count(*) as count from service_executions").fetchone()["count"] == 0
