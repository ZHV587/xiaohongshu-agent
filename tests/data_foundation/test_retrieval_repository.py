from datetime import timedelta

from data_foundation.knowledge.service import KnowledgeService
from data_foundation.performance_feedback import save_performance_metric_resource
from data_foundation.repositories.resource import ResourceRepository


def _save(
    repo: ResourceRepository,
    *,
    resource_id: str | None = None,
    owner: str = "owner-a",
    visibility: str = "team",
    text: str = "职场新人复盘方法",
):
    return repo.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id=owner,
        resource_id=resource_id,
        resource_type="feishu_doc",
        title="职场复盘",
        content_text=text,
        content_json={"niche": "职场", "tags": ["复盘"]},
        visibility=visibility,
        owner_open_id=owner,
        outbox_requests=[],
    )


def _qualify(conn, resource) -> None:
    KnowledgeService(conn).enrich_exact_version(
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        resource_version=resource.version,
    )


def test_current_knowledge_rows_is_exact_current_acl_and_filter_gate(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    team = _save(repo, text="团队可读的职场复盘")
    private = _save(repo, visibility="private", text="仅 owner 可读的职场复盘")
    _qualify(migrated_conn, team)
    _qualify(migrated_conn, private)

    rows = repo.current_knowledge_rows(
        tenant_id="tenant-a",
        actor_open_id="viewer",
        resource_ids=[private.id, team.id],
        resource_versions=[private.version, team.version],
    )
    assert [(row["resource_id"], row["resource_version"]) for row in rows] == [
        (team.id, team.version)
    ]
    row = rows[0]
    assert row["niche"] == "职场"
    assert 0.0 <= float(row["quality_score"]) <= 1.0

    filtered = repo.current_knowledge_rows(
        tenant_id="tenant-a",
        actor_open_id="viewer",
        resource_ids=[team.id],
        resource_versions=[team.version],
        asset_kinds=[row["asset_kind"]],
        source_kinds=[row["source_kind"]],
        niches=["职场"],
        min_quality=float(row["quality_score"]),
        updated_after=row["qualified_at"] - timedelta(seconds=1),
    )
    assert len(filtered) == 1
    assert repo.current_knowledge_rows(
        tenant_id="tenant-a",
        actor_open_id="viewer",
        resource_ids=[team.id],
        resource_versions=[team.version],
        niches=["母婴"],
    ) == []

    revised = _save(repo, resource_id=team.id, text="第二版团队职场复盘")
    _qualify(migrated_conn, revised)
    exact = repo.current_knowledge_rows(
        tenant_id="tenant-a",
        actor_open_id="viewer",
        resource_ids=[team.id, revised.id],
        resource_versions=[team.version, revised.version],
    )
    assert [(row["resource_id"], row["resource_version"]) for row in exact] == [
        (revised.id, revised.version)
    ]


def test_bulk_performance_metrics_follow_exact_measured_by_edges(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    target = _save(repo, visibility="private")
    _qualify(migrated_conn, target)
    metric = save_performance_metric_resource(
        repo,
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        target_resource_id=target.id,
        target_resource_version=target.version,
        metrics={"likes": 1200, "collects": 300},
        published_at="2026-07-01T00:00:00Z",
    )

    owner_rows = repo.bulk_exact_performance_metrics(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_ids=[target.id],
        resource_versions=[target.version],
    )
    assert len(owner_rows[(target.id, target.version)]) == 1
    assert owner_rows[(target.id, target.version)][0]["resource_version"] == metric[
        "resource"
    ]["version"]
    assert owner_rows[(target.id, target.version)][0]["metrics"]["likes"] == 1200

    viewer_rows = repo.bulk_exact_performance_metrics(
        tenant_id="tenant-a",
        actor_open_id="viewer",
        resource_ids=[target.id],
        resource_versions=[target.version],
    )
    assert viewer_rows[(target.id, target.version)] == []

    revised = _save(repo, resource_id=target.id, visibility="private", text="第二版")
    _qualify(migrated_conn, revised)
    current_rows = repo.bulk_exact_performance_metrics(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_ids=[revised.id],
        resource_versions=[revised.version],
    )
    assert current_rows[(revised.id, revised.version)] == []
