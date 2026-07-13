from dataclasses import FrozenInstanceError
from pathlib import Path
import tomllib
from typing import get_type_hints

import psycopg
import pytest

from data_foundation import db, models


EXPECTED_TABLES = {
    "user_skills",
    "user_skill_versions",
    "user_skill_publications",
    "user_skill_audit_events",
    "user_skill_revisions",
    "resources",
    "resource_type_counts",
    "resource_versions",
    "resource_events",
    "resource_mappings",
    "resource_permissions",
    "resource_embeddings",
    "resource_edges",
    "resource_outbox",
    "embedding_indexes",
    "sync_sources",
    "sync_runs",
    "service_instances",
    "service_executions",
    "service_error_aggregates",
}


def _columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        """
        select column_name
        from information_schema.columns
        where table_schema = current_schema() and table_name = %s
        """,
        (table,),
    ).fetchall()
    return {row[0] for row in rows}


def _vector() -> list[float]:
    return [0.0] * 1536


def _insert_resource_version(conn, tenant_id: str = "tenant-a") -> tuple[str, int]:
    resource_id = conn.execute(
        "insert into resources(tenant_id, type, title) values (%s, 'document', 'Title') returning id",
        (tenant_id,),
    ).fetchone()[0]
    version = 1
    conn.execute(
        """
        insert into resource_versions(resource_id, tenant_id, version, content_hash)
        values (%s, %s, %s, 'hash')
        """,
        (resource_id, tenant_id, version),
    )
    return str(resource_id), version


def _insert_embedding_index(
    conn,
    tenant_id: str = "tenant-a",
    config_version: str = "2026-06-20T10:00:00Z-a1b2",
    status: str = "building",
) -> str:
    return str(
        conn.execute(
            """
            insert into embedding_indexes
              (tenant_id, embedding_model, config_version, dimensions, status)
            values (%s, 'embedding-model', %s, 1536, %s)
            returning id
            """,
            (tenant_id, config_version, status),
        ).fetchone()[0]
    )


def test_schema_sql_is_packaged_for_installed_deployments():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]
    assert "schema.sql" in package_data["data_foundation"]


def test_schema_source_declares_clean_operational_contract():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    for table in EXPECTED_TABLES:
        assert f"create table if not exists {table}" in schema
    assert "available_at" not in schema
    assert "last_error " not in schema
    assert "public.vector(1536)" in schema
    assert "next_attempt_at" in schema
    assert "lease_expires_at" in schema
    assert "dedupe_key text not null" in schema
    assert "unique (tenant_id, dedupe_key)" in schema
    assert "dedupe_key text not null unique" not in schema
    assert "current_version" not in schema
    assert "config_version int" not in schema
    assert "nulls not distinct" in schema


def test_schema_declares_isolated_immutable_user_skill_contract():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists user_skills" in schema
    assert "create table if not exists user_skill_versions" in schema
    assert "create table if not exists user_skill_publications" in schema
    assert "create table if not exists user_skill_audit_events" in schema
    assert "create table if not exists user_skill_revisions" in schema
    assert "references resources" not in schema.split("create table if not exists user_skills", 1)[1].split(
        "create table if not exists resources", 1
    )[0]
    assert "before update or delete on user_skill_versions" in schema
    assert "before update or delete on user_skill_audit_events" in schema
    assert "foreign key (tenant_id, owner_open_id, skill_id, published_version)" in schema
    assert "where archived_at is null" in schema


def test_schema_source_enforces_tenant_scoped_resource_references():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "foreign key (tenant_id, resource_id)\n    references resources(tenant_id, id)" in schema
    assert schema.count("foreign key (tenant_id, resource_id)\n    references resources(tenant_id, id)") == 4
    assert "foreign key (tenant_id, source_resource_id)\n    references resources(tenant_id, id)" in schema
    assert "foreign key (tenant_id, target_resource_id)\n    references resources(tenant_id, id)" in schema
    assert "foreign key (tenant_id, event_id)\n    references resource_events(tenant_id, id)" in schema
    assert "unique (tenant_id, id, embedding_model, chunker_version)" in schema
    assert (
        "foreign key (tenant_id, embedding_index_id, embedding_model, chunker_version)\n"
        "    references embedding_indexes(tenant_id, id, embedding_model, chunker_version)"
    ) in schema
    assert "unique (tenant_id, id)" in schema
    assert "foreign key (tenant_id, execution_id)\n    references service_executions(tenant_id, id)" in schema


