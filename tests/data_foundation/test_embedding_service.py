from __future__ import annotations

from data_foundation.embedding_repository import VectorChunk
from data_foundation.embedding_service import EmbeddingIndexProfile, EmbeddingIndexService
from data_foundation.repository import ResourceRepository


def _resource(conn, *, tenant_id: str = "tenant-a", title: str, content: str | None = "正文"):
    return ResourceRepository(conn).upsert_resource(
        tenant_id=tenant_id,
        actor_open_id="ou_owner",
        resource_type="doc",
        title=title,
        content_text=content,
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )


def _service(conn, *, profile_version: str = "cfg-v1") -> EmbeddingIndexService:
    return EmbeddingIndexService(
        conn,
        profile=EmbeddingIndexProfile(
            embedding_model="model",
            config_version=profile_version,
            chunker_version="text-v1",
        ),
    )


def test_new_profile_enqueues_complete_backfill_once(migrated_conn):
    _resource(migrated_conn, title="文档一")
    _resource(migrated_conn, title="文档二")
    _resource(migrated_conn, title="空文档", content=" ")
    service = _service(migrated_conn)

    first = service.reconcile_tenant("tenant-a")
    second = service.reconcile_tenant("tenant-a")

    assert first.enqueued == 2
    assert first.activated is False
    assert second.enqueued == 0
    assert second.embedding_index_id == first.embedding_index_id
    rows = migrated_conn.execute(
        """
        select topic, payload
        from resource_outbox
        where tenant_id = 'tenant-a'
        order by payload->>'resource_id'
        """
    ).fetchall()
    assert [row["topic"] for row in rows] == ["embedding_generate", "embedding_generate"]
    assert {row["payload"]["embedding_index_id"] for row in rows} == {first.embedding_index_id}
    assert {row["payload"]["chunker_version"] for row in rows} == {"text-v1"}


def test_zero_resource_index_activates_immediately(migrated_conn):
    result = _service(migrated_conn).reconcile_tenant("empty-tenant")

    assert result.enqueued == 0
    assert result.activated is True
    row = migrated_conn.execute(
        "select status from embedding_indexes where id = %s",
        (result.embedding_index_id,),
    ).fetchone()
    assert row["status"] == "active"


def test_active_index_reconcile_enqueues_later_resources(migrated_conn):
    service = _service(migrated_conn)
    initial = service.reconcile_tenant("tenant-a")
    assert initial.activated is True

    resource = _resource(migrated_conn, title="后来的文档")
    later = service.reconcile_tenant("tenant-a")

    assert later.embedding_index_id == initial.embedding_index_id
    assert later.activated is True
    assert later.enqueued == 1
    row = migrated_conn.execute(
        """
        select payload
        from resource_outbox
        where tenant_id = 'tenant-a' and topic = 'embedding_generate'
        """
    ).fetchone()
    assert row["payload"]["resource_id"] == resource.id
    expected = migrated_conn.execute(
        "select expected_resources from embedding_indexes where id = %s",
        (initial.embedding_index_id,),
    ).fetchone()
    assert expected["expected_resources"] == 1


def test_new_config_does_not_retire_old_active_until_backfill_complete(migrated_conn):
    resource = _resource(migrated_conn, title="文档")
    first = _service(migrated_conn, profile_version="cfg-v1").reconcile_tenant("tenant-a")
    repo = service_repo = _service(migrated_conn, profile_version="cfg-v1").embedding_repo
    repo.store_batch(
        tenant_id="tenant-a",
        embedding_index_id=first.embedding_index_id,
        resource_id=resource.id,
        resource_version=resource.version,
        chunks=[VectorChunk(0, "正文", [0.1] + [0.0] * 1535)],
    )
    repo.activate_if_complete(first.embedding_index_id, tenant_id="tenant-a")

    second = _service(migrated_conn, profile_version="cfg-v2").reconcile_tenant("tenant-a")

    assert second.activated is False
    active = service_repo.active_index("tenant-a")
    assert active.id == first.embedding_index_id
