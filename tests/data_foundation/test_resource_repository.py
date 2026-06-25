import pytest
import re
import importlib.resources
import data_foundation.db
from psycopg.rows import dict_row
from data_foundation.models import Resource, RuntimeIdentityConfig

from data_foundation.repositories.resource import ResourceRepository

def test_upsert_resource_inserts_correctly(migrated_conn):
    repo = ResourceRepository()
    actor = RuntimeIdentityConfig(tenant_id="test_tenant", open_id="test_user")
    res = Resource(
        id=None,
        tenant_id="test_tenant",
        type="xhs_copy",
        title="Test Resource",
        summary="Test Summary",
        content_text="Test Content",
        content_json={"foo": "bar"},
        status="active",
        visibility="private",
        owner_open_id="test_user",
        created_at=None,
        updated_at=None
    )
    saved = repo.upsert_resource(res, actor=actor, conn=migrated_conn)
    assert saved.id is not None
    assert saved.title == "Test Resource"
    assert saved.version == 1

    # 1. Verify resource version was created, event logged, outbox enqueued, type counts updated
    with migrated_conn.cursor(row_factory=dict_row) as cursor:
        versions = cursor.execute(
            "select version, content_text, content_json from resource_versions where resource_id = %s",
            (saved.id,)
        ).fetchall()
        assert len(versions) == 1
        assert versions[0]["version"] == 1
        assert versions[0]["content_text"] == "Test Content"
        assert versions[0]["content_json"] == {"foo": "bar"}

        events = cursor.execute(
            "select event_type, payload from resource_events where resource_id = %s",
            (saved.id,)
        ).fetchall()
        assert len(events) == 1
        assert events[0]["event_type"] == "imported"
        assert events[0]["payload"] == {"version": 1}

        outbox = cursor.execute(
            "select topic, payload from resource_outbox where resource_id = %s order by topic",
            (saved.id,)
        ).fetchall()
        assert len(outbox) == 2
        assert outbox[0]["topic"] == "graph_ingest"
        assert outbox[0]["payload"] == {"resource_id": str(saved.id), "version": 1}
        assert outbox[1]["topic"] == "meili_index"
        assert outbox[1]["payload"] == {"resource_id": str(saved.id), "version": 1}

        counts = cursor.execute(
            "select count from resource_type_counts where tenant_id = %s and type = %s",
            ("test_tenant", "xhs_copy")
        ).fetchone()
        assert counts is not None
        assert counts["count"] == 1


def test_upsert_resource_updates_correctly(migrated_conn):
    repo = ResourceRepository()
    actor = RuntimeIdentityConfig(tenant_id="test_tenant", open_id="test_user")
    
    # First insert
    res = Resource(
        id=None,
        tenant_id="test_tenant",
        type="xhs_copy",
        title="Original Resource",
        summary="Orig Summary",
        content_text="Orig Content",
        content_json={"version": 1},
        status="active",
        visibility="private",
        owner_open_id="test_user",
        created_at=None,
        updated_at=None
    )
    saved = repo.upsert_resource(res, actor=actor, conn=migrated_conn)
    resource_id = saved.id

    # Then update with a type change
    updated_res = Resource(
        id=resource_id,
        tenant_id="test_tenant",
        type="xhs_idea",
        title="Updated Resource",
        summary="Updated Summary",
        content_text="Updated Content",
        content_json={"version": 2},
        status="active",
        visibility="team",
        owner_open_id="test_user",
        created_at=None,
        updated_at=None
    )
    updated = repo.upsert_resource(updated_res, actor=actor, conn=migrated_conn)
    assert updated.id == resource_id
    assert updated.title == "Updated Resource"
    assert updated.type == "xhs_idea"
    assert updated.version == 2

    # Verify version 2, events, outbox and type counts
    with migrated_conn.cursor(row_factory=dict_row) as cursor:
        versions = cursor.execute(
            "select version, content_text from resource_versions where resource_id = %s order by version",
            (resource_id,)
        ).fetchall()
        assert len(versions) == 2
        assert versions[1]["version"] == 2
        assert versions[1]["content_text"] == "Updated Content"

        events = cursor.execute(
            "select event_type from resource_events where resource_id = %s order by created_at",
            (resource_id,)
        ).fetchall()
        assert len(events) == 2
        assert events[1]["event_type"] == "updated"

        outbox = cursor.execute(
            "select topic, payload from resource_outbox where resource_id = %s and resource_version = 2 order by topic",
            (resource_id,)
        ).fetchall()
        assert len(outbox) == 2
        assert outbox[0]["topic"] == "graph_ingest"
        assert outbox[0]["payload"]["version"] == 2
        assert outbox[1]["topic"] == "meili_index"
        assert outbox[1]["payload"]["version"] == 2

        copy_count = cursor.execute(
            "select count from resource_type_counts where tenant_id = %s and type = %s",
            ("test_tenant", "xhs_copy")
        ).fetchone()
        idea_count = cursor.execute(
            "select count from resource_type_counts where tenant_id = %s and type = %s",
            ("test_tenant", "xhs_idea")
        ).fetchone()
        assert copy_count is None
        assert idea_count is not None and idea_count["count"] == 1



def test_upsert_resource_tenant_isolation(migrated_conn):
    repo = ResourceRepository()
    actor1 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    actor2 = RuntimeIdentityConfig(tenant_id="tenant_2", open_id="user_2")

    # Tenant 1 inserts a resource
    res = Resource(
        id=None,
        tenant_id="tenant_1",
        type="xhs_copy",
        title="Tenant 1 Resource",
        summary=None,
        content_text=None,
        content_json={},
        status="active",
        visibility="private",
        owner_open_id="user_1",
        created_at=None,
        updated_at=None
    )
    saved = repo.upsert_resource(res, actor=actor1, conn=migrated_conn)

    # Tenant 2 attempts to update Tenant 1's resource
    evil_res = Resource(
        id=saved.id,
        tenant_id="tenant_2",
        type="xhs_copy",
        title="Hijacked",
        summary=None,
        content_text=None,
        content_json={},
        status="active",
        visibility="private",
        owner_open_id="user_2",
        created_at=None,
        updated_at=None
    )

    with pytest.raises(PermissionError, match="Tenant access bypass"):
        repo.upsert_resource(evil_res, actor=actor2, conn=migrated_conn)

