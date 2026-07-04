from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from data_foundation.source_repository import SourceRepository
from data_foundation.repositories.resource import ResourceRepository


def _register(
    repo: SourceRepository,
    *,
    tenant_id: str = "tenant-a",
    name: str = "source",
    source_type: str = "feishu_base",
    credentials: dict | None = None,
    cursor: dict | None = None,
    schedule_seconds: int = 60,
):
    source = repo.register_source(
        tenant_id=tenant_id,
        source_type=source_type,
        name=name,
        external_id=f"{tenant_id}:{name}",
        credentials=credentials or {"token": f"secret-{tenant_id}-{name}"},
        config={"table": name},
        schedule_seconds=schedule_seconds,
    )
    if cursor is not None:
        repo.finish_source(
            source.id,
            tenant_id=tenant_id,
            lease_owner=None,
            cursor=cursor,
            next_run_after_seconds=0,
        )
        source = repo.get_source(tenant_id=tenant_id, source_id=source.id)
    return source


def test_register_source_is_idempotent_and_keeps_credentials_out_of_public_model(migrated_conn):
    repo = SourceRepository(migrated_conn)

    first = _register(repo, credentials={"access_token": "old"})
    second = repo.register_source(
        tenant_id="tenant-a",
        source_type="feishu_base",
        name="source",
        external_id="tenant-a:source",
        credentials={"access_token": "new"},
        config={"table": "updated"},
        schedule_seconds=120,
    )
    public, secrets = repo.get_source_with_secrets(tenant_id="tenant-a", source_id=first.id)

    assert second.id == first.id
    assert second.config == {"table": "updated"}
    assert second.schedule_seconds == 120
    assert not hasattr(second, "credentials")
    assert public == second
    assert secrets.credentials == {"access_token": "new"}


def test_due_tenants_are_ordered_by_last_dispatch(migrated_conn):
    repo = SourceRepository(migrated_conn)
    _register(repo, tenant_id="old", name="base")
    _register(repo, tenant_id="partly-new", name="old-base")
    _register(repo, tenant_id="partly-new", name="new-base")
    _register(repo, tenant_id="waiting", name="base")
    migrated_conn.execute(
        """
        update sync_sources
        set last_dispatched_at = case tenant_id
          when 'old' then '2026-06-20T02:00:00Z'::timestamptz
          when 'waiting' then null
          when 'partly-new' then case name
            when 'old-base' then '2026-06-20T03:00:00Z'::timestamptz
            else null
          end
        end,
        next_run_at = now() - interval '1 minute'
        """
    )
    migrated_conn.commit()

    assert repo.discover_due_tenants(limit=10)[:3] == ["waiting", "partly-new", "old"]


def test_source_lease_is_tenant_scoped(migrated_conn):
    repo = SourceRepository(migrated_conn)
    source = _register(repo, tenant_id="tenant-a")
    leased = repo.lease_due_source(
        tenant_id="tenant-a",
        lease_owner="worker-a",
        lease_seconds=60,
    )

    assert leased.id == source.id
    assert repo.renew_source(
        source.id,
        tenant_id="tenant-b",
        lease_owner="worker-a",
        lease_seconds=60,
    ) is False
    assert repo.renew_source(
        source.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        lease_seconds=60,
    ) is True


def test_lease_due_source_uses_skip_locked(database_url, migrated_conn):
    repo = SourceRepository(migrated_conn)
    source = _register(repo, tenant_id="tenant-a")
    schema = migrated_conn.execute("select current_schema() as schema").fetchone()["schema"]
    # 与生产 db.connect() 一致:连接级 dict_row 是仓储的单一事实源(仓储不再自行改写连接)。
    first_conn = psycopg.connect(database_url, row_factory=dict_row)
    second_conn = psycopg.connect(database_url, row_factory=dict_row)
    try:
        first_conn.execute(f'set search_path to "{schema}", public')
        second_conn.execute(f'set search_path to "{schema}", public')
        first = SourceRepository(first_conn).lease_due_source(
            tenant_id="tenant-a",
            lease_owner="worker-a",
            lease_seconds=60,
        )
        second = SourceRepository(second_conn).lease_due_source(
            tenant_id="tenant-a",
            lease_owner="worker-b",
            lease_seconds=60,
        )

        assert first.id == source.id
        assert second is None
    finally:
        first_conn.rollback()
        second_conn.rollback()
        first_conn.close()
        second_conn.close()


