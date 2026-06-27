import pytest
from psycopg.rows import dict_row

from data_foundation.repositories.resource import ResourceRepository
from data_foundation.repositories.feedback import FeedbackRepository
from data_foundation.models import Resource, RuntimeIdentityConfig


def test_add_edge_validation(migrated_conn):
    repo = FeedbackRepository()
    with pytest.raises(ValueError, match="Edge type is required"):
        repo.add_edge(
            tenant_id="tenant_1",
            source_resource_id="00000000-0000-0000-0000-000000000001",
            target_resource_id="00000000-0000-0000-0000-000000000002",
            edge_type="",
            weight=1.0,
            conn=migrated_conn
        )
    with pytest.raises(ValueError, match="Edge weight must be finite"):
        repo.add_edge(
            tenant_id="tenant_1",
            source_resource_id="00000000-0000-0000-0000-000000000001",
            target_resource_id="00000000-0000-0000-0000-000000000002",
            edge_type="test_edge",
            weight=float('inf'),
            conn=migrated_conn
        )


def test_add_edge_cross_tenant_denied(migrated_conn):
    res_repo = ResourceRepository()
    fb_repo = FeedbackRepository()
    
    actor1 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    actor2 = RuntimeIdentityConfig(tenant_id="tenant_2", open_id="user_2")
    
    r1 = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_1",
            type="xhs_copy",
            title="T1 Resource",
            summary=None,
            content_text="Content 1",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_1",
            created_at=None,
            updated_at=None
        ),
        actor=actor1,
        conn=migrated_conn
    )
    
    r2 = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_2",
            type="xhs_copy",
            title="T2 Resource",
            summary=None,
            content_text="Content 2",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_2",
            created_at=None,
            updated_at=None
        ),
        actor=actor2,
        conn=migrated_conn
    )
    
    with pytest.raises(PermissionError, match="Both edge endpoints must belong to this tenant"):
        fb_repo.add_edge(
            tenant_id="tenant_1",
            source_resource_id=r1.id,
            target_resource_id=r2.id,
            edge_type="cross_edge",
            weight=1.0,
            conn=migrated_conn
        )


