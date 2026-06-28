from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from data_foundation.permissions import actor_from_config
from data_foundation.repositories.resource import ResourceRepository
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


@dataclass(frozen=True)
class _LangGraphUser:
    identity: str


def test_actor_from_config_reads_langgraph_auth_user():
    # LangGraph server 在 tool 上下文把认证用户注入 configurable["langgraph_auth_user"]。
    cfg = {"configurable": {"langgraph_auth_user": _LangGraphUser("ou_real")}}
    assert actor_from_config(cfg) == "ou_real"
    # dict 形态的用户对象也兼容
    cfg_dict = {"configurable": {"langgraph_auth_user": {"identity": "ou_dict"}}}
    assert actor_from_config(cfg_dict) == "ou_dict"


def test_actor_from_config_ignores_client_supplied_user_id():
    # 安全:绝不信任 configurable 里客户端可伪造的 user_id/open_id,只认服务端注入的 auth_user。
    cfg = {"configurable": {"user_id": "ou_forged", "open_id": "ou_forged2"}}
    with pytest.raises(PermissionError, match="Missing LangGraph user identity"):
        actor_from_config(cfg)


def test_actor_from_config_falls_back_to_runtime_contextvar():
    # 并发工具调用(asyncio.gather + run_in_executor 线程池)下,显式 config 参数可能丢失
    # configurable/身份。此时应通过 LangGraph get_config() 从运行时 contextvar 兜底取身份。
    from langchain_core.runnables.config import var_child_runnable_config

    runtime_cfg = {"configurable": {"langgraph_auth_user": _LangGraphUser("ou_ctxvar"), "thread_id": "t"}}
    token = var_child_runnable_config.set(runtime_cfg)
    try:
        # 参数 config 完全没有身份,但 contextvar 里有 -> 兜底成功
        assert actor_from_config(None) == "ou_ctxvar"
        assert actor_from_config({"configurable": {}}) == "ou_ctxvar"
    finally:
        var_child_runnable_config.reset(token)

    # contextvar 也清空后,应正确拒绝(兜底不会变成放行口子)
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


def test_semantic_rows_uses_schema_qualified_vector_cast_for_custom_search_paths():
    class _CapturingConnection:
        row_factory = None

        def __init__(self):
            self.sql = ""

        def execute(self, sql, params=None):
            self.sql = sql.lower()
            return self

        def fetchall(self):
            return []

        def cursor(self, row_factory=None):
            return self

        def transaction(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    conn = _CapturingConnection()
    repo = ResourceRepository(conn)  # type: ignore[arg-type]

    assert repo.semantic_rows(
        tenant_id="default",
        actor_open_id="ou_owner",
        embedding=[0.0] * 1536,
        embedding_model="model-a",
        top_k=5,
    ) == []

    assert "::public.vector" in conn.sql
    assert "::vector" not in conn.sql


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


def _outbox_rows_for(migrated_conn, *, resource_id, topic):
    return migrated_conn.execute(
        "select resource_id::text as rid, resource_version from resource_outbox "
        "where resource_id = %s and topic = %s",
        (resource_id, topic),
    ).fetchall()


def test_add_edge_enqueues_graph_ingest_for_source_endpoint(migrated_conn):
    """根因回归:add_edge 必须为边的 source 端点入队 graph_ingest —— 否则当 source 是
    既有资源(非同批 upsert)时,边永远进不了 Falkor。模拟 performance_feedback 的
    measured_by:既有文档 ← 新建 metric 度量,边 source=文档(既有)。"""
    repo = ResourceRepository(migrated_conn)
    # 既有文档(source 端),只入 meili,不带 graph_ingest —— 模拟"非新建、未被图 ingest"
    doc = repo.upsert_resource(
        tenant_id="default", actor_open_id="ou_owner", resource_type="xhs_copy",
        title="文案", content_text="正文", content_json={}, visibility="team",
        owner_open_id="ou_owner",
        outbox_requests=[OutboxRequest("meili_index", ("search",), {})],
    )
    assert _outbox_rows_for(migrated_conn, resource_id=doc.id, topic="graph_ingest") == []

    # 新建 metric 并建 measured_by 边:source=既有文档,target=新 metric
    metric = repo.upsert_resource(
        tenant_id="default", actor_open_id="ou_owner", resource_type="performance_metric",
        title="效果", content_text="score", content_json={}, visibility="team",
        owner_open_id="ou_owner",
        outbox_requests=[OutboxRequest("graph_ingest", ("graph",), {})],
    )
    repo.add_edge(
        tenant_id="default", source_resource_id=doc.id,
        target_resource_id=metric.id, edge_type="measured_by", weight=1.0,
    )

    # 文档(边 source)现在有了 graph_ingest → 下次 ingest 文档时这条出边会进 Falkor
    rows = _outbox_rows_for(migrated_conn, resource_id=doc.id, topic="graph_ingest")
    assert len(rows) == 1
    assert rows[0]["resource_version"] == doc.version


def test_add_edge_graph_ingest_dedupes_with_existing(migrated_conn):
    """source 自身已有 graph_ingest(同 version)时,add_edge 补的入队走 dedupe 去重,
    不产生重复 graph_ingest 行。"""
    repo = ResourceRepository(migrated_conn)
    src = repo.upsert_resource(
        tenant_id="default", actor_open_id="ou_owner", resource_type="topic",
        title="源", content_text="x", content_json={}, visibility="team",
        owner_open_id="ou_owner",
        outbox_requests=[OutboxRequest("graph_ingest", ("graph",), {})],
    )
    tgt = repo.upsert_resource(
        tenant_id="default", actor_open_id="ou_owner", resource_type="topic",
        title="靶", content_text="y", content_json={}, visibility="team",
        owner_open_id="ou_owner",
        outbox_requests=[OutboxRequest("graph_ingest", ("graph",), {})],
    )
    # src 已有 1 条 graph_ingest(version=1);加边后 add_edge 用同 dedupe_parts+同 version
    repo.add_edge(
        tenant_id="default", source_resource_id=src.id,
        target_resource_id=tgt.id, edge_type="derived_from", weight=1.0,
    )
    rows = _outbox_rows_for(migrated_conn, resource_id=src.id, topic="graph_ingest")
    assert len(rows) == 1  # 去重,不是 2


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


def test_admin_open_id_has_no_implicit_cross_user_read(migrated_conn):
    # 数据底座不再有 admin 旁路:运维 admin(XHS_ADMIN_OPEN_IDS)不自动获得他人
    # private 资源的读权限。跨用户读必须经 owner/team/resource_permissions 显式授予。
    repo = ResourceRepository(migrated_conn)
    created = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="draft",
        title="他人私有草稿",
        content_text="无显式授权管理员也读不到",
        content_json={},
        visibility="private",
        owner_open_id="ou_owner",
    )

    # 即使把某 open_id 写进 app.admin_open_ids,也不再产生任何效果(旁路已删)
    migrated_conn.execute("set app.admin_open_ids = 'ou_admin'")

    assert repo.get_resource("default", "ou_admin", created.id) is None

    # 显式 read 授权后才可读
    repo.grant_permission(
        tenant_id="default",
        resource_id=created.id,
        subject_type="user",
        subject_id="ou_admin",
        permission="read",
    )
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


