from __future__ import annotations

import pytest

from data_foundation.creation_memory import save_generated_copy_resource
from data_foundation.performance_feedback import save_performance_metric_resource
from data_foundation.embedding_repository import EmbeddingRepository, VectorChunk
from data_foundation.repositories.generated_copy import (
    GeneratedCopyConflict,
    GeneratedCopyRepository,
)
from data_foundation.repositories.resource import ResourceRepository


def _seed_copy(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    topic = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_type="generated_topic",
        title="露营选题",
        content_text="轻量露营",
        visibility="team",
        owner_open_id="ou_user",
    )
    saved = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="露营别乱买",
        body="先看这份清单。",
        tags=["#露营"],
        source_topic="轻量露营",
        evidence=[{"resource_id": topic.id, "resource_version": int(topic.version)}],
    )
    return repo, topic.id, saved["resource"]["resource_id"]


def test_every_candidate_version_gets_exact_evidence_and_imitation_edges(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    reference = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_type="xhs_online_note",
        title="范本",
        content_text="范本正文",
        visibility="team",
        owner_open_id="ou_user",
        outbox_requests=[],
    )
    versions = [
        {
            "label": label,
            "title": f"{label} 标题",
            "body": f"{label} 正文",
            "tags": ["#测试"],
        }
        for label in ("A", "B", "C")
    ]

    saved = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="A 标题",
        body="A 正文",
        tags=["#测试"],
        versions=versions,
        evidence=[{
            "resource_id": reference.id,
            "resource_version": int(reference.version),
        }],
        reference_resource_id=reference.id,
        reference_resource_version=int(reference.version),
    )

    resource_id = saved["resource"]["resource_id"]
    rows = migrated_conn.execute(
        """
        select source_resource_version, edge_type
        from resource_edges
        where source_resource_id = %s
          and edge_type in ('derived_from', 'imitated_from')
        order by source_resource_version, edge_type
        """,
        (resource_id,),
    ).fetchall()
    assert {
        (int(row["source_resource_version"]), row["edge_type"])
        for row in rows
    } == {
        (version, edge_type)
        for version in (1, 2, 3)
        for edge_type in ("derived_from", "imitated_from")
    }


def test_candidate_revision_adoption_and_attribution_share_one_resource(migrated_conn):
    repo, topic_id, resource_id = _seed_copy(migrated_conn)
    lifecycle = GeneratedCopyRepository(repo)

    initial = lifecycle.get_state(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    assert initial.lifecycle_status == "candidate"
    assert initial.latest_resource_version == 1

    # 候选只投 graph，不进入 Meili 高质量知识。
    candidate_topics = {
        row[0]
        for row in migrated_conn.execute(
            "select topic from resource_outbox where resource_id = %s and resource_version = 1",
            (resource_id,),
        ).fetchall()
    }
    assert candidate_topics == {"graph_ingest"}
    assert migrated_conn.execute(
        """
        select 1 from resource_edges
        where source_resource_id = %s and target_resource_id = %s and edge_type = 'derived_from'
        """,
        (resource_id, topic_id),
    ).fetchone()

    revised = lifecycle.save_revision(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        expected_resource_version=1,
        expected_state_version=1,
        title="露营装备别乱买",
        body="真正需要的只有这几件。",
        tags=["#露营", "#避坑"],
        label="B",
    )
    assert revised.latest_resource_version == 2
    assert revised.selected_version == 2
    revision_edges = migrated_conn.execute(
        """
        select edge_type, target_resource_id::text as target_resource_id,
               target_resource_version, properties
        from resource_edges
        where source_resource_id = %s and source_resource_version = 2
        order by edge_type
        """,
        (resource_id,),
    ).fetchall()
    assert {row["edge_type"] for row in revision_edges} == {"derived_from", "revised_from"}
    assert next(row for row in revision_edges if row["edge_type"] == "derived_from")[
        "target_resource_id"
    ] == topic_id
    revised_from = next(row for row in revision_edges if row["edge_type"] == "revised_from")
    assert revised_from["target_resource_id"] == resource_id
    assert revised_from["target_resource_version"] == 1
    assert revised_from["properties"]["relation_kind"] == "revision"
    assert {
        row[0]
        for row in migrated_conn.execute(
            "select topic from resource_outbox where resource_id = %s and resource_version = 2",
            (resource_id,),
        ).fetchall()
    } == {"graph_ingest"}

    with pytest.raises(GeneratedCopyConflict, match="state version changed"):
        lifecycle.adopt_version(
            tenant_id="default",
            actor_open_id="ou_user",
            resource_id=resource_id,
            resource_version=2,
            expected_state_version=1,
        )

    adopted = lifecycle.adopt_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=2,
        expected_state_version=revised.state_version,
    )
    assert adopted.adopted_version == 2
    assert {
        row[0]
        for row in migrated_conn.execute(
            "select topic from resource_outbox where resource_id = %s and resource_version = 2",
            (resource_id,),
        ).fetchall()
    } == {"graph_ingest", "knowledge_enrich"}

    finalized = lifecycle.finalize_for_schedule(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        target_resource_version=2,
        expected_latest_resource_version=2,
        expected_state_version=adopted.state_version,
    )
    published = lifecycle.mark_published(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    assert finalized.finalized_version == 2
    assert published.published_version == 2
    assert migrated_conn.execute(
        """
        select 1
        from resource_outbox outbox
        join resource_events event on event.id = outbox.event_id
        where outbox.resource_id = %s and outbox.resource_version = 2
          and outbox.topic = 'knowledge_enrich' and event.event_type = 'published'
        """,
        (resource_id,),
    ).fetchone()

    metric = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        target_resource_id=resource_id,
        target_resource_version=2,
        metrics={"views": 1000, "likes": 100},
    )
    assert migrated_conn.execute(
        """
        select 1
        from resource_outbox outbox
        join resource_events event on event.id = outbox.event_id
        where outbox.resource_id = %s and outbox.resource_version = 2
          and outbox.topic = 'knowledge_enrich' and event.event_type = 'metrics_backfilled'
        """,
        (resource_id,),
    ).fetchone()
    assert metric["target_resource_version"] == 2
    metric_json = migrated_conn.execute(
        "select content_json from resources where id = %s",
        (metric["resource"]["resource_id"],),
    ).fetchone()[0]
    assert metric_json["target_resource_version"] == 2
    assert lifecycle.get_state(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    ).lifecycle_status == "measured"


