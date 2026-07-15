import inspect

import pytest

from data_foundation.knowledge.repository import (
    KnowledgeRepository,
    _represent_near_similarity,
)
from data_foundation.knowledge.service import KnowledgeService
from data_foundation.repositories.resource import ResourceRepository


def _save(repo, *, tenant="tenant-a", owner="ou_owner", resource_id=None, text="正文", visibility="private"):
    return repo.upsert_resource(
        tenant_id=tenant,
        actor_open_id=owner,
        resource_type="feishu_doc",
        title="标题",
        content_text=text,
        content_json={"niche": "职场", "tags": ["复盘"]},
        visibility=visibility,
        resource_id=resource_id,
        outbox_requests=[],
    )


def test_knowledge_service_builds_history_current_family_and_real_material_edges(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    service = KnowledgeService(migrated_conn)
    first = _save(resources, text="Cafe\u0301\u200b\n\n👩\u200d💻")

    result_v1 = service.enrich_exact_version(
        tenant_id=first.tenant_id,
        resource_id=first.id,
        resource_version=1,
    )
    neighbor = _save(resources, text="职场复盘的另一篇真实素材")
    neighbor_result = service.enrich_exact_version(
        tenant_id=neighbor.tenant_id,
        resource_id=neighbor.id,
        resource_version=1,
    )
    second = _save(resources, resource_id=first.id, text="第二版正文")
    result_v2 = service.enrich_exact_version(
        tenant_id=second.tenant_id,
        resource_id=second.id,
        resource_version=2,
    )

    assert result_v1.status == result_v2.status == neighbor_result.status == "qualified"
    history = migrated_conn.execute(
        """
        select resource_version from qualified_knowledge_versions
        where tenant_id = %s and resource_id = %s order by resource_version
        """,
        (first.tenant_id, first.id),
    ).fetchall()
    current = migrated_conn.execute(
        """
        select resource_version from current_knowledge_targets
        where tenant_id = %s and resource_id = %s
        """,
        (first.tenant_id, first.id),
    ).fetchall()
    assert [row["resource_version"] for row in history] == [1, 2]
    assert [row["resource_version"] for row in current] == [2]

    anchors = migrated_conn.execute(
        "select id::text from resources where tenant_id = %s and type = 'knowledge_anchor'",
        (first.tenant_id,),
    ).fetchall()
    assert anchors == []
    edges = migrated_conn.execute(
        """
        select source_resource_version, target_resource_version, edge_type, properties
        from resource_edges
        where tenant_id = %s and source_resource_id = %s
        order by source_resource_version
        """,
        (first.tenant_id, first.id),
    ).fetchall()
    assert [edge["source_resource_version"] for edge in edges] == [1, 2]
    assert all(edge["target_resource_version"] == 1 for edge in edges)
    assert all(edge["edge_type"] in {"same_niche", "same_topic", "semantically_related"} for edge in edges)
    assert migrated_conn.execute(
        """
        select 1 from resource_edges
        where tenant_id = %s
          and source_resource_id = %s and source_resource_version = 1
          and target_resource_id = %s and target_resource_version = 1
        """,
        (first.tenant_id, neighbor.id, first.id),
    ).fetchone() is not None


def test_knowledge_enrich_retry_reuses_exact_family_without_orphan_rows(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    service = KnowledgeService(migrated_conn)
    resource = _save(resources, text="幂等正文")

    first = service.enrich_exact_version(
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        resource_version=1,
    )
    replay = service.enrich_exact_version(
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        resource_version=1,
    )

    assert replay.family_id == first.family_id
    assert migrated_conn.execute(
        "select count(*) as n from knowledge_families where tenant_id = %s",
        (resource.tenant_id,),
    ).fetchone()["n"] == 1


def test_search_reconcile_generation_cannot_collide_with_processing_job(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    service = KnowledgeService(migrated_conn)
    resource = _save(resources, text="generation reconciliation")

    service.enrich_exact_version(
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        resource_version=1,
    )
    first = migrated_conn.execute(
        """
        select id, payload
        from resource_outbox
        where tenant_id = %s and resource_id = %s
          and resource_version = 1 and topic = 'meili_index'
        """,
        (resource.tenant_id, resource.id),
    ).fetchone()
    assert first["payload"]["reconcile_generation"] == 1
    migrated_conn.execute(
        """
        update resource_outbox
        set status = 'processing', lease_owner = 'old-worker',
            lease_expires_at = now() + interval '1 minute'
        where id = %s
        """,
        (first["id"],),
    )

    service.enrich_exact_version(
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        resource_version=1,
    )

    rows = migrated_conn.execute(
        """
        select status, payload
        from resource_outbox
        where tenant_id = %s and resource_id = %s
          and resource_version = 1 and topic = 'meili_index'
        order by (payload->>'reconcile_generation')::bigint
        """,
        (resource.tenant_id, resource.id),
    ).fetchall()
    assert [row["payload"]["reconcile_generation"] for row in rows] == [1, 2]
    assert [row["status"] for row in rows] == ["processing", "pending"]


def test_exact_family_matching_is_owner_acl_and_tenant_isolated(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    service = KnowledgeService(migrated_conn)
    owner_a = _save(resources, owner="owner-a", text="完全相同正文")
    owner_a_2 = _save(resources, owner="owner-a", text="完全相同正文")
    owner_b = _save(resources, owner="owner-b", text="完全相同正文")
    other_tenant = _save(resources, tenant="tenant-b", owner="owner-a", text="完全相同正文")
    for resource in (owner_a, owner_a_2, owner_b, other_tenant):
        service.enrich_exact_version(
            tenant_id=resource.tenant_id,
            resource_id=resource.id,
            resource_version=1,
        )

    rows = migrated_conn.execute(
        """
        select resource_id::text, duplicate_family_id::text, duplicate_kind
        from knowledge_asset_states
        where tenant_id = 'tenant-a' and resource_id = any(%s::uuid[])
        """,
        ([owner_a.id, owner_a_2.id, owner_b.id],),
    ).fetchall()
    by_id = {row["resource_id"]: row for row in rows}
    assert by_id[owner_a.id]["duplicate_family_id"] == by_id[owner_a_2.id]["duplicate_family_id"]
    assert by_id[owner_a_2.id]["duplicate_kind"] == "exact"
    assert by_id[owner_b.id]["duplicate_family_id"] != by_id[owner_a.id]["duplicate_family_id"]
    tenant_b_family = migrated_conn.execute(
        """
        select duplicate_family_id::text from knowledge_asset_states
        where tenant_id = 'tenant-b' and resource_id = %s
        """,
        (other_tenant.id,),
    ).fetchone()["duplicate_family_id"]
    assert tenant_b_family != by_id[owner_a.id]["duplicate_family_id"]
    exact_edge = migrated_conn.execute(
        """
        select target_resource_id::text, target_resource_version, edge_type, weight, properties
        from resource_edges
        where tenant_id = 'tenant-a'
          and source_resource_id = %s and source_resource_version = 1
          and edge_type = 'duplicate_of'
        """,
        (owner_a_2.id,),
    ).fetchone()
    assert exact_edge["target_resource_id"] == owner_a.id
    assert exact_edge["target_resource_version"] == 1
    assert exact_edge["weight"] == 1.0
    assert exact_edge["properties"]["family_id"] == by_id[owner_a.id]["duplicate_family_id"]
    assert exact_edge["properties"]["match_kind"] == "exact"
    assert exact_edge["properties"]["similarity"] == 1.0
    assert exact_edge["properties"]["evidence"] == "normalized_sha256_equal"


def test_family_matching_uses_live_acl_and_unknown_visibility_fails_closed(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    service = KnowledgeService(migrated_conn)

    stale_team = _save(resources, owner="source-owner", visibility="team", text="旧团队权限正文")
    stale_result = service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=stale_team.id, resource_version=1
    )
    migrated_conn.execute(
        "update resources set visibility = 'private' where tenant_id = %s and id = %s",
        ("tenant-a", stale_team.id),
    )
    stale_probe = _save(resources, owner="viewer", visibility="private", text="旧团队权限正文")
    stale_probe_result = service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=stale_probe.id, resource_version=1
    )
    assert stale_probe_result.family_id != stale_result.family_id

    unknown = _save(resources, owner="source-owner", visibility="team", text="未知权限正文")
    unknown_result = service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=unknown.id, resource_version=1
    )
    migrated_conn.execute(
        "update resources set visibility = 'future_visibility' where tenant_id = %s and id = %s",
        ("tenant-a", unknown.id),
    )
    unknown_probe = _save(resources, owner="viewer", visibility="private", text="未知权限正文")
    unknown_probe_result = service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=unknown_probe.id, resource_version=1
    )
    assert unknown_probe_result.family_id != unknown_result.family_id

    granted = _save(resources, owner="source-owner", visibility="team", text="显式授权正文")
    granted_result = service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=granted.id, resource_version=1
    )
    migrated_conn.execute(
        "update resources set visibility = 'private' where tenant_id = %s and id = %s",
        ("tenant-a", granted.id),
    )
    migrated_conn.execute(
        """
        insert into resource_permissions (
          tenant_id, resource_id, subject_type, subject_id, permission
        ) values ('tenant-a', %s, 'user', 'viewer', 'read')
        """,
        (granted.id,),
    )
    granted_probe = _save(resources, owner="viewer", visibility="private", text="显式授权正文")
    granted_probe_result = service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=granted_probe.id, resource_version=1
    )
    assert granted_probe_result.family_id == granted_result.family_id