def test_resource_type_counts_follow_new_and_retyped_resources(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    created = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="draft",
        title="草稿",
        content_text="正文",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "test", "external_type": "doc", "external_id": "resource-type-count"},
    )
    repo.upsert_resource(
        tenant_id="other-tenant",
        actor_open_id="ou_owner",
        resource_type="draft",
        title="其他租户草稿",
        content_text="正文",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )
    updated = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="generated_copy",
        title="文案",
        content_text="新版正文",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "test", "external_type": "doc", "external_id": "resource-type-count"},
    )

    assert updated.id == created.id
    rows = migrated_conn.execute(
        """
        select tenant_id, type, count
        from resource_type_counts
        order by tenant_id, type
        """
    ).fetchall()
    assert rows == [
        {"tenant_id": "default", "type": "generated_copy", "count": 1},
        {"tenant_id": "other-tenant", "type": "draft", "count": 1},
    ]
    status = repo.data_foundation_status("default")
    facts = repo.runtime_fact_aggregates("default")
    assert status["resources"]["by_type"] == {"generated_copy": 1}
    assert facts["resources"]["by_type"]["generated_copy"] == 1
    assert facts["resources"]["by_type"]["draft"] == 0


def test_runtime_status_reads_resource_type_count_facts_not_resource_table():
    source = Path("data_foundation/repositories/resource.py").read_text(encoding="utf-8").lower()

    assert "from resource_type_counts" in source
    assert "select type, count(*) as count\n            from resources\n            where tenant_id = %s\n            group by type" not in source