def test_exact_adopted_retry_preserves_state_and_single_downstream_fact(migrated_conn):
    repo, _topic_id, resource_id = _seed_copy(migrated_conn)
    lifecycle = GeneratedCopyRepository(repo)
    initial = lifecycle.get_state(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    target_version = int(initial.selected_version)

    adopted = lifecycle.adopt_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=target_version,
        expected_state_version=initial.state_version,
    )
    stale_replay = lifecycle.adopt_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=target_version,
        expected_state_version=initial.state_version,
    )
    current_replay = lifecycle.adopt_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=target_version,
        expected_state_version=adopted.state_version,
    )

    assert stale_replay == adopted
    assert current_replay == adopted
    persisted = lifecycle.get_state(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    assert persisted == adopted
    assert migrated_conn.execute(
        """
        select count(*) as count
        from resource_events
        where tenant_id = 'default' and resource_id = %s
          and event_type = 'adopted'
        """,
        (resource_id,),
    ).fetchone()["count"] == 1
    assert migrated_conn.execute(
        """
        select count(*) as count
        from resource_outbox outbox
        join resource_events event
          on event.tenant_id = outbox.tenant_id and event.id = outbox.event_id
        where outbox.tenant_id = 'default' and outbox.resource_id = %s
          and outbox.topic = 'knowledge_enrich' and event.event_type = 'adopted'
        """,
        (resource_id,),
    ).fetchone()["count"] == 1
    assert migrated_conn.execute(
        """
        select count(*) as count
        from preference_observations
        where tenant_id = 'default' and owner_open_id = 'ou_user'
          and resource_id = %s and resource_version = %s
          and observation_type = 'adopted'
        """,
        (resource_id, target_version),
    ).fetchone()["count"] == 1


def test_schedule_final_draft_appends_snapshot_and_finalizes_atomically(migrated_conn):
    repo, _topic_id, resource_id = _seed_copy(migrated_conn)
    lifecycle = GeneratedCopyRepository(repo)

    state = lifecycle.finalize_for_schedule(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        target_resource_version=1,
        expected_latest_resource_version=1,
        expected_state_version=1,
        request_id="schedule-dirty-1",
        final_draft={
            "title": "排期最终稿",
            "body": "这是用户编辑后的精确正文。",
            "tags": ["#最终稿"],
        },
    )
    assert state.latest_resource_version == 2
    assert state.selected_version == state.adopted_version == state.finalized_version == 2
    versions = migrated_conn.execute(
        "select version, content_json from resource_versions where resource_id = %s order by version",
        (resource_id,),
    ).fetchall()
    assert [row[0] for row in versions] == [1, 2]
    assert versions[1][1]["variant_label"] == "A"
    snapshots = lifecycle.list_versions(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    assert snapshots[1]["resourceVersion"] == 2
    assert snapshots[1]["label"] == "A"
    assert snapshots[1]["body"] == versions[1][1]["body"]
    assert state.selected_label == snapshots[1]["label"]
    assert versions[1][1]["body"] == "这是用户编辑后的精确正文。"


def test_dirty_schedule_revises_selected_snapshot_when_latest_is_newer(migrated_conn):
    repo, _topic_id, resource_id = _seed_copy(migrated_conn)
    lifecycle = GeneratedCopyRepository(repo)
    revised = lifecycle.save_revision(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        expected_resource_version=1,
        expected_state_version=1,
        title="B 版标题",
        body="B 版正文",
        tags=["#B"],
        label="B",
    )
    selected = lifecycle.select_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=1,
        expected_state_version=revised.state_version,
        label="A",
    )

    finalized = lifecycle.finalize_for_schedule(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        target_resource_version=1,
        expected_latest_resource_version=2,
        expected_state_version=selected.state_version,
        request_id="schedule-selected-a",
        final_draft={"title": "A 最终稿", "body": "从 A 精确快照继续编辑", "tags": ["#A"]},
    )

    assert finalized.latest_resource_version == 3
    assert finalized.selected_version == finalized.finalized_version == 3
    snapshots = lifecycle.list_versions(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    assert snapshots[-1]["resourceVersion"] == 3
    assert snapshots[-1]["label"] == "A"
    assert snapshots[-1]["body"] == "从 A 精确快照继续编辑"


def test_performance_rejects_unadopted_candidate_version(migrated_conn):
    repo, _topic_id, resource_id = _seed_copy(migrated_conn)
    with pytest.raises(GeneratedCopyConflict, match="published"):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            target_resource_id=resource_id,
            target_resource_version=1,
            metrics={"likes": 1},
        )


def test_performance_rejects_adopted_but_unpublished_version(migrated_conn):
    repo, _topic_id, resource_id = _seed_copy(migrated_conn)
    lifecycle = GeneratedCopyRepository(repo)
    lifecycle.adopt_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=1,
        expected_state_version=1,
    )
    with pytest.raises(GeneratedCopyConflict, match="published"):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            target_resource_id=resource_id,
            target_resource_version=1,
            metrics={"likes": 1},
        )