def test_qualified_assets_enqueue_one_debounced_actor_synthesis_job(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    service = KnowledgeService(migrated_conn)
    first = _save(resources, owner="ou-owner", text="第一份可沉淀素材")
    second = _save(resources, owner="ou-owner", text="第二份可沉淀素材")

    first_result = service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=first.id, resource_version=1
    )
    assert "preference_synthesize" in first_result.downstream_topics
    row = migrated_conn.execute(
        """
        select id, status, lease_owner, payload
        from resource_outbox
        where tenant_id = 'tenant-a' and topic = 'preference_synthesize'
        """
    ).fetchone()
    assert row["status"] == "pending"
    assert row["payload"]["actor_open_id"] == "ou-owner"
    migrated_conn.execute(
        """
        update resource_outbox
        set status = 'processing', lease_owner = 'stale-worker',
            lease_expires_at = now() + interval '1 minute'
        where id = %s
        """,
        (row["id"],),
    )

    service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=second.id, resource_version=1
    )
    # Replaying one exact qualification remains one actor job, while a new trigger
    # revokes any stale lease so its completion cannot swallow pending synthesis.
    service.enrich_exact_version(
        tenant_id="tenant-a", resource_id=first.id, resource_version=1
    )
    rows = migrated_conn.execute(
        """
        select status, lease_owner, payload
        from resource_outbox
        where tenant_id = 'tenant-a' and topic = 'preference_synthesize'
        """
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert rows[0]["lease_owner"] is None
    assert rows[0]["payload"]["actor_open_id"] == "ou-owner"
def test_near_family_creates_exact_variant_edge_and_retry_is_idempotent(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    service = KnowledgeService(migrated_conn)
    canonical_text = "小红书文案要先写真实场景，再给具体动作。" * 20
    variant_text = canonical_text[:-1] + "！"
    canonical = _save(resources, owner="owner-a", text=canonical_text)
    variant = _save(resources, owner="owner-a", text=variant_text)
    service.enrich_exact_version(
        tenant_id=canonical.tenant_id,
        resource_id=canonical.id,
        resource_version=1,
    )
    first = service.enrich_exact_version(
        tenant_id=variant.tenant_id,
        resource_id=variant.id,
        resource_version=1,
    )
    replay = service.enrich_exact_version(
        tenant_id=variant.tenant_id,
        resource_id=variant.id,
        resource_version=1,
    )

    assert first.duplicate_kind == replay.duplicate_kind == "near"
    assert first.family_id == replay.family_id
    edges = migrated_conn.execute(
        """
        select target_resource_id::text, target_resource_version, edge_type, weight, properties
        from resource_edges
        where tenant_id = %s
          and source_resource_id = %s and source_resource_version = 1
          and edge_type = 'variant_of'
        """,
        (variant.tenant_id, variant.id),
    ).fetchall()
    assert len(edges) == 1
    edge = edges[0]
    assert edge["target_resource_id"] == canonical.id
    assert edge["target_resource_version"] == 1
    assert 0.9 <= float(edge["weight"]) < 1.0
    assert edge["properties"]["family_id"] == first.family_id
    assert edge["properties"]["match_kind"] == "near"
    assert edge["properties"]["similarity"] == pytest.approx(float(edge["weight"]), abs=1e-6)
    assert edge["properties"]["evidence"] == "pg_trgm_similarity_gte_0.9"
    state_score = migrated_conn.execute(
        """
        select (metadata->>'duplicate_similarity')::double precision as score
        from knowledge_asset_states
        where tenant_id = %s and resource_id = %s and resource_version = 1
        """,
        (variant.tenant_id, variant.id),
    ).fetchone()["score"]
    assert state_score == pytest.approx(float(edge["weight"]), abs=1e-6)
    assert state_score < 1.0
    graph_jobs = migrated_conn.execute(
        """
        select count(*) as n from resource_outbox
        where tenant_id = %s and resource_id = %s and resource_version = 1
          and topic = 'graph_ingest'
        """,
        (variant.tenant_id, variant.id),
    ).fetchone()["n"]
    assert graph_jobs == 1


@pytest.mark.parametrize(
    ("raw_score", "expected"),
    [
        (0.91, 0.91),
        (0.999999, 0.999999),
        (1.0, 0.999999),
    ],
)
def test_near_similarity_representation_reserves_one_for_exact(raw_score, expected):
    represented = _represent_near_similarity(raw_score)

    assert represented == pytest.approx(expected)
    assert represented < 1.0


def test_near_family_candidate_recall_uses_trigram_index_operator():
    source = inspect.getsource(KnowledgeRepository._resolve_family)

    assert "pg_trgm.similarity_threshold" in source
    assert "OPERATOR(public.%%)" in source
    assert "similarity(candidate.normalized_text" in source


def test_knowledge_enrichment_rows_are_immutable(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    resource = _save(resources)
    KnowledgeService(migrated_conn).enrich_exact_version(
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        resource_version=1,
    )

    with pytest.raises(Exception, match="immutable"):
        migrated_conn.execute(
            "update knowledge_enrichments set created_by = 'tampered' where resource_id = %s",
            (resource.id,),
        )


def test_confirm_exact_version_is_acl_checked_and_cannot_bypass_copy_lifecycle(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    session = resources.upsert_resource(
        tenant_id="tenant-a", actor_open_id="owner-a", resource_type="session_snapshot",
        title="定位", content_text="只服务职场新人",
        content_json={"snapshot_kind": "positioning"}, outbox_requests=[],
    )
    repository = KnowledgeRepository(migrated_conn)
    result = repository.confirm_exact_version(
        "tenant-a", "owner-a", session.id, 1, "strategy_fact",
        {"snapshot_kind": "positioning"},
    )
    assert result["eligibility"] == "pending"
    confirmation = migrated_conn.execute(
        """
        select metadata->'confirmation' as confirmation
        from knowledge_asset_states
        where tenant_id = 'tenant-a' and resource_id = %s and resource_version = 1
        """,
        (session.id,),
    ).fetchone()["confirmation"]
    assert confirmation["snapshot_kind"] == "positioning"
    with pytest.raises(ValueError, match="does not match"):
        repository.confirm_exact_version(
            "tenant-a", "owner-a", session.id, 1, "strategy_fact",
            {"snapshot_kind": "decision"},
        )
    row = migrated_conn.execute(
        """
        select topic, payload from resource_outbox
        where tenant_id = 'tenant-a' and resource_id = %s and topic = 'knowledge_enrich'
        """,
        (session.id,),
    ).fetchone()
    assert row["payload"]["version"] == 1

    generated = resources.upsert_resource(
        tenant_id="tenant-a", actor_open_id="owner-a", resource_type="generated_copy",
        title="候选", content_text="候选正文", outbox_requests=[],
    )
    with pytest.raises(ValueError, match="lifecycle"):
        repository.confirm_exact_version(
            "tenant-a", "owner-a", generated.id, 1, "strategy_fact", {"snapshot_kind": "copy"}
        )


def test_confirm_exact_version_retry_never_demotes_qualified_state(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    session = resources.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_type="session_snapshot",
        title="定位",
        content_text="只服务职场新人",
        content_json={"snapshot_kind": "positioning"},
        outbox_requests=[],
    )
    repository = KnowledgeRepository(migrated_conn)
    repository.confirm_exact_version(
        "tenant-a",
        "owner-a",
        str(session.id),
        1,
        "strategy_fact",
        {"snapshot_kind": "positioning"},
    )
    result = KnowledgeService(migrated_conn).enrich_exact_version(
        tenant_id="tenant-a", resource_id=str(session.id), resource_version=1
    )
    assert result.status == "qualified"

    replay = repository.confirm_exact_version(
        "tenant-a",
        "owner-a",
        str(session.id),
        1,
        "strategy_fact",
        {"snapshot_kind": "positioning"},
    )

    assert replay["eligibility"] == "qualified"
    assert replay["idempotent_replay"] is True
    state = migrated_conn.execute(
        """
        select eligibility from knowledge_asset_states
        where tenant_id = %s and resource_id = %s and resource_version = 1
        """,
        ("tenant-a", session.id),
    ).fetchone()
    assert state["eligibility"] == "qualified"


def test_confirm_exact_version_retry_revives_terminal_job_while_pending(migrated_conn):
    resources = ResourceRepository(migrated_conn)
    session = resources.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_type="session_snapshot",
        title="目标",
        content_text="三个月内完成首轮验证",
        content_json={"snapshot_kind": "workflow_state"},
        outbox_requests=[],
    )
    repository = KnowledgeRepository(migrated_conn)
    repository.confirm_exact_version(
        "tenant-a", "owner-a", str(session.id), 1, "strategy_fact", {"snapshot_kind": "workflow_state"}
    )
    migrated_conn.execute(
        """
        update resource_outbox set status = 'succeeded'
        where tenant_id = %s and resource_id = %s and topic = 'knowledge_enrich'
        """,
        ("tenant-a", session.id),
    )

    replay = repository.confirm_exact_version(
        "tenant-a", "owner-a", str(session.id), 1, "strategy_fact", {"snapshot_kind": "workflow_state"}
    )

    assert replay["eligibility"] == "pending"
    assert replay["idempotent_replay"] is True
    job = migrated_conn.execute(
        """
        select status, attempts, lease_owner from resource_outbox
        where tenant_id = %s and resource_id = %s and topic = 'knowledge_enrich'
        """,
        ("tenant-a", session.id),
    ).fetchone()
    assert (job["status"], job["attempts"], job["lease_owner"]) == ("pending", 0, None)


def test_generated_target_revisit_creates_new_meili_reconciliation(migrated_conn):
    from data_foundation.repositories.generated_copy import GeneratedCopyRepository

    resources = ResourceRepository(migrated_conn)
    first = resources.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_type="generated_copy",
        title="A版",
        content_text="A版正文",
        content_json={"title": "A版", "body": "A版正文", "variant_label": "A"},
        owner_open_id="owner-a",
        outbox_requests=[],
    )
    second = resources.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_id=str(first.id),
        resource_type="generated_copy",
        title="B版",
        content_text="B版正文",
        content_json={"title": "B版", "body": "B版正文", "variant_label": "B"},
        owner_open_id="owner-a",
        outbox_requests=[],
    )
    lifecycle = GeneratedCopyRepository(resources)
    state = lifecycle.initialize_candidate(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_id=str(first.id),
        resource_version=1,
        label="A",
    )
    knowledge = KnowledgeService(migrated_conn)

    state = lifecycle.adopt_version(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_id=str(first.id),
        resource_version=1,
        expected_state_version=state.state_version,
    )
    knowledge.enrich_exact_version(
        tenant_id="tenant-a", resource_id=str(first.id), resource_version=1
    )
    migrated_conn.execute(
        """
        update resource_outbox set status = 'succeeded'
        where tenant_id = %s and resource_id = %s
          and resource_version = 1 and topic = 'meili_index'
        """,
        ("tenant-a", first.id),
    )

    state = lifecycle.adopt_version(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_id=str(first.id),
        resource_version=int(second.version),
        expected_state_version=state.state_version,
    )
    knowledge.enrich_exact_version(
        tenant_id="tenant-a",
        resource_id=str(first.id),
        resource_version=int(second.version),
    )
    state = lifecycle.adopt_version(
        tenant_id="tenant-a",
        actor_open_id="owner-a",
        resource_id=str(first.id),
        resource_version=1,
        expected_state_version=state.state_version,
    )
    knowledge.enrich_exact_version(
        tenant_id="tenant-a", resource_id=str(first.id), resource_version=1
    )

    rows = migrated_conn.execute(
        """
        select dedupe_key, status,
               (payload->>'reconcile_generation')::bigint as reconcile_generation
        from resource_outbox
        where tenant_id = %s and resource_id = %s
          and resource_version = 1 and topic = 'meili_index'
        order by reconcile_generation
        """,
        ("tenant-a", first.id),
    ).fetchall()
    assert len(rows) == 2
    assert [row["reconcile_generation"] for row in rows] == [1, 2]
    assert rows[0]["status"] == "succeeded"
    assert rows[1]["status"] == "pending"
    assert rows[0]["dedupe_key"] != rows[1]["dedupe_key"]
