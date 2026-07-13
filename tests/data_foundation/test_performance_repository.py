import pytest

from data_foundation.repositories.resource import ResourceRepository
from data_foundation.repositories.performance import PerformanceRepository
from data_foundation.models import RuntimeIdentityConfig


def _create_resource(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    title: str,
    content_text: str,
    visibility: str,
    conn,
):
    return repo.upsert_resource(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        resource_type="xhs_copy",
        title=title,
        content_text=content_text,
        content_json={},
        status="active",
        visibility=visibility,
        owner_open_id=actor_open_id,
        conn=conn,
    )


def test_save_performance_calculates_weighted_score(migrated_conn):
    res_repo = ResourceRepository()
    perf_repo = PerformanceRepository()
    
    actor = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    
    # Create target resource
    target = _create_resource(
        res_repo,
        tenant_id=actor.tenant_id,
        actor_open_id=actor.open_id,
        title="My target resource",
        content_text="Some text",
        visibility="private",
        conn=migrated_conn,
    )
    
    likes, comments, shares = 10, 5, 2
    expected_score = float(likes * 1 + comments * 2 + shares * 3) # 26.0
    
    score = perf_repo.save_performance(
        resource_id=target.id,
        resource_version=int(target.version),
        likes=likes,
        comments=comments,
        shares=shares,
        actor=actor,
        conn=migrated_conn
    )
    
    assert score == expected_score
    
    # Verify the metric resource was stored
    rows = perf_repo.performance_rows(
        tenant_id="tenant_1",
        actor_open_id="user_1",
        resource_id=target.id,
        conn=migrated_conn
    )
    assert len(rows) == 1
    row = rows[0]
    
    assert row["title"] == "效果数据"
    assert row["weight"] == expected_score
    assert row["content_json"]["target_resource_id"] == str(target.id)
    assert row["content_json"]["target_resource_version"] == int(target.version)
    assert row["content_json"]["metrics"] == {"likes": likes, "comments": comments, "shares": shares}
    assert row["content_json"]["score"] == expected_score


def test_save_performance_denied_without_write_permission(migrated_conn):
    res_repo = ResourceRepository()
    perf_repo = PerformanceRepository()
    
    actor1 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    actor2 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_2")
    
    # Create private resource owned by user_1
    target = _create_resource(
        res_repo,
        tenant_id=actor1.tenant_id,
        actor_open_id=actor1.open_id,
        title="Private Resource",
        content_text="Some text",
        visibility="private",
        conn=migrated_conn,
    )
    
    # actor2 (user_2) has no write permission on target. Should raise PermissionError.
    with pytest.raises(PermissionError, match="is not writable by actor"):
        perf_repo.save_performance(
            resource_id=target.id,
            resource_version=int(target.version),
            likes=10,
            comments=5,
            shares=2,
            actor=actor2,
            conn=migrated_conn
        )


def test_performance_rows_filters_permissions(migrated_conn):
    res_repo = ResourceRepository()
    perf_repo = PerformanceRepository()
    
    actor1 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    actor2 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_2")
    
    # Create target resource owned by user_1 (private)
    target_private = _create_resource(
        res_repo,
        tenant_id=actor1.tenant_id,
        actor_open_id=actor1.open_id,
        title="Private target",
        content_text="Content",
        visibility="private",
        conn=migrated_conn,
    )
    
    # Save performance metrics for target_private using actor1
    perf_repo.save_performance(
        resource_id=target_private.id,
        resource_version=int(target_private.version),
        likes=10,
        comments=5,
        shares=2,
        actor=actor1,
        conn=migrated_conn
    )
    
    # actor1 should be able to read the performance rows
    rows_actor1 = perf_repo.performance_rows(
        tenant_id="tenant_1",
        actor_open_id="user_1",
        resource_id=target_private.id,
        conn=migrated_conn
    )
    assert len(rows_actor1) == 1
    
    # actor2 should NOT be able to read the performance rows
    rows_actor2 = perf_repo.performance_rows(
        tenant_id="tenant_1",
        actor_open_id="user_2",
        resource_id=target_private.id,
        conn=migrated_conn
    )
    assert len(rows_actor2) == 0
    
    # Now try with a team visible resource
    target_team = _create_resource(
        res_repo,
        tenant_id=actor1.tenant_id,
        actor_open_id=actor1.open_id,
        title="Team target",
        content_text="Content",
        visibility="team",
        conn=migrated_conn,
    )
    
    perf_repo.save_performance(
        resource_id=target_team.id,
        resource_version=int(target_team.version),
        likes=20,
        comments=10,
        shares=5,
        actor=actor1,
        conn=migrated_conn
    )
    
    # actor2 should be able to read the performance rows because visibility is team
    rows_team_actor2 = perf_repo.performance_rows(
        tenant_id="tenant_1",
        actor_open_id="user_2",
        resource_id=target_team.id,
        conn=migrated_conn
    )
    assert len(rows_team_actor2) == 1


def test_bulk_performance_metrics(migrated_conn):
    res_repo = ResourceRepository()
    perf_repo = PerformanceRepository()
    
    actor1 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_1")
    actor2 = RuntimeIdentityConfig(tenant_id="tenant_1", open_id="user_2")
    
    # Create target 1 (private to user_1)
    target1 = _create_resource(
        res_repo,
        tenant_id=actor1.tenant_id,
        actor_open_id=actor1.open_id,
        title="Target 1 Private",
        content_text="Content 1",
        visibility="private",
        conn=migrated_conn,
    )
    
    # Create target 2 (team visible to user_1)
    target2 = _create_resource(
        res_repo,
        tenant_id=actor1.tenant_id,
        actor_open_id=actor1.open_id,
        title="Target 2 Team",
        content_text="Content 2",
        visibility="team",
        conn=migrated_conn,
    )
    
    # Save performance for target1
    perf_repo.save_performance(
        resource_id=target1.id,
        resource_version=int(target1.version),
        likes=10,
        comments=5,
        shares=2,
        actor=actor1,
        conn=migrated_conn
    )
    
    # Save performance for target2
    perf_repo.save_performance(
        resource_id=target2.id,
        resource_version=int(target2.version),
        likes=20,
        comments=10,
        shares=5,
        actor=actor1,
        conn=migrated_conn
    )
    
    # 1. Bulk query without actor filtering (only by tenant_id)
    res_no_actor = perf_repo.bulk_performance_metrics(
        tenant_id="tenant_1",
        resource_ids=[str(target1.id), str(target2.id)],
        actor=None,
        conn=migrated_conn
    )
    assert len(res_no_actor[str(target1.id)]) == 1
    assert len(res_no_actor[str(target2.id)]) == 1
    assert res_no_actor[str(target1.id)][0]["metrics"]["likes"] == 10
    assert res_no_actor[str(target2.id)][0]["metrics"]["likes"] == 20
    
    # 2. Bulk query with actor1 (owner of both)
    res_actor1 = perf_repo.bulk_performance_metrics(
        tenant_id="tenant_1",
        resource_ids=[str(target1.id), str(target2.id)],
        actor=actor1,
        conn=migrated_conn
    )
    assert len(res_actor1[str(target1.id)]) == 1
    assert len(res_actor1[str(target2.id)]) == 1
    
    # 3. Bulk query with actor2 (user_2, can only read team visible target2)
    res_actor2 = perf_repo.bulk_performance_metrics(
        tenant_id="tenant_1",
        resource_ids=[str(target1.id), str(target2.id)],
        actor=actor2,
        conn=migrated_conn
    )
    assert len(res_actor2[str(target1.id)]) == 0
    assert len(res_actor2[str(target2.id)]) == 1