def test_finalized_copy_rejects_select_revision_and_adopt_downgrade(migrated_conn):
    repo, _topic_id, resource_id = _seed_copy(migrated_conn)
    lifecycle = GeneratedCopyRepository(repo)
    finalized = lifecycle.finalize_for_schedule(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        target_resource_version=1,
        expected_latest_resource_version=1,
        expected_state_version=1,
    )
    with pytest.raises(GeneratedCopyConflict, match="cannot select"):
        lifecycle.select_version(
            tenant_id="default", actor_open_id="ou_user", resource_id=resource_id,
            resource_version=1, expected_state_version=finalized.state_version,
        )
    with pytest.raises(GeneratedCopyConflict, match="cannot revise"):
        lifecycle.save_revision(
            tenant_id="default", actor_open_id="ou_user", resource_id=resource_id,
            expected_resource_version=1, expected_state_version=finalized.state_version,
            title="不应保存", body="终态后禁止修改", tags=[],
        )
    with pytest.raises(GeneratedCopyConflict, match="cannot adopt"):
        lifecycle.adopt_version(
            tenant_id="default", actor_open_id="ou_user", resource_id=resource_id,
            resource_version=1, expected_state_version=finalized.state_version,
        )


def test_candidate_set_is_one_resource_three_versions_and_turn_retry_is_idempotent(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    candidates = [
        {"label": "A", "title": "A 标题", "body": "A 正文", "tags": ["#A"], "cover": "A封面", "note": "数据派"},
        {"label": "B", "title": "B 标题", "body": "B 正文", "tags": ["#B"], "cover": "B封面", "note": "情绪派"},
        {"label": "C", "title": "C 标题", "body": "C 正文", "tags": ["#C"], "cover": "C封面", "note": "故事派"},
    ]
    kwargs = dict(
        tenant_id="default",
        actor_open_id="ou_user",
        title="A 标题",
        body="A 正文",
        tags=["#A"],
        versions=candidates,
        origin_turn_id="turn-abc",
    )
    first = save_generated_copy_resource(repo, **kwargs)
    replay = save_generated_copy_resource(repo, **kwargs)

    assert replay["idempotent_replay"] is True
    assert first["resource"]["resource_id"] == replay["resource"]["resource_id"]
    assert first["resource"]["title"] == "A 标题"
    assert [item["resource_version"] for item in first["resource"]["versions"]] == [1, 2, 3]
    assert first["resource"]["resource_version"] == 1
    assert first["resource"]["latest_resource_version"] == 3
    resource_id = first["resource"]["resource_id"]
    assert migrated_conn.execute(
        "select count(*) from resources where tenant_id = 'default' and type = 'generated_copy'"
    ).fetchone()[0] == 1
    assert migrated_conn.execute(
        "select count(*) from resource_versions where resource_id = %s", (resource_id,)
    ).fetchone()[0] == 3
    assert {
        row[0]
        for row in migrated_conn.execute(
            "select topic from resource_outbox where resource_id = %s", (resource_id,)
        ).fetchall()
    } == {"graph_ingest"}
    state = GeneratedCopyRepository(repo).get_state(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    assert state.selected_version == 1
    assert state.knowledge_target_version is None


def test_existing_resource_candidate_revision_appends_instead_of_duplicating(migrated_conn):
    repo, _topic_id, resource_id = _seed_copy(migrated_conn)
    revised = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        expected_resource_version=1,
        expected_state_version=1,
        title="润色稿",
        body="润色后的正文",
        tags=["#润色"],
    )
    assert revised["resource"]["resource_id"] == resource_id
    assert revised["resource"]["resource_version"] == 2
    assert migrated_conn.execute(
        "select count(*) from resources where id = %s", (resource_id,)
    ).fetchone()[0] == 1
    assert migrated_conn.execute(
        "select count(*) from resource_versions where resource_id = %s", (resource_id,)
    ).fetchone()[0] == 2
    state = GeneratedCopyRepository(repo).get_state(
        tenant_id="default", actor_open_id="ou_user", resource_id=resource_id
    )
    assert state.selected_version == revised["resource"]["resource_version"] == 2


def test_implicit_single_revision_inherits_selected_slot_and_exact_optional_fields(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    saved = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="A title",
        body="A body",
        tags=[],
        versions=[
            {"label": "A", "title": "A title", "body": "A body", "tags": [], "cover": "A cover", "note": "A note"},
            {"label": "B", "title": "B title", "body": "B body", "tags": [], "cover": "B cover", "note": "B note"},
            {"label": "C", "title": "C title", "body": "C body", "tags": [], "cover": "C cover", "note": "C note"},
        ],
    )
    resource_id = saved["resource"]["resource_id"]
    lifecycle = GeneratedCopyRepository(repo)
    selected = lifecycle.select_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=2,
        expected_state_version=1,
        label="B",
    )
    revised = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        expected_resource_version=3,
        expected_state_version=selected.state_version,
        title="B polished",
        body="B polished body",
        tags=[],
    )
    version = revised["resource"]["resource_version"]
    snapshot = repo.get_resource_version(
        "default", "ou_user", resource_id, version
    )
    assert revised["resource"]["versions"][0]["label"] == "B"
    assert snapshot.content_json["variant_label"] == "B"
    assert snapshot.content_json["cover"] == "B cover"
    assert snapshot.content_json["note"] == "B note"


