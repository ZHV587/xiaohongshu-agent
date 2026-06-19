import tomllib
from pathlib import Path


def test_schema_sql_is_packaged_for_installed_deployments():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    assert "schema.sql" in package_data["data_foundation"]


def test_schema_enables_required_extensions(migrated_conn):
    rows = migrated_conn.execute(
        "select extname from pg_extension where extname in ('pgcrypto', 'vector')"
    ).fetchall()
    assert {row[0] for row in rows} == {"pgcrypto", "vector"}


def test_schema_creates_core_tables(migrated_conn):
    rows = migrated_conn.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = current_schema()
        order by table_name
        """
    ).fetchall()
    assert [row[0] for row in rows] == [
        "resource_edges",
        "resource_embeddings",
        "resource_events",
        "resource_mappings",
        "resource_outbox",
        "resource_permissions",
        "resource_versions",
        "resources",
        "sync_runs",
    ]


def test_schema_is_idempotent(migrated_conn):
    from data_foundation.db import run_migrations

    run_migrations(migrated_conn)
    count = migrated_conn.execute(
        "select count(*) from information_schema.tables where table_schema = current_schema()"
    ).fetchone()[0]
    assert count == 9


def test_sync_runs_schema_exists(migrated_conn):
    columns = migrated_conn.execute(
        """
        select column_name
        from information_schema.columns
        where table_schema = current_schema()
          and table_name = 'sync_runs'
        order by ordinal_position
        """
    ).fetchall()

    assert [row[0] for row in columns] == [
        "id",
        "tenant_id",
        "source",
        "triggered_by",
        "actor_open_id",
        "status",
        "started_at",
        "finished_at",
        "created_count",
        "updated_count",
        "skipped_count",
        "failed_count",
        "error",
        "metadata",
        "created_at",
        "updated_at",
    ]


def test_sync_runs_status_constraint(migrated_conn):
    import pytest

    with pytest.raises(Exception):
        migrated_conn.execute(
            """
            insert into sync_runs (tenant_id, source, triggered_by, actor_open_id, status)
            values ('default', 'feishu', 'manual', 'ou_user', 'bad-status')
            """
        )
