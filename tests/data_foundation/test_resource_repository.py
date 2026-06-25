import pytest
import re
import importlib.resources
import data_foundation.db
from data_foundation.models import Resource, RuntimeIdentityConfig

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

# Import ResourceRepository afterwards
from data_foundation.repositories.resource import ResourceRepository

def test_upsert_resource_inserts_correctly(migrated_conn):
    repo = ResourceRepository()
    actor = RuntimeIdentityConfig(tenant_id="test_tenant", open_id="test_user")
    res = Resource(
        id=None,
        tenant_id="test_tenant",
        type="xhs_copy",
        title="Test Resource",
        summary=None,
        content_text="Test Content",
        content_json={},
        status="active",
        visibility="private",
        owner_open_id="test_user",
        created_at=None,
        updated_at=None
    )
    # Exclude non-existent fields for now, ensure standard models fields align with schema
    saved = repo.upsert_resource(res, actor=actor, conn=migrated_conn)
    assert saved.id is not None
    assert saved.title == "Test Resource"