def test_semantic_search_reads_adopted_snapshot_when_latest_is_an_unadopted_candidate(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    saved = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="A 标题",
        body="A 被采纳正文",
        tags=[],
        versions=[
            {"label": "A", "title": "A 标题", "body": "A 被采纳正文", "tags": []},
            {"label": "B", "title": "B 标题", "body": "B 普通候选", "tags": []},
            {"label": "C", "title": "C 标题", "body": "C 最新但未采纳", "tags": []},
        ],
    )
    resource_id = saved["resource"]["resource_id"]
    lifecycle = GeneratedCopyRepository(repo)
    lifecycle.adopt_version(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=resource_id,
        resource_version=1,
        expected_state_version=1,
    )
    embeddings = EmbeddingRepository(migrated_conn)
    index = embeddings.create_index(
        tenant_id="default",
        embedding_model="model-a",
        config_version="cfg-a",
        chunker_version="text-v1",
        expected_resources=1,
    )
    vector = [0.1] * 1536
    assert embeddings.store_batch(
        tenant_id="default",
        embedding_index_id=index.id,
        resource_id=resource_id,
        resource_version=1,
        chunks=[VectorChunk(chunk_index=0, chunk_text="A 被采纳正文", embedding=vector)],
    ) == "stored"
    rows = repo.semantic_rows(
        tenant_id="default",
        actor_open_id="ou_user",
        embedding=vector,
        embedding_model="model-a",
        top_k=5,
    )
    assert rows[0]["title"] == "A 标题"
    assert rows[0]["content_text"] == "A 标题\n\nA 被采纳正文"
    assert "C 最新但未采纳" not in rows[0]["content_text"]
