import pytest
from psycopg.rows import dict_row

from data_foundation.repositories.resource import ResourceRepository


def test_upsert_resource_inserts_correctly(migrated_conn):
    repo = ResourceRepository()
    saved = repo.upsert_resource(
        tenant_id="test_tenant",
        actor_open_id="test_user",
        resource_type="xhs_copy",
        title="Test Resource",
        summary="Test Summary",
        content_text="Test Content",
        content_json={"foo": "bar"},
        visibility="private",
        owner_open_id="test_user",
        conn=migrated_conn,
    )
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

        # 默认契约:普通资源先进入 knowledge_enrich，再由其投递现有索引处理器。
        outbox = cursor.execute(
            "select topic, payload from resource_outbox where resource_id = %s order by topic",
            (saved.id,)
        ).fetchall()
        assert len(outbox) == 1
        assert outbox[0]["topic"] == "knowledge_enrich"
        assert outbox[0]["payload"] == {"resource_id": str(saved.id), "version": 1}

        counts = cursor.execute(
            "select count from resource_type_counts where tenant_id = %s and type = %s",
            ("test_tenant", "xhs_copy")
        ).fetchone()
        assert counts is not None
        assert counts["count"] == 1


def test_upsert_resource_updates_correctly(migrated_conn):
    repo = ResourceRepository()

    # First insert
    saved = repo.upsert_resource(
        tenant_id="test_tenant",
        actor_open_id="test_user",
        resource_type="xhs_copy",
        title="Original Resource",
        summary="Orig Summary",
        content_text="Orig Content",
        content_json={"version": 1},
        visibility="private",
        owner_open_id="test_user",
        conn=migrated_conn,
    )
    resource_id = saved.id

    # Then update with a type change
    updated = repo.upsert_resource(
        tenant_id="test_tenant",
        actor_open_id="test_user",
        resource_id=resource_id,
        resource_type="xhs_idea",
        title="Updated Resource",
        summary="Updated Summary",
        content_text="Updated Content",
        content_json={"version": 2},
        visibility="team",
        owner_open_id="test_user",
        conn=migrated_conn,
    )
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
            "select event_type, (payload->>'version')::int as resource_version "
            "from resource_events where resource_id = %s order by resource_version",
            (resource_id,),
        ).fetchall()
        assert [(event["event_type"], event["resource_version"]) for event in events] == [
            ("imported", 1),
            ("updated", 2),
        ]

        outbox = cursor.execute(
            "select topic, payload from resource_outbox where resource_id = %s and resource_version = 2 order by topic",
            (resource_id,)
        ).fetchall()
        assert len(outbox) == 1
        assert outbox[0]["topic"] == "knowledge_enrich"
        assert outbox[0]["payload"]["version"] == 2

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


def test_status_only_update_creates_exact_version_and_outbox(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first = repo.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="ou-owner",
        resource_type="xhs_copy",
        title="待退役素材",
        content_text="正文不变",
        content_json={"title": "待退役素材"},
        status="active",
        owner_open_id="ou-owner",
        outbox_requests=[],
    )

    retired = repo.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="ou-owner",
        resource_id=str(first.id),
        resource_type="xhs_copy",
        title="待退役素材",
        content_text="正文不变",
        content_json={"title": "待退役素材"},
        status="inactive",
        owner_open_id="ou-owner",
    )

    assert retired.version == 2
    row = migrated_conn.execute(
        "select status from resources where tenant_id = %s and id = %s",
        ("tenant-a", first.id),
    ).fetchone()
    assert row["status"] == "inactive"
    outbox = migrated_conn.execute(
        """
        select topic, resource_version from resource_outbox
        where tenant_id = %s and resource_id = %s and resource_version = 2
        """,
        ("tenant-a", first.id),
    ).fetchall()
    assert [(item["topic"], item["resource_version"]) for item in outbox] == [
        ("knowledge_enrich", 2)
    ]


def test_upsert_resource_tenant_isolation(migrated_conn):
    repo = ResourceRepository()

    # Tenant 1 inserts a resource
    saved = repo.upsert_resource(
        tenant_id="tenant_1",
        actor_open_id="user_1",
        resource_type="xhs_copy",
        title="Tenant 1 Resource",
        content_json={},
        visibility="private",
        owner_open_id="user_1",
        conn=migrated_conn,
    )

    # Tenant 2 attempts to update Tenant 1's resource by reusing its id
    with pytest.raises(PermissionError, match="Tenant access bypass"):
        repo.upsert_resource(
            tenant_id="tenant_2",
            actor_open_id="user_2",
            resource_id=saved.id,
            resource_type="xhs_copy",
            title="Hijacked",
            content_json={},
            visibility="private",
            owner_open_id="user_2",
            conn=migrated_conn,
        )


def test_get_resource_version_uses_snapshot_and_acl(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="generated_copy",
        title="A 标题",
        content_text="A 正文",
        content_json={"title": "A 标题", "body": "A 正文"},
        visibility="private",
        owner_open_id="ou_owner",
    )
    repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_id=first.id,
        resource_type="generated_copy",
        title="C 最新标题",
        content_text="C 最新正文",
        content_json={"title": "C 最新标题", "body": "C 最新正文"},
        visibility="private",
        owner_open_id="ou_owner",
    )

    snapshot = repo.get_resource_version("default", "ou_owner", first.id, 1)
    assert snapshot is not None
    assert snapshot.title == "A 标题"
    assert snapshot.content_text == "A 正文"
    assert snapshot.version == 1
    assert repo.get_resource_version("default", "ou_other", first.id, 1) is None