def test_schema_source_uses_tenant_recent_resource_version_index_and_safe_reset():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()
    reset_source = Path("data_foundation/db.py").read_text(encoding="utf-8").lower()

    assert "idx_resource_versions_tenant_recent" in schema
    assert "on resource_versions (tenant_id, created_at desc)" in schema
    assert "cascade" not in reset_source


def test_schema_source_qualifies_trigram_operator_class_for_custom_search_paths():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "create extension if not exists vector with schema public" in schema
    assert "create extension if not exists pg_trgm with schema public" in schema
    assert "public.vector(1536)" in schema
    assert "public.vector_cosine_ops" in schema
    assert "public.gin_trgm_ops" in schema


def test_schema_source_aligns_source_ready_index_with_dispatch_order():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "drop index if exists idx_sync_sources_ready;" in schema
    assert "drop index if exists idx_sync_sources_ready_tenant;" in schema
    assert "idx_sync_sources_ready_tenant_ordered" in schema
    assert "on sync_sources (tenant_id, last_dispatched_at nulls first, next_run_at, id)" in schema
    assert "idx_sync_sources_due_tenants" in schema
    assert "on sync_sources (next_run_at, tenant_id, last_dispatched_at nulls first)" in schema
    assert "where enabled" in schema


def test_schema_declares_universal_work_discovery_indexes():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "idx_resources_embedding_work_tenants" in schema
    assert "on resources (tenant_id, id)" in schema
    assert "nullif(trim(coalesce(content_text, '')), '') is not null" in schema
    assert "idx_resource_outbox_ready_tenants" in schema
    assert "on resource_outbox (next_attempt_at, tenant_id)" in schema


def test_schema_source_counts_have_tenant_first_indexes():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "idx_sync_sources_tenant_due" in schema
    assert "on sync_sources (tenant_id, next_run_at, lease_expires_at)" in schema
    assert "where enabled" in schema
    assert "idx_sync_sources_tenant_running" in schema
    assert "on sync_sources (tenant_id, lease_expires_at)" in schema
    assert "where enabled and lease_expires_at is not null" in schema


def test_schema_source_replaces_legacy_runtime_fact_indexes():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "idx_resource_outbox_tenant_status" in schema
    assert "on resource_outbox (tenant_id, status)" in schema
    assert "drop index if exists idx_embedding_indexes_tenant_recent;" in schema
    assert "idx_embedding_indexes_tenant_status_recent" in schema
    assert "on embedding_indexes (tenant_id, status, created_at desc, id desc)" in schema
    assert "where status in ('active', 'building')" in schema
    assert "drop index if exists idx_service_error_aggregates_tenant_recent;" in schema
    assert "idx_service_error_aggregates_tenant_recent_ordered" in schema
    assert "on service_error_aggregates (tenant_id, window_started_at desc, window_ended_at desc, id desc)" in schema


def test_schema_source_declares_resource_type_count_facts():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "create table if not exists resource_type_counts" in schema
    assert "primary key (tenant_id, type)" in schema
    assert "count bigint not null default 0 check (count >= 0)" in schema
    assert "insert into resource_type_counts (tenant_id, type, count)" in schema
    assert "select tenant_id, type, count(*)" in schema
    assert "from resources" in schema
    assert "on conflict (tenant_id, type) do update" in schema


def test_schema_source_declares_sync_run_running_indexes():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()

    assert "idx_sync_runs_tenant_running" in schema
    assert "on sync_runs (tenant_id, started_at desc, id desc)" in schema
    assert "idx_sync_runs_stale_running" in schema
    assert "on sync_runs (started_at, id)" in schema
    assert "where status = 'running'" in schema


def test_reset_allowlist_contains_only_all_operational_tables():
    assert set(db.DATA_FOUNDATION_TABLES) == EXPECTED_TABLES


