from __future__ import annotations

from dataclasses import dataclass

import pytest

from data_foundation.permissions import actor_from_config
from data_foundation.repository import ResourceRepository
from data_foundation.models import OutboxRequest


@dataclass(frozen=True)
class _User:
    identity: str | None = "ou_owner"


@dataclass(frozen=True)
class _ServerInfo:
    user: _User


@dataclass(frozen=True)
class _Config:
    server_info: _ServerInfo


def test_actor_from_config_requires_langgraph_identity():
    assert actor_from_config(_Config(_ServerInfo(_User("ou_owner")))) == "ou_owner"

    with pytest.raises(PermissionError, match="Missing LangGraph user identity"):
        actor_from_config(None)


def test_resource_repository_no_longer_exposes_legacy_outbox_runtime():
    assert not hasattr(ResourceRepository, "lease_outbox")
    assert not hasattr(ResourceRepository, "complete_outbox")


def test_resource_repository_no_longer_writes_embeddings_without_an_index():
    assert not hasattr(ResourceRepository, "replace_embedding_chunks")
    assert not hasattr(ResourceRepository, "set_embedding")


def test_resource_repository_no_longer_owns_sync_run_lifecycle():
    assert not hasattr(ResourceRepository, "start_sync_run")
    assert not hasattr(ResourceRepository, "finish_sync_run")


def test_resource_repository_exposes_runtime_fact_aggregates():
    assert callable(getattr(ResourceRepository, "runtime_fact_aggregates"))


def test_upsert_resource_writes_version_event_mapping_and_outbox(migrated_conn):
    repo = ResourceRepository(migrated_conn)

    resource = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_base_record",
        title="露营装备清单",
        content_text="帐篷 天幕 炉具",
        content_json={"fields": {"点赞": 120}},
        visibility="private",
        owner_open_id="ou_owner",
        mapping={
            "system": "feishu",
            "external_type": "base_record",
            "external_id": "base:table:rec1",
        },
        outbox_requests=[
            OutboxRequest("meili_index", ("search",), {}),
            OutboxRequest("embedding_generate", ("embedding", "idx"), {"embedding_index_id": "idx"}),
            OutboxRequest("graph_ingest", ("graph",), {}),
        ],
    )

    assert resource.id
    assert resource.version == 1
    assert repo.get_resource("default", "ou_owner", resource.id).title == "露营装备清单"

    counts = repo.debug_counts()
    assert counts["resource_versions"] == 1
    assert counts["resource_events"] == 1
    assert counts["resource_mappings"] == 1
    assert counts["resource_outbox"] == 3


def test_upsert_same_mapping_creates_second_version(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="旧标题",
        content_text="旧内容",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "feishu", "external_type": "docx", "external_id": "doc1"},
        outbox_requests=[OutboxRequest("meili_index", ("search",), {})],
    )
    second = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="新标题",
        content_text="新内容",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "feishu", "external_type": "docx", "external_id": "doc1"},
        outbox_requests=[OutboxRequest("meili_index", ("search",), {})],
    )

    assert second.id == first.id
    assert second.version == 2
    assert repo.debug_counts()["resource_versions"] == 2
    events = migrated_conn.execute("select event_type from resource_events order by created_at, id").fetchall()
    assert [event["event_type"] for event in events] == ["imported", "updated"]