def test_finish_source_persists_cursor_and_schedules_next_run(migrated_conn):
    repo = SourceRepository(migrated_conn)
    source = _register(repo, tenant_id="tenant-a", schedule_seconds=300)
    leased = repo.lease_due_source(tenant_id="tenant-a", lease_owner="worker-a", lease_seconds=60)

    assert repo.finish_source(
        leased.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        cursor={"page": "next"},
        next_run_after_seconds=300,
    ) is True
    current = repo.get_source(tenant_id="tenant-a", source_id=source.id)

    assert current.cursor == {"page": "next"}
    assert current.lease_owner is None
    assert current.next_run_at > datetime.now(timezone.utc)


def test_sync_run_lifecycle_and_stale_recovery(migrated_conn):
    repo = SourceRepository(migrated_conn)
    source = _register(repo, tenant_id="tenant-a", cursor={"before": 1})
    run_id = repo.start_run(
        source.id,
        tenant_id="tenant-a",
        instance_id=None,
        execution_id=None,
    )

    repo.finish_run(
        run_id,
        tenant_id="tenant-a",
        status="succeeded",
        cursor_after={"after": 2},
        read_count=5,
        created_count=2,
        updated_count=3,
        skipped_count=0,
        failed_count=0,
        error_code=None,
        error_summary=None,
    )
    row = migrated_conn.execute(
        "select status, cursor_before, cursor_after, read_count from sync_runs where id = %s",
        (run_id,),
    ).fetchone()
    assert row["status"] == "succeeded"
    assert dict(row["cursor_before"]) == {"before": 1}
    assert dict(row["cursor_after"]) == {"after": 2}
    assert row["read_count"] == 5

    stale_source = _register(repo, tenant_id="tenant-a", name="stale")
    stale_run_id = repo.start_run(stale_source.id, tenant_id="tenant-a")
    migrated_conn.execute(
        """
        update sync_runs
        set started_at = %s
        where id = %s
        """,
        (datetime.now(timezone.utc) - timedelta(hours=2), stale_run_id),
    )
    migrated_conn.commit()

    assert repo.recover_stale_runs(older_than_seconds=300, limit=10) == 1
    recovered = migrated_conn.execute(
        "select status, error_code from sync_runs where id = %s",
        (stale_run_id,),
    ).fetchone()
    assert recovered["status"] == "stopped"
    assert recovered["error_code"] == "STALE_SYNC_RUN"

    assert repo.finish_run(
        stale_run_id,
        tenant_id="tenant-a",
        status="succeeded",
        cursor_after={},
        read_count=1,
        created_count=1,
        updated_count=0,
        skipped_count=0,
        failed_count=0,
        error_code=None,
        error_summary=None,
    ) is False
    still_recovered = migrated_conn.execute(
        "select status, error_code from sync_runs where id = %s",
        (stale_run_id,),
    ).fetchone()
    assert still_recovered["status"] == "stopped"
    assert still_recovered["error_code"] == "STALE_SYNC_RUN"


def test_sync_run_status_summary_uses_source_repository_lifecycle(migrated_conn):
    source_repo = SourceRepository(migrated_conn)
    resource_repo = ResourceRepository(migrated_conn)
    source = source_repo.register_source(
        tenant_id="default",
        source_type="feishu_base",
        name="manual-feishu-base",
        config={"app_token": "app", "table_id": "tbl"},
        schedule_seconds=60,
    )

    run_id = source_repo.start_run(source.id, tenant_id="default", instance_id=None)
    source_repo.finish_run(
        run_id,
        tenant_id="default",
        status="partial",
        cursor_after={},
        read_count=10,
        created_count=2,
        updated_count=3,
        skipped_count=4,
        failed_count=1,
        error_code=None,
        error_summary="one row failed",
    )

    status = resource_repo.data_foundation_status("default")

    assert status["sync"]["running"] is False
    assert status["sync"]["last_status"] == "partial"
    assert status["sync"]["last_error_summary"] == "one row failed"
    assert status["sync"]["last_counts"] == {
        "created": 2,
        "updated": 3,
        "skipped": 4,
        "failed": 1,
    }