def test_add_edge_inserts_correctly(migrated_conn):
    res_repo = ResourceRepository()
    fb_repo = FeedbackRepository()
    actor = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    
    r1 = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_1",
            type="xhs_copy",
            title="Resource 1",
            summary=None,
            content_text="Content 1",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_1",
            created_at=None,
            updated_at=None
        ),
        actor=actor,
        conn=migrated_conn
    )
    
    r2 = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_1",
            type="xhs_copy",
            title="Resource 2",
            summary=None,
            content_text="Content 2",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_1",
            created_at=None,
            updated_at=None
        ),
        actor=actor,
        conn=migrated_conn
    )
    
    # Delete existing outbox messages for r1 to isolate
    with migrated_conn.cursor() as cursor:
        cursor.execute("delete from resource_outbox where resource_id = %s", (r1.id,))
        
    fb_repo.add_edge(
        tenant_id="tenant_1",
        source_resource_id=r1.id,
        target_resource_id=r2.id,
        edge_type="related_to",
        weight=2.5,
        conn=migrated_conn
    )
    
    with migrated_conn.cursor(row_factory=dict_row) as cursor:
        # Verify edge
        edge = cursor.execute(
            "select * from resource_edges where tenant_id = %s and source_resource_id = %s and target_resource_id = %s and edge_type = %s",
            ("tenant_1", r1.id, r2.id, "related_to")
        ).fetchone()
        assert edge is not None
        assert edge["weight"] == 2.5
        
        # Verify outbox
        outbox = cursor.execute(
            "select * from resource_outbox where resource_id = %s",
            (r1.id,)
        ).fetchall()
        assert len(outbox) == 1
        assert outbox[0]["topic"] == "graph_ingest"
        assert outbox[0]["event_id"] is None
        assert outbox[0]["payload"] == {"resource_id": str(r1.id), "version": 1}
        
        # Verify dedupe key —— 含边维度(target+edge_type),与 node-ingest key 区分(Q-2 修复)
        import hashlib
        import json
        expected_dedupe = hashlib.sha256(
            json.dumps(
                ["tenant_1", str(r1.id), 1, "graph_ingest", "graph", "edge", str(r2.id), "related_to"],
                sort_keys=True,
                ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()
        assert outbox[0]["dedupe_key"] == expected_dedupe


def test_create_edge_denies_unauthorized_user(migrated_conn):
    res_repo = ResourceRepository()
    fb_repo = FeedbackRepository()
    
    actor1 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    actor2 = RuntimeIdentityConfig(tenant_id="tenant_2", open_id="user_2")
    actor3 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_3")
    
    # 1. Invalid UUID formats
    with pytest.raises(PermissionError, match="Invalid UUID format"):
        fb_repo.create_edge(
            source_id="invalid-uuid",
            target_id="00000000-0000-0000-0000-000000000002",
            edge_type="test",
            actor=actor1,
            conn=migrated_conn
        )
        
    with pytest.raises(PermissionError, match="Invalid UUID format"):
        fb_repo.create_edge(
            source_id="00000000-0000-0000-0000-000000000001",
            target_id="invalid-uuid",
            edge_type="test",
            actor=actor1,
            conn=migrated_conn
        )
        
    # Create resource in tenant_1 (private)
    r1 = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_1",
            type="xhs_copy",
            title="T1 Private Resource",
            summary=None,
            content_text="Content",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_1",
            created_at=None,
            updated_at=None
        ),
        actor=actor1,
        conn=migrated_conn
    )
    
    # Create resource in tenant_2 (private)
    r2 = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_2",
            type="xhs_copy",
            title="T2 Private Resource",
            summary=None,
            content_text="Content 2",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_2",
            created_at=None,
            updated_at=None
        ),
        actor=actor2,
        conn=migrated_conn
    )
    
    # 2. Source is unauthorized (actor2 trying to use tenant_1's private resource)
    with pytest.raises(PermissionError, match="Source resource does not exist or unauthorized"):
        fb_repo.create_edge(
            source_id=r1.id,
            target_id=r2.id,
            edge_type="test",
            actor=actor2,
            conn=migrated_conn
        )

    # 3. Source is team visible in tenant_1: actor1 (user_1) owns it.
    r_team = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_1",
            type="xhs_copy",
            title="T1 Team Resource",
            summary=None,
            content_text="Content",
            content_json={},
            status="active",
            visibility="team",
            owner_open_id="user_1",
            created_at=None,
            updated_at=None
        ),
        actor=actor1,
        conn=migrated_conn
    )
    
    # Create valid target in tenant_1 (private to actor1)
    r_target = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_1",
            type="xhs_copy",
            title="Target",
            summary=None,
            content_text="Content",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_1",
            created_at=None,
            updated_at=None
        ),
        actor=actor1,
        conn=migrated_conn
    )
    
    # actor3 trying to create edge from r_team (owned by user_1) to r_target (private to user_1)
    # This should fail because actor3 does not have write permission on r_team (not owner/no write perm)
    with pytest.raises(PermissionError, match="Source resource does not exist or unauthorized"):
        fb_repo.create_edge(
            source_id=r_team.id,
            target_id=r_target.id,
            edge_type="test_team_edge",
            actor=actor3,
            conn=migrated_conn
        )
        
    # Create a resource owned by actor3
    r_owned_by_user3 = res_repo.upsert_resource(
        Resource(
            id=None,
            tenant_id="tenant_1",
            type="xhs_copy",
            title="Owned by User 3",
            summary=None,
            content_text="Content",
            content_json={},
            status="active",
            visibility="private",
            owner_open_id="user_3",
            created_at=None,
            updated_at=None
        ),
        actor=actor3,
        conn=migrated_conn
    )
    
    # actor3 trying to create edge from r_owned_by_user3 (write) to r_target (private to user_1, no read perm)
    # This should fail because actor3 does not have read permission on r_target
    with pytest.raises(PermissionError, match="Target resource does not exist or unauthorized"):
        fb_repo.create_edge(
            source_id=r_owned_by_user3.id,
            target_id=r_target.id,
            edge_type="test_edge",
            actor=actor3,
            conn=migrated_conn
        )
        
    # actor3 trying to create edge from r_owned_by_user3 (write) to r_team (team visible, read perm)
    # This should succeed because actor3 has write permission on source, and read permission on target
    fb_repo.create_edge(
        source_id=r_owned_by_user3.id,
        target_id=r_team.id,
        edge_type="test_team_read_edge",
        actor=actor3,
        conn=migrated_conn
    )
    
    # 4. Target resource not in tenant_1 (r2 is in tenant_2)
    # This should fail because actor3 does not have read permission on r2
    with pytest.raises(PermissionError, match="Target resource does not exist or unauthorized"):
        fb_repo.create_edge(
            source_id=r_owned_by_user3.id,
            target_id=r2.id,
            edge_type="test_invalid_target",
            actor=actor3,
            conn=migrated_conn
        )



def test_add_edge_after_node_ingest_enqueues_distinct_task(migrated_conn):
    """Q-2 回归:节点已 graph_ingest 标 succeeded 后再加边,必须产生**新的** pending 任务,
    而非因 dedupe_key 与 node-ingest 相同被 on conflict 吞掉(否则边永不入 FalkorDB)。"""
    res_repo = ResourceRepository()
    fb_repo = FeedbackRepository()
    actor = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")

    def _mk(title):
        return res_repo.upsert_resource(
            Resource(id=None, tenant_id="tenant_1", type="xhs_copy", title=title, summary=None,
                     content_text="x", content_json={}, version=None, status="active",
                     visibility="private", owner_open_id="user_1", created_at=None, updated_at=None),
            actor=actor, conn=migrated_conn,
        )
    src, tgt = _mk("src"), _mk("tgt")

    # 模拟节点的 graph_ingest 已被处理成 succeeded(upsert_resource 入队的那条)
    with migrated_conn.cursor() as cur:
        cur.execute(
            "update resource_outbox set status='succeeded' where resource_id=%s and topic='graph_ingest'",
            (src.id,),
        )

    fb_repo.add_edge(tenant_id="tenant_1", source_resource_id=src.id, target_resource_id=tgt.id,
                     edge_type="measured_by", weight=1.0, conn=migrated_conn)

    with migrated_conn.cursor(row_factory=dict_row) as cur:
        rows = cur.execute(
            "select status, dedupe_key from resource_outbox where resource_id=%s and topic='graph_ingest'",
            (src.id,),
        ).fetchall()
    # 必须有一条新的 pending(边任务),与已 succeeded 的 node 任务并存、dedupe_key 不同
    statuses = sorted(r["status"] for r in rows)
    assert "pending" in statuses, f"加边未产生新任务,边会丢失:{statuses}"
    assert len({r["dedupe_key"] for r in rows}) == len(rows), "边任务与节点任务 dedupe_key 撞了"