def test_operational_records_are_frozen_and_hide_source_credentials():
    required = {
        "OutboxItem",
        "OutboxRequest",
        "SyncSource",
        "SourceSecrets",
        "EmbeddingIndex",
        "ServiceExecution",
        "ProcessorState",
    }
    assert required <= set(vars(models))
    assert "credentials" not in models.SyncSource.__dataclass_fields__
    request = models.OutboxRequest("embedding_generate", ("v1",), {"version": 1})
    with pytest.raises(FrozenInstanceError):
        request.topic = "changed"


def test_model_config_versions_are_strings():
    assert get_type_hints(models.EmbeddingIndex)["config_version"] is str
    assert get_type_hints(models.ServiceExecution)["config_version"] == str | None
    assert get_type_hints(models.ProcessorState)["config_version"] == str | None


def test_schema_enables_required_extensions(migrated_conn):
    rows = migrated_conn.execute(
        "select extname from pg_extension where extname in ('pgcrypto', 'vector', 'pg_trgm')"
    ).fetchall()
    exts = {row[0] for row in rows}
    if "vector" not in exts:
        assert exts == {"pgcrypto", "pg_trgm"}
    else:
        assert exts == {"pgcrypto", "vector", "pg_trgm"}


def test_schema_creates_operational_tables(migrated_conn):
    rows = migrated_conn.execute(
        "select table_name from information_schema.tables where table_schema=current_schema()"
    ).fetchall()
    assert {row[0] for row in rows} == EXPECTED_TABLES


def test_schema_is_idempotent(migrated_conn):
    db.run_migrations(migrated_conn)
    rows = migrated_conn.execute(
        "select table_name from information_schema.tables where table_schema=current_schema()"
    ).fetchall()
    assert {row[0] for row in rows} == EXPECTED_TABLES


def test_config_version_columns_are_text(migrated_conn):
    rows = migrated_conn.execute(
        """
        select table_name, data_type
        from information_schema.columns
        where table_schema = current_schema() and column_name = 'config_version'
        """
    ).fetchall()
    assert {row[0]: row[1] for row in rows} == {
        "embedding_indexes": "text",
        "service_executions": "text",
        "service_instances": "text",
    }


def test_outbox_has_new_lease_fields_without_legacy_fields(migrated_conn):
    columns = _columns(migrated_conn, "resource_outbox")
    assert {
        "dedupe_key",
        "resource_version",
        "next_attempt_at",
        "lease_owner",
        "lease_expires_at",
        "error_code",
        "error_summary",
        "dead_at",
    } <= columns
    assert {"available_at", "last_error"}.isdisjoint(columns)


