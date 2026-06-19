from __future__ import annotations

from dataclasses import dataclass

import pytest

from data_foundation.permissions import actor_from_config
from data_foundation.repository import ResourceRepository


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
        outbox_topics=["meili_index", "embedding_generate", "graph_ingest"],
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
        outbox_topics=["meili_index"],
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
        outbox_topics=["meili_index"],
    )

    assert second.id == first.id
    assert second.version == 2
    assert repo.debug_counts()["resource_versions"] == 2
    events = migrated_conn.execute("select event_type from resource_events order by created_at, id").fetchall()
    assert [event["event_type"] for event in events] == ["imported", "updated"]


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