def test_recover_stale_runs_does_not_clear_new_valid_source_lease(migrated_conn):
    repo = SourceRepository(migrated_conn)
    source = _register(repo, tenant_id="tenant-a")
    stale_run_id = repo.start_run(source.id, tenant_id="tenant-a")
    migrated_conn.execute(
        """
        update sync_runs
        set started_at = %s
        where id = %s
        """,
        (datetime.now(timezone.utc) - timedelta(hours=2), stale_run_id),
    )
    migrated_conn.commit()
    leased = repo.lease_due_source(tenant_id="tenant-a", lease_owner="worker-new", lease_seconds=600)

    assert leased.lease_owner == "worker-new"
    assert repo.recover_stale_runs(older_than_seconds=300, limit=10) == 1
    current = repo.get_source(tenant_id="tenant-a", source_id=source.id)
    assert current.lease_owner == "worker-new"


def test_finish_run_redacts_error_summary_before_persisting(migrated_conn):
    repo = SourceRepository(migrated_conn)
    source = _register(repo, tenant_id="tenant-a")
    run_id = repo.start_run(source.id, tenant_id="tenant-a")

    assert repo.finish_run(
        run_id,
        tenant_id="tenant-a",
        status="failed",
        cursor_after=None,
        read_count=0,
        created_count=0,
        updated_count=0,
        skipped_count=0,
        failed_count=1,
        error_code=None,
        error_summary="request failed api_key=super-secret token=also-secret",
    ) is True
    row = migrated_conn.execute(
        "select error_code, error_summary from sync_runs where id = %s",
        (run_id,),
    ).fetchone()

    assert row["error_code"] == "internal_error"
    assert "super-secret" not in row["error_summary"]
    assert "also-secret" not in row["error_summary"]
    assert "api_key=<redacted>" in row["error_summary"]


def test_finish_run_rolls_back_and_keeps_connection_usable_on_failure(migrated_conn, monkeypatch):
    """缺陷3 回归:finish_run 的 update 失败必须回滚,连接不进 aborted 态级联拖垮整轮。

    原裸 commit 无 rollback —— 一条 execute 失败后连接 aborted,后续任何语句报
    'current transaction is aborted',整轮所有后续租户 finish_run 连环失败。
    改 with transaction 后:异常自动 rollback,连接回到干净态可继续用。
    """
    repo = SourceRepository(migrated_conn)
    source = _register(repo, tenant_id="tenant-a", name="s-rollback")
    run_id = repo.start_run(source.id, tenant_id="tenant-a")

    real_execute = migrated_conn.execute
    calls = {"n": 0}

    def failing_execute(sql, params=None):
        # 只让 finish_run 的 update sync_runs 失败一次,模拟 DB 抖动
        if "update sync_runs" in str(sql).lower() and calls["n"] == 0:
            calls["n"] += 1
            raise psycopg.errors.OperationalError("simulated transient DB error")
        return real_execute(sql, params)

    monkeypatch.setattr(migrated_conn, "execute", failing_execute)
    try:
        raised = False
        try:
            repo.finish_run(
                run_id, tenant_id="tenant-a", status="succeeded", cursor_after=None,
                read_count=0, created_count=0, updated_count=0, skipped_count=0,
                failed_count=0, error_code=None, error_summary=None,
            )
        except Exception:
            raised = True
        assert raised
    finally:
        monkeypatch.undo()

    # 关键:连接未 aborted,后续语句正常执行(不报 current transaction is aborted)。
    row = migrated_conn.execute("select 1 as ok").fetchone()
    assert row["ok"] == 1
    # run 仍是 running(回滚了失败的 finish),可被后续正常 finish。
    assert repo.finish_run(
        run_id, tenant_id="tenant-a", status="succeeded", cursor_after=None,
        read_count=0, created_count=0, updated_count=0, skipped_count=0,
        failed_count=0, error_code=None, error_summary=None,
    ) is True