def test_outbox_rejects_legacy_status(migrated_conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        migrated_conn.execute(
            """
            insert into resource_outbox(tenant_id, topic, dedupe_key, status)
            values (%s, %s, %s, %s)
            """,
            ("tenant-a", "embedding_generate", "key", "failed"),
        )


def test_outbox_dedupe_key_is_unique(migrated_conn):
    migrated_conn.execute(
        """
        insert into resource_outbox(tenant_id, topic, dedupe_key)
        values ('tenant-a', 'embedding_generate', 'same-key')
        """
    )
    with pytest.raises(psycopg.errors.UniqueViolation):
        migrated_conn.execute(
            """
            insert into resource_outbox(tenant_id, topic, dedupe_key)
            values ('tenant-a', 'embedding_generate', 'same-key')
            """
        )


def test_only_one_active_embedding_index_per_tenant(migrated_conn):
    _insert_embedding_index(migrated_conn, status="active")
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_embedding_index(
            migrated_conn,
            config_version="2026-06-20T10:01:00Z-b2c3",
            status="active",
        )


def test_same_model_chunks_can_coexist_in_two_embedding_indexes(migrated_conn):
    resource_id, version = _insert_resource_version(migrated_conn)
    first_index = _insert_embedding_index(migrated_conn)
    second_index = _insert_embedding_index(
        migrated_conn, config_version="2026-06-20T10:01:00Z-b2c3"
    )

    for index_id in (first_index, second_index):
        migrated_conn.execute(
            """
            insert into resource_embeddings
              (tenant_id, resource_id, resource_version, embedding_index_id,
               chunk_index, chunk_text, chunker_version, embedding_model, embedding)
            values (%s, %s, %s, %s, 0, 'chunk', 'v1', 'embedding-model', %s)
            """,
            ("tenant-a", resource_id, version, index_id, _vector()),
        )

    assert migrated_conn.execute("select count(*) from resource_embeddings").fetchone()[0] == 2


@pytest.mark.parametrize("target", ["embedding_resource", "embedding_index", "outbox"])
def test_resource_references_reject_cross_tenant_rows(migrated_conn, target):
    resource_id, version = _insert_resource_version(migrated_conn, "tenant-a")
    if target == "embedding_resource":
        index_id = _insert_embedding_index(migrated_conn, "tenant-b")
        statement = """
            insert into resource_embeddings
              (tenant_id, resource_id, resource_version, embedding_index_id,
               chunk_index, chunk_text, chunker_version, embedding_model, embedding)
            values ('tenant-b', %s, %s, %s, 0, 'chunk', 'v1', 'embedding-model', %s)
        """
        params = (resource_id, version, index_id, _vector())
    elif target == "embedding_index":
        index_id = _insert_embedding_index(migrated_conn, "tenant-b")
        statement = """
            insert into resource_embeddings
              (tenant_id, resource_id, resource_version, embedding_index_id,
               chunk_index, chunk_text, chunker_version, embedding_model, embedding)
            values ('tenant-a', %s, %s, %s, 0, 'chunk', 'v1', 'embedding-model', %s)
        """
        params = (resource_id, version, index_id, _vector())
    else:
        statement = """
            insert into resource_outbox
              (tenant_id, resource_id, resource_version, topic, dedupe_key)
            values ('tenant-b', %s, %s, 'embedding_generate', 'cross-tenant')
        """
        params = (resource_id, version)

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(statement, params)


@pytest.mark.parametrize(
    ("table", "statement"),
    [
        (
            "resource_mappings",
            """
            insert into resource_mappings
              (tenant_id, resource_id, system, external_type, external_id)
            values ('tenant-b', %s, 'feishu', 'docx', 'mapping-cross-tenant')
            """,
        ),
        (
            "resource_events",
            """
            insert into resource_events(tenant_id, resource_id, event_type)
            values ('tenant-b', %s, 'updated')
            """,
        ),
        (
            "resource_permissions",
            """
            insert into resource_permissions
              (tenant_id, resource_id, subject_type, subject_id, permission)
            values ('tenant-b', %s, 'user', 'ou_user', 'read')
            """,
        ),
    ],
)
def test_resource_owned_rows_reject_cross_tenant_resources(migrated_conn, table, statement):
    resource_id, _ = _insert_resource_version(migrated_conn, "tenant-a")

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(statement, (resource_id,))


def test_edges_reject_cross_tenant_endpoints(migrated_conn):
    source_id, _ = _insert_resource_version(migrated_conn, "tenant-a")
    target_id, _ = _insert_resource_version(migrated_conn, "tenant-b")

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(
            """
            insert into resource_edges
              (tenant_id, source_resource_id, target_resource_id, edge_type)
            values ('tenant-a', %s, %s, 'references')
            """,
            (source_id, target_id),
        )


def test_outbox_rejects_cross_tenant_event(migrated_conn):
    event_id = migrated_conn.execute(
        """
        insert into resource_events(tenant_id, event_type)
        values ('tenant-a', 'updated')
        returning id
        """
    ).fetchone()[0]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(
            """
            insert into resource_outbox(tenant_id, event_id, topic, dedupe_key)
            values ('tenant-b', %s, 'embedding_generate', 'event-cross-tenant')
            """,
            (event_id,),
        )


def test_sync_run_source_tenant_must_match(migrated_conn):
    source_id = migrated_conn.execute(
        """
        insert into sync_sources
          (tenant_id, source_type, name, credentials, schedule_seconds)
        values ('tenant-a', 'feishu_base', 'source', '{}', 60)
        returning id
        """
    ).fetchone()[0]
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(
            """
            insert into sync_runs(sync_source_id, tenant_id, source_type)
            values (%s, 'tenant-b', 'feishu_base')
            """,
            (source_id,),
        )


def test_sync_run_execution_tenant_must_match(migrated_conn):
    migrated_conn.execute(
        """
        insert into service_instances(instance_id, deployment_id, component)
        values ('inst-a', 'deploy-a', 'sync')
        """
    )
    execution_id = migrated_conn.execute(
        """
        insert into service_executions(component, instance_id, tenant_id, operation, status)
        values ('sync', 'inst-a', 'tenant-a', 'ingest', 'running')
        returning id
        """
    ).fetchone()[0]

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(
            """
            insert into sync_runs(tenant_id, source_type, execution_id)
            values ('tenant-b', 'feishu_base', %s)
            """,
            (execution_id,),
        )


def test_embedding_index_model_and_chunker_must_match(migrated_conn):
    resource_id, version = _insert_resource_version(migrated_conn, "tenant-a")
    index_id = _insert_embedding_index(migrated_conn, "tenant-a")

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        migrated_conn.execute(
            """
            insert into resource_embeddings
              (tenant_id, resource_id, resource_version, embedding_index_id,
               chunk_index, chunk_text, chunker_version, embedding_model, embedding)
            values ('tenant-a', %s, %s, %s, 0, 'chunk', 'v1', 'other-model', %s)
            """,
            (resource_id, version, index_id, _vector()),
        )


def test_manual_sync_run_can_omit_registered_source(migrated_conn):
    migrated_conn.execute(
        """
        insert into sync_runs(sync_source_id, tenant_id, source_type)
        values (null, 'tenant-a', 'feishu_base')
        """
    )


def test_null_error_aggregate_dimensions_are_still_unique(migrated_conn):
    values = ("2026-06-20T10:00:00Z", "2026-06-20T11:00:00Z", "scheduler", "timeout")
    statement = """
        insert into service_error_aggregates
          (window_started_at, window_ended_at, tenant_id, component, operation,
           error_code, error_count)
        values (%s, %s, null, %s, null, %s, 1)
    """
    migrated_conn.execute(statement, values)
    with pytest.raises(psycopg.errors.UniqueViolation):
        migrated_conn.execute(statement, values)


def test_ready_and_lease_indexes_cover_operational_queues(migrated_conn):
    rows = migrated_conn.execute(
        """
        select indexname, indexdef
        from pg_indexes
        where schemaname = current_schema()
        """
    ).fetchall()
    indexes = {row[0]: row[1].lower() for row in rows}

    assert "idx_resource_outbox_ready" not in indexes
    assert "(tenant_id, status, topic, next_attempt_at, created_at, id)" in indexes[
        "idx_resource_outbox_ready_tenant"
    ]
    assert "where" in indexes["idx_resource_outbox_ready_tenant"]
    assert "pending" in indexes["idx_resource_outbox_ready_tenant"]
    assert "retry" in indexes["idx_resource_outbox_ready_tenant"]
    assert "(lease_expires_at)" in indexes["idx_resource_outbox_lease"]
    assert "idx_sync_sources_ready" not in indexes
    assert "idx_sync_sources_ready_tenant" not in indexes
    assert "last_dispatched_at nulls first" in indexes["idx_sync_sources_ready_tenant_ordered"]
    assert "where enabled" in indexes["idx_sync_sources_ready_tenant_ordered"]
    assert "(next_run_at, tenant_id, last_dispatched_at nulls first)" in indexes[
        "idx_sync_sources_due_tenants"
    ]
    assert "where enabled" in indexes["idx_sync_sources_due_tenants"]
    assert "(tenant_id, next_run_at, lease_expires_at)" in indexes["idx_sync_sources_tenant_due"]
    assert "where enabled" in indexes["idx_sync_sources_tenant_due"]
    assert "(tenant_id, lease_expires_at)" in indexes["idx_sync_sources_tenant_running"]
    assert "enabled" in indexes["idx_sync_sources_tenant_running"]
    assert "lease_expires_at is not null" in indexes["idx_sync_sources_tenant_running"]
    assert "(lease_expires_at)" in indexes["idx_sync_sources_lease"]


def test_runtime_fact_indexes_cover_status_aggregation_paths(migrated_conn):
    rows = migrated_conn.execute(
        """
        select indexname, indexdef
        from pg_indexes
        where schemaname = current_schema()
        """
    ).fetchall()
    indexes = {row[0]: row[1].lower() for row in rows}

    assert "(tenant_id, status)" in indexes["idx_resource_outbox_tenant_status"]
    assert "idx_embedding_indexes_tenant_recent" not in indexes
    assert "(tenant_id, status, created_at desc, id desc)" in indexes[
        "idx_embedding_indexes_tenant_status_recent"
    ]
    assert "active" in indexes["idx_embedding_indexes_tenant_status_recent"]
    assert "building" in indexes["idx_embedding_indexes_tenant_status_recent"]
    assert "idx_service_error_aggregates_tenant_recent" not in indexes
    assert "(tenant_id, window_started_at desc, window_ended_at desc, id desc)" in indexes[
        "idx_service_error_aggregates_tenant_recent_ordered"
    ]


def test_sync_run_running_indexes_cover_status_and_stale_recovery(migrated_conn):
    rows = migrated_conn.execute(
        """
        select indexname, indexdef
        from pg_indexes
        where schemaname = current_schema()
        """
    ).fetchall()
    indexes = {row[0]: row[1].lower() for row in rows}

    assert "(tenant_id, started_at desc, id desc)" in indexes["idx_sync_runs_tenant_running"]
    assert "where (status = 'running'" in indexes["idx_sync_runs_tenant_running"]
    assert "(started_at, id)" in indexes["idx_sync_runs_stale_running"]
    assert "where (status = 'running'" in indexes["idx_sync_runs_stale_running"]


def test_resource_content_trigram_index_supports_keyword_fallback(migrated_conn):
    rows = migrated_conn.execute(
        """
        select indexname, indexdef
        from pg_indexes
        where schemaname = current_schema()
        """
    ).fetchall()
    indexes = {row[0]: row[1].lower() for row in rows}
    indexdef = indexes["idx_resources_trgm_content"]

    assert "using gin" in indexdef
    assert "gin_trgm_ops" in indexdef
    assert "coalesce(title" in indexdef
    assert "coalesce(summary" in indexdef
    assert "coalesce(content_text" in indexdef


def test_embedding_dimension_and_source_type_constraints(migrated_conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        migrated_conn.execute(
            """
            insert into embedding_indexes
              (tenant_id, embedding_model, config_version, dimensions, status)
            values ('tenant-a', 'model', '2026-06-20T10:00:00Z-a1b2', 768, 'building')
            """
        )
    migrated_conn.rollback()
    with pytest.raises(psycopg.errors.CheckViolation):
        migrated_conn.execute(
            """
            insert into sync_sources
              (tenant_id, source_type, name, credentials, schedule_seconds)
            values ('tenant-a', 'mysql_table', 'bad', '{}', 60)
            """
        )


def test_reset_preserves_non_business_tables(migrated_conn):
    migrated_conn.execute("create table lark_uat_tokens (id text primary key)")
    migrated_conn.execute("insert into lark_uat_tokens values ('keep-me')")

    db.reset_data_foundation(migrated_conn)

    assert migrated_conn.execute("select id from lark_uat_tokens").fetchone()[0] == "keep-me"
    rows = migrated_conn.execute(
        "select table_name from information_schema.tables where table_schema=current_schema()"
    ).fetchall()
    assert {row[0] for row in rows} == EXPECTED_TABLES | {"lark_uat_tokens"}


def test_reset_refuses_to_damage_non_business_dependents(migrated_conn):
    migrated_conn.execute(
        """
        create table audit_resource_links (
          id uuid primary key,
          resource_id uuid not null references resources(id)
        )
        """
    )

    with pytest.raises(psycopg.errors.DependentObjectsStillExist):
        db.reset_data_foundation(migrated_conn)

    assert migrated_conn.execute(
        "select 1 from information_schema.table_constraints "
        "where table_schema = current_schema() and table_name = 'audit_resource_links' "
        "and constraint_type = 'FOREIGN KEY'"
    ).fetchone() == (1,)