def test_upsert_identical_mapping_is_idempotent(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    kwargs = {
        "tenant_id": "default",
        "actor_open_id": "ou_owner",
        "resource_type": "feishu_doc",
        "title": "相同标题",
        "content_text": "相同内容",
        "content_json": {"source": "wiki"},
        "visibility": "team",
        "owner_open_id": "ou_owner",
        "mapping": {"system": "feishu", "external_type": "docx", "external_id": "doc-replay"},
        "outbox_requests": [
            OutboxRequest("meili_index", ("search",), {}),
            OutboxRequest("embedding_generate", ("embedding", "idx"), {"embedding_index_id": "idx"}),
        ],
    }

    first = repo.upsert_resource(**kwargs)
    second = repo.upsert_resource(**kwargs)

    assert second.id == first.id
    assert second.version == 1
    assert repo.debug_counts()["resource_versions"] == 1
    assert repo.debug_counts()["resource_events"] == 1
    assert repo.debug_counts()["resource_outbox"] == 2


def test_first_sync_failure_is_persisted_as_unbound_event(migrated_conn):
    repo = ResourceRepository(migrated_conn)

    repo.mark_mapping_failed(
        tenant_id="default",
        actor_open_id="ou_sync",
        system="feishu",
        external_type="docx",
        external_id="doc-first-failure",
        error="document parse failed",
    )

    event = migrated_conn.execute(
        """
        select resource_id, event_type, actor_open_id, payload
        from resource_events
        where tenant_id = 'default'
        """
    ).fetchone()
    assert event["resource_id"] is None
    assert event["event_type"] == "sync_failed"
    assert event["actor_open_id"] == "ou_sync"
    assert event["payload"] == {
        "system": "feishu",
        "external_type": "docx",
        "external_id": "doc-first-failure",
        "error": "document parse failed",
    }


def test_permission_filter_blocks_other_private_resource(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    created = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="draft",
        title="私有草稿",
        content_text="只有 owner 可读",
        content_json={},
        visibility="private",
        owner_open_id="ou_owner",
    )

    assert repo.get_resource("default", "ou_owner", created.id) is not None
    assert repo.get_resource("default", "ou_other", created.id) is None

    repo.grant_permission(
        tenant_id="default",
        resource_id=created.id,
        subject_type="user",
        subject_id="ou_other",
        permission="read",
    )
    assert repo.get_resource("default", "ou_other", created.id) is not None


def test_admin_can_read_same_tenant_without_per_resource_grant(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    created = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="draft",
        title="管理员可读草稿",
        content_text="管理员无需逐资源授权",
        content_json={},
        visibility="private",
        owner_open_id="ou_owner",
    )

    migrated_conn.execute("set app.admin_open_ids = 'ou_other, ou_admin'")

    assert repo.get_resource("default", "ou_admin", created.id) is not None


def test_same_external_mapping_can_exist_in_different_tenants(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    mapping = {"system": "feishu", "external_type": "docx", "external_id": "doc1"}

    first = repo.upsert_resource(
        tenant_id="tenant_a",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="租户 A 文档",
        content_text="A",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping=mapping,
    )
    second = repo.upsert_resource(
        tenant_id="tenant_b",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="租户 B 文档",
        content_text="B",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping=mapping,
    )

    assert second.id != first.id


def test_runtime_fact_aggregates_are_bounded_and_redacted(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="First",
        content_text="resource-body-secret",
        content_json={"private": "resource-json-secret"},
        visibility="team",
        owner_open_id="ou_owner",
    )
    repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_base_record",
        title="Second",
        content_text="another-resource-body-secret",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )
    repo.upsert_resource(
        tenant_id="other-tenant",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="Other tenant",
        content_text="other-tenant-secret",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )

    expired_source = migrated_conn.execute(
        """
        insert into sync_sources (
          tenant_id, source_type, name, credentials, schedule_seconds, next_run_at
        )
        values ('default', 'feishu_base', 'expired', '{"token":"credentials-secret"}', 60, now() - interval '1 minute')
        returning id
        """
    ).fetchone()["id"]
    migrated_conn.execute(
        """
        insert into sync_sources (
          tenant_id, source_type, name, credentials, schedule_seconds, next_run_at, lease_expires_at
        )
        values ('default', 'feishu_wiki', 'running', '{"token":"credentials-secret"}', 60, now() + interval '1 minute', now() + interval '1 minute')
        """
    )
    migrated_conn.execute(
        """
        insert into sync_runs (tenant_id, sync_source_id, source_type, status, started_at)
        values ('default', %s, 'feishu_base', 'succeeded', now())
        """,
        (expired_source,),
    )

    for status in ("pending", "retry", "processing", "blocked", "dead", "succeeded", "superseded"):
        migrated_conn.execute(
            """
            insert into resource_outbox (tenant_id, topic, dedupe_key, payload, status)
            values ('default', 'embedding_generate', %s, '{"token":"outbox-payload-secret"}', %s)
            """,
            (f"runtime-facts-{status}", status),
        )

    active_index = migrated_conn.execute(
        """
        insert into embedding_indexes (
          tenant_id, embedding_model, config_version, dimensions, status,
          expected_resources, completed_resources, failed_resources, activated_at
        )
        values ('default', 'model-a', 'cfg-1', 1536, 'active', 2, 1, 0, now())
        returning id
        """
    ).fetchone()["id"]
    migrated_conn.execute(
        """
        insert into embedding_indexes (
          tenant_id, embedding_model, config_version, dimensions, status,
          expected_resources, completed_resources, failed_resources
        )
        values ('default', 'model-b', 'cfg-2', 1536, 'building', 2, 0, 1)
        """
    )
    migrated_conn.execute(
        """
        insert into resource_embeddings (
          tenant_id, resource_id, resource_version, embedding_index_id,
          chunk_index, chunk_text, chunker_version, embedding_model, embedding
        )
        values ('default', %s, 1, %s, 0, 'indexed-body-secret', 'v1', 'model-a', %s::vector)
        """,
        (first.id, active_index, "[" + ",".join(["0"] * 1536) + "]"),
    )
    migrated_conn.execute(
        """
        insert into service_error_aggregates (
          window_started_at, window_ended_at, tenant_id, component, operation, error_code, error_count
        )
        values (now() - interval '1 minute', now(), 'default', 'sync', 'import', 'SYNC_FAILED', 3)
        """
    )
    migrated_conn.execute(
        """
        insert into service_error_aggregates (
          window_started_at, window_ended_at, tenant_id, component, operation, error_code, error_count
        )
        values (now() - interval '1 minute', now(), 'other-tenant', 'sync', 'import', 'OTHER_TENANT', 9)
        """
    )
    migrated_conn.commit()

    facts = repo.runtime_fact_aggregates("default")

    assert facts["sources"] == {"enabled": 2, "expired": 1, "running": 1, "last_status": "succeeded"}
    assert facts["outbox"] == {
        "pending": 1,
        "retry": 1,
        "processing": 1,
        "blocked": 1,
        "dead": 1,
        "succeeded": 1,
        "superseded": 1,
    }
    assert facts["embedding"]["active"]["config_version"] == "cfg-1"
    assert facts["embedding"]["building"]["config_version"] == "cfg-2"
    assert facts["resources"]["total"] == 2
    assert facts["resources"]["by_type"] == {"feishu_base_record": 1, "feishu_doc": 1}
    assert facts["resources"]["last_indexed_at"] is not None
    assert facts["errors"][0]["error_code"] == "SYNC_FAILED"
    assert facts["errors"][0]["count"] == 3
    assert set(facts["errors"][0]) == {
        "component",
        "operation",
        "error_code",
        "count",
        "window_started_at",
        "window_ended_at",
    }
    rendered = str(facts)
    assert "credentials-secret" not in rendered
    assert "outbox-payload-secret" not in rendered
    assert "resource-body-secret" not in rendered
    assert "resource-json-secret" not in rendered
    assert "indexed-body-secret" not in rendered
    assert "OTHER_TENANT" not in rendered
