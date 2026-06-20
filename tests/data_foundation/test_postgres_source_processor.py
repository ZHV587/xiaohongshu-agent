from __future__ import annotations

from datetime import datetime, timezone

import pytest

from data_foundation.models import SourceSecrets, SyncSource
from data_foundation.repository import ResourceRepository
from data_foundation.sources.base import SourceContext, SourceLease
from data_foundation.sources.postgres import (
    PostgresTableConfig,
    PostgresTableSourceProcessor,
    SourceConfigError,
)
from data_foundation.sources.registry import default_source_registry


class RecordingLease(SourceLease):
    def __init__(self):
        self.renewed = 0

    async def assert_owned(self) -> None:
        self.renewed += 1


def _valid_mapping(**overrides):
    return {
        "schema": "public",
        "table": "records",
        "primary_key": "id",
        "title_column": "title",
        "content_columns": ["body", "extra"],
        "updated_at_column": "updated_at",
        "resource_type": "external_note",
        "page_size": 2,
    } | overrides


def _source_context(*, database_url: str, config: dict, cursor: dict | None = None) -> SourceContext:
    return SourceContext(
        source=SyncSource(
            id="source-1",
            tenant_id="tenant-a",
            source_type="postgres_table",
            name="外部表",
            external_id=None,
            config=config,
            enabled=True,
            schedule_seconds=60,
            next_run_at=None,
            last_dispatched_at=None,
            lease_owner="worker-a",
            lease_expires_at=None,
            cursor=cursor or {},
            created_at=None,
            updated_at=None,
        ),
        secrets=SourceSecrets(credentials={"dsn": database_url}),
        actor_open_id="ou_sync",
    )


def _current_schema(conn) -> str:
    row = conn.execute("select current_schema() as schema").fetchone()
    return row["schema"] if isinstance(row, dict) else row[0]


def test_postgres_source_rejects_arbitrary_sql():
    with pytest.raises(SourceConfigError, match="sql"):
        PostgresTableConfig.from_dict(_valid_mapping(sql="drop table users"))


def test_postgres_source_rejects_dangerous_identifier():
    with pytest.raises(SourceConfigError, match="table"):
        PostgresTableConfig.from_dict(_valid_mapping(table="records;drop table x"))


def test_default_source_registry_includes_postgres_processor(migrated_conn):
    registry = default_source_registry(ResourceRepository(migrated_conn))

    assert isinstance(registry.processor_for("postgres_table"), PostgresTableSourceProcessor)


@pytest.mark.asyncio
async def test_postgres_source_keyset_paginates_read_only_and_updates_cursor(database_url, migrated_conn):
    schema = _current_schema(migrated_conn)
    migrated_conn.execute(
        """
        create table external_records (
          id int primary key,
          title text not null,
          body text,
          extra text,
          updated_at timestamptz
        )
        """
    )
    migrated_conn.execute(
        """
        insert into external_records(id, title, body, extra, updated_at)
        values
          (1, '标题一', '正文一', '补充一', '2026-06-20T08:00:00Z'),
          (2, '标题二', '正文二', '补充二', '2026-06-20T09:00:00Z'),
          (3, '标题三', '正文三', null, '2026-06-20T10:00:00Z')
        """
    )
    migrated_conn.commit()
    repo = ResourceRepository(migrated_conn)
    processor = PostgresTableSourceProcessor(resource_repo=repo)
    lease = RecordingLease()

    result = await processor.sync(
        _source_context(
            database_url=database_url,
            config=_valid_mapping(schema=schema, table="external_records"),
        ),
        lease,
    )

    assert result.status == "succeeded"
    assert result.read_count == 3
    assert result.created_count == 3
    assert result.cursor == {"last_pk": "3"}
    assert lease.renewed == 2
    assert processor.last_observed_transaction_read_only is True

    rows = migrated_conn.execute(
        """
        select r.title, r.content_text, r.content_json, rm.external_type, rm.external_id, rm.external_updated_at
        from resources r
        join resource_mappings rm on rm.tenant_id = r.tenant_id and rm.resource_id = r.id
        where r.tenant_id = 'tenant-a'
        order by rm.external_id
        """
    ).fetchall()
    assert [row["title"] for row in rows] == ["标题一", "标题二", "标题三"]
    assert rows[0]["content_text"] == "正文一\n补充一"
    assert rows[0]["content_json"] == {"body": "正文一", "extra": "补充一", "id": 1}
    assert rows[0]["external_type"] == f"{schema}.external_records"
    assert rows[0]["external_id"] == "1"
    assert rows[0]["external_updated_at"] == datetime(2026, 6, 20, 8, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_postgres_source_resumes_after_cursor(database_url, migrated_conn):
    schema = _current_schema(migrated_conn)
    migrated_conn.execute("create table external_resume (id int primary key, title text, body text)")
    migrated_conn.execute(
        """
        insert into external_resume(id, title, body)
        values (1, '旧', '旧正文'), (2, '新', '新正文')
        """
    )
    migrated_conn.commit()

    result = await PostgresTableSourceProcessor(resource_repo=ResourceRepository(migrated_conn)).sync(
        _source_context(
            database_url=database_url,
            config=_valid_mapping(
                schema=schema,
                table="external_resume",
                content_columns=["body"],
                updated_at_column=None,
            ),
            cursor={"last_pk": "1"},
        ),
        RecordingLease(),
    )

    assert result.read_count == 1
    assert result.cursor == {"last_pk": "2"}
    assert migrated_conn.execute("select count(*) as count from resources").fetchone()["count"] == 1


@pytest.mark.asyncio
async def test_postgres_source_rejects_non_postgres_dsn(migrated_conn):
    result = await PostgresTableSourceProcessor(resource_repo=ResourceRepository(migrated_conn)).sync(
        _source_context(
            database_url="mysql://user:pass@localhost/db",
            config=_valid_mapping(),
        ),
        RecordingLease(),
    )

    assert result.status == "failed"
    assert result.failed_count == 1
    assert "mysql://user:pass" not in result.errors[0]