def test_runtime_facts_split_source_counts_for_index_usage():
    source = Path("data_foundation/repositories/resource.py").read_text(encoding="utf-8").lower()

    assert "count(*) filter" not in source
    assert "source_enabled" in source
    assert "source_expired" in source
    assert "source_running" in source
    assert "lease_expires_at is not null" in source
    assert "lease_expires_at > now()" in source


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
    repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="external_note",
        title="External",
        content_text="external-secret",
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
        insert into sync_sources (
          tenant_id, source_type, name, credentials, schedule_seconds, next_run_at, lease_expires_at
        )
        values ('other-tenant', 'feishu_wiki', 'other-running', '{"token":"other-credentials-secret"}', 60, now() - interval '1 minute', now() + interval '1 minute')
        """
    )
    migrated_conn.execute(
        """
        insert into sync_runs (tenant_id, sync_source_id, source_type, status, started_at)
        values ('default', %s, 'feishu_base', 'succeeded', now())
        """,
        (expired_source,),
    )
    migrated_conn.execute(
        """
        insert into sync_runs (tenant_id, source_type, status, started_at)
        values ('other-tenant', 'feishu_base', 'failed', now() + interval '1 second')
        """
    )

    for status in ("pending", "retry", "processing", "blocked", "dead", "succeeded", "superseded"):
        migrated_conn.execute(
            """
            insert into resource_outbox (tenant_id, topic, dedupe_key, payload, status)
            values ('default', 'embedding_generate', %s, '{"token":"outbox-payload-secret"}', %s)
            """,
            (f"runtime-facts-{status}", status),
        )
        migrated_conn.execute(
            """
            insert into resource_outbox (tenant_id, topic, dedupe_key, payload, status)
            values ('other-tenant', 'embedding_generate', %s, '{"token":"other-outbox-payload-secret"}', %s)
            """,
            (f"other-runtime-facts-{status}", status),
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
        insert into embedding_indexes (
          tenant_id, embedding_model, config_version, dimensions, status,
          expected_resources, completed_resources, failed_resources
        )
        values ('other-tenant', 'model-other', 'cfg-other', 1536, 'building', 99, 98, 1)
        """
    )
    migrated_conn.execute(
        """
        insert into resource_embeddings (
          tenant_id, resource_id, resource_version, embedding_index_id,
          chunk_index, chunk_text, chunker_version, embedding_model, embedding
        )
        values ('default', %s, 1, %s, 0, 'indexed-body-secret', 'v1', 'model-a', %s::public.vector)
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
    assert facts["resources"]["total"] == 3
    assert facts["resources"]["by_type"] == {
        "feishu_base_record": 1,
        "feishu_doc": 1,
        "generated_topic": 0,
        "generated_copy": 0,
        "revision_request": 0,
        "performance_metric": 0,
        "draft": 0,
        "topic": 0,
        "doc": 0,
        "other": 1,
    }
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
    assert "cfg-other" not in rendered
    assert "other-outbox-payload-secret" not in rendered


def test_readable_rows_by_ids_filters_and_preserves_order(migrated_conn):
    from data_foundation.repositories.resource import ResourceRepository
    repo = ResourceRepository(migrated_conn)
    a = repo.upsert_resource(tenant_id="default", actor_open_id="ou_x", resource_type="feishu_base_record",
        title="A", content_text="a", content_json={}, visibility="team", owner_open_id="ou_x")
    b = repo.upsert_resource(tenant_id="default", actor_open_id="ou_x", resource_type="feishu_base_record",
        title="B", content_text="b", content_json={}, visibility="team", owner_open_id="ou_x")
    rows = repo.readable_rows_by_ids(tenant_id="default", actor_open_id="ou_x", resource_ids=[b.id, a.id])
    assert [str(r["id"]) for r in rows] == [b.id, a.id]
    c = repo.upsert_resource(tenant_id="default", actor_open_id="ou_other", resource_type="feishu_base_record",
        title="C", content_text="c", content_json={}, visibility="private", owner_open_id="ou_other")
    rows2 = repo.readable_rows_by_ids(tenant_id="default", actor_open_id="ou_x", resource_ids=[c.id, a.id])
    assert [str(r["id"]) for r in rows2] == [a.id]


def test_bulk_performance_metrics_sql_syntax():
    class _CapturingConnection:
        row_factory = None

        def __init__(self):
            self.sql = ""
            self.params = None

        def execute(self, sql, params=None):
            self.sql = sql.lower()
            self.params = params
            return self

        def fetchall(self):
            return []

        def cursor(self, row_factory=None):
            return self

        def transaction(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    conn = _CapturingConnection()
    repo = ResourceRepository(conn)  # type: ignore[arg-type]
    repo.bulk_performance_metrics("default", ["id-1", "id-2"])

    assert "select target.id::text" in conn.sql
    assert "join resource_edges e" in conn.sql
    assert "join resources metric" in conn.sql
    assert conn.params == {"resource_ids": ["id-1", "id-2"], "tenant_id": "default"}


def test_bulk_performance_metrics_fetches_multiple(migrated_conn):

    repo = ResourceRepository(migrated_conn)
    tenant_id = "default"
    actor_open_id = "ou_owner"
    target1 = repo.upsert_resource(
        tenant_id=tenant_id, actor_open_id=actor_open_id, resource_type="generated_copy",
        title="笔记 1", content_text="正文 1", content_json={}, visibility="private", owner_open_id=actor_open_id
    )
    target2 = repo.upsert_resource(
        tenant_id=tenant_id, actor_open_id=actor_open_id, resource_type="generated_copy",
        title="笔记 2", content_text="正文 2", content_json={}, visibility="private", owner_open_id=actor_open_id
    )
    metric = repo.upsert_resource(
        tenant_id=tenant_id, actor_open_id=actor_open_id, resource_type="performance_metric",
        title="小红书效果 2026-06-23", content_text="",
        content_json={"target_resource_id": str(target1.id), "metrics": {"likes": 50}, "score": 50.0},
        visibility="private", owner_open_id=actor_open_id
    )
    repo.add_edge(tenant_id=tenant_id, source_resource_id=target1.id, target_resource_id=metric.id, edge_type="measured_by", weight=50.0)

    res = repo.bulk_performance_metrics(tenant_id, [str(target1.id), str(target2.id)])
    assert str(target1.id) in res
    assert len(res[str(target1.id)]) == 1
    assert res[str(target1.id)][0]["metrics"]["likes"] == 50
    assert str(target2.id) in res
    assert len(res[str(target2.id)]) == 0


