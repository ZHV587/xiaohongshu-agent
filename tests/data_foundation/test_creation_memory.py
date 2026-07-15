from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

from data_foundation.repositories.resource import ResourceRepository
from data_foundation.writing_context import WritingContext
from data_foundation.creation_memory import (
    associate_ingested_resource,
    link_imitation_source,
    save_generated_copy_resource,
    save_generated_topic_resource,
    save_user_feedback_resource,
)


class _MemoryPreferenceRepository:
    def __init__(self):
        self.observations = {}
        self.state = None

    def acquire_actor_lock(self, **_kwargs):
        return None

    def insert_observation(self, *, observation, **_kwargs):
        inserted = observation.event_key not in self.observations
        self.observations.setdefault(observation.event_key, observation)
        return inserted

    def list_observations(self, **_kwargs):
        return list(self.observations.values())

    def get_profile_state(self, **_kwargs):
        return self.state

    def upsert_profile_state(self, **kwargs):
        self.state = dict(kwargs)
        return self.state


@pytest.fixture()
def preference_memory(monkeypatch):
    from data_foundation.repositories import preference as preference_repository

    memory = _MemoryPreferenceRepository()
    monkeypatch.setattr(preference_repository, "PreferenceRepository", lambda _conn: memory)
    return memory


@dataclass
class RecordingRepository:
    upserts: list[dict[str, Any]]
    edges: list[tuple[str, str, str]]

    def __init__(self):
        self.upserts = []
        self.edges = []
        self.edge_versions = []
        self.resources = {}
        self.conn = object()
        self.account_repo = SimpleNamespace(
            get_resource_context=lambda **_kwargs: WritingContext()
        )

    def unit_of_work(self):
        return nullcontext()

    def upsert_resource(self, **kwargs):
        self.upserts.append(kwargs)
        resource_id = kwargs.get("resource_id") or f"generated-{len(self.resources) + 1}"
        resource = SimpleNamespace(
            id=resource_id,
            type=kwargs["resource_type"],
            title=kwargs["title"],
            version=1,
            content_text=kwargs.get("content_text"),
            content_json=dict(kwargs.get("content_json") or {}),
            visibility=kwargs.get("visibility", "private"),
            owner_open_id=kwargs.get("owner_open_id"),
        )
        self.resources[(str(resource_id), 1)] = resource
        return resource

    def add_edge(self, **kwargs):
        self.edges.append((
            kwargs["source_resource_id"],
            kwargs["target_resource_id"],
            kwargs["edge_type"],
        ))
        self.edge_versions.append(
            (kwargs["source_resource_version"], kwargs["target_resource_version"])
        )

    def get_resource_version(self, tenant_id, actor_open_id, resource_id, resource_version):
        stored = self.resources.get((str(resource_id), int(resource_version)))
        if stored is not None:
            return stored
        return SimpleNamespace(
            id=resource_id,
            version=resource_version,
            type="generated_copy",
            title="目标文案",
            content_text="目标正文",
            content_json={"title": "目标文案", "body": "目标正文", "tags": []},
            visibility="team",
            owner_open_id=actor_open_id,
        )

    def get_resource(self, _tenant_id, _actor_open_id, resource_id):
        versions = [
            resource
            for (stored_id, _version), resource in self.resources.items()
            if stored_id == str(resource_id)
        ]
        return versions[-1] if versions else None


def test_save_generated_topic_persists_resource_and_evidence_edges():
    repo = RecordingRepository()

    result = save_generated_topic_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        direction="露营装备",
        topics=["轻量露营（收藏点强）", "亲子露营（决策链短）"],
        evidence=[
                {
                    "resource_id": "source-1",
                    "resource_version": 4,
                "title": "轻量露营样本",
                "summary": "轻量清单收藏高",
                "source_updated_at": "2026-05-01T08:00:00+00:00",
                "indexed_at": "2026-06-19T12:30:00+00:00",
            },
            {"resource_id": "source-1", "resource_version": 4, "summary": "重复来源应去重"},
        ],
    )

    assert result == {
        "ok": True,
        "resource": {
            "resource_id": "generated-1",
            "type": "generated_topic",
            "title": "露营装备 选题",
            "version": 1,
        },
        "evidence_count": 1,
    }
    assert repo.upserts[0]["resource_type"] == "generated_topic"
    assert repo.upserts[0]["title"] == "露营装备 选题"
    assert repo.upserts[0]["summary"] == "轻量露营（收藏点强）; 亲子露营（决策链短）"
    assert repo.upserts[0]["content_text"] == "- 轻量露营（收藏点强）\n- 亲子露营（决策链短）"
    assert repo.upserts[0]["content_json"] == {
        "direction": "露营装备",
        "topics": ["轻量露营（收藏点强）", "亲子露营（决策链短）"],
        "evidence": [{
            "resource_id": "source-1",
            "resource_version": 4,
            "title": "轻量露营样本",
            "summary": "轻量清单收藏高",
            "source_updated_at": "2026-05-01T08:00:00+00:00",
            "indexed_at": "2026-06-19T12:30:00+00:00",
        }],
    }
    assert repo.upserts[0]["visibility"] == "team"
    assert repo.upserts[0]["owner_open_id"] == "ou_user"
    assert [request.topic for request in repo.upserts[0]["outbox_requests"]] == ["knowledge_enrich"]
    assert repo.edges == [("generated-1", "source-1", "derived_from")]
    assert repo.edge_versions == [(1, 4)]


def test_save_generated_copy_persists_publishable_text_and_evidence_edges():
    repo = RecordingRepository()

    result = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="露营别乱买",
        body="这份清单够了",
        tags=["#露营", "#装备"],
        source_topic="轻量露营",
        evidence=[{
            "resource_id": "source-1",
            "resource_version": 4,
            "title": "轻量露营样本",
            "summary": "清单型内容收藏高",
            "source_updated_at": "未知",
            "indexed_at": "2026-06-19T12:30:00+00:00",
        }],
    )

    assert result["ok"] is True
    assert result["resource"]["type"] == "generated_copy"
    assert repo.upserts[0]["resource_type"] == "generated_copy"
    assert repo.upserts[0]["title"] == "露营别乱买"
    assert repo.upserts[0]["summary"] == "轻量露营"
    assert repo.upserts[0]["content_text"] == "露营别乱买\n\n这份清单够了\n\n#露营 #装备"
    assert repo.upserts[0]["content_json"] == {
        "title": "露营别乱买",
        "body": "这份清单够了",
        "tags": ["#露营", "#装备"],
        "cover": "",
        "note": "",
        "variant_label": "A",
        "source_topic": "轻量露营",
        "evidence": [{
            "resource_id": "source-1",
            "resource_version": 4,
            "title": "轻量露营样本",
            "summary": "清单型内容收藏高",
            "source_updated_at": "未知",
            "indexed_at": "2026-06-19T12:30:00+00:00",
        }],
        "resource_context": {
            "schema_version": 1,
            "account_id": None,
            "niche": None,
            "scope_key": "global",
        },
    }
    assert repo.edges == [("generated-1", "source-1", "derived_from")]


def test_save_generated_copy_links_imitation_source_edge():
    """§5 仿写:传 reference_resource_id 时,除 derived_from 证据边外再建 imitated_from 范本边。"""
    repo = RecordingRepository()
    result = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="露营别乱买",
        body="这份清单够了",
        tags=["#露营"],
        source_topic="轻量露营",
        evidence=[{"resource_id": "source-1", "resource_version": 4, "summary": "清单收藏高"}],
        reference_resource_id="ref-note-1",
        reference_resource_version=6,
    )
    assert result["ok"] is True
    assert ("generated-1", "source-1", "derived_from") in repo.edges
    assert ("generated-1", "ref-note-1", "imitated_from") in repo.edges


def test_save_generated_copy_links_every_candidate_exact_version():
    class _VersionedRepository(RecordingRepository):
        def upsert_resource(self, **kwargs):
            self.upserts.append(kwargs)
            resource_id = kwargs.get("resource_id") or "generated-1"
            versions = [
                version
                for stored_id, version in self.resources
                if stored_id == str(resource_id)
            ]
            version = max(versions, default=0) + 1
            resource = SimpleNamespace(
                id=resource_id,
                type=kwargs["resource_type"],
                title=kwargs["title"],
                version=version,
                content_text=kwargs.get("content_text"),
                content_json=dict(kwargs.get("content_json") or {}),
                visibility=kwargs.get("visibility", "private"),
                owner_open_id=kwargs.get("owner_open_id"),
            )
            self.resources[(str(resource_id), version)] = resource
            return resource

    repo = _VersionedRepository()
    candidates = [
        {"label": label, "title": f"{label} 标题", "body": f"{label} 正文", "tags": []}
        for label in ("A", "B", "C")
    ]
    result = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="A 标题",
        body="A 正文",
        tags=[],
        versions=candidates,
        evidence=[{"resource_id": "source-1", "resource_version": 4}],
        reference_resource_id="reference-1",
        reference_resource_version=6,
    )

    assert [item["resource_version"] for item in result["resource"]["versions"]] == [1, 2, 3]
    assert {
        (edge_type, source_version, target_version)
        for (_, _, edge_type), (source_version, target_version) in zip(
            repo.edges, repo.edge_versions, strict=True
        )
    } == {
        (edge_type, source_version, target_version)
        for source_version in (1, 2, 3)
        for edge_type, target_version in (("derived_from", 4), ("imitated_from", 6))
    } | {
        ("co_generated_variant", 1, 2),
        ("co_generated_variant", 2, 1),
        ("co_generated_variant", 3, 1),
    }


def test_save_generated_copy_rejects_more_than_three_ui_candidates():
    repo = RecordingRepository()
    versions = [
        {"label": label, "title": f"{label} 标题", "body": f"{label} 正文", "tags": []}
        for label in ("A", "B", "C", "D")
    ]
    with pytest.raises(ValueError, match="at most 3"):
        save_generated_copy_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            title="A 标题",
            body="A 正文",
            tags=[],
            versions=versions,
        )


def test_existing_resource_revision_requires_both_cas_tokens(monkeypatch):
    import data_foundation.repositories.generated_copy as lifecycle_module

    repo = RecordingRepository()
    repo.conn = type("Conn", (), {"transaction": lambda self: nullcontext()})()
    calls = []

    class _Lifecycle:
        def __init__(self, _repo):
            pass

        def save_revision(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["expected_resource_version"] == 1
            assert kwargs["expected_state_version"] == 1
            assert kwargs["label"] is None
            assert kwargs["cover"] is None
            assert kwargs["note"] is None
            return type(
                "State",
                (),
                {
                    "latest_resource_version": 2,
                    "state_version": 2,
                    "selected_label": "B",
                },
            )()

        def select_version(self, **kwargs):
            return type("State", (), {"state_version": 3})()

    monkeypatch.setattr(lifecycle_module, "GeneratedCopyRepository", _Lifecycle)
    result = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="existing-1",
        expected_resource_version=1,
        expected_state_version=1,
        title="润色标题",
        body="润色正文",
        tags=["#润色"],
    )

    assert calls
    assert result["resource"]["resource_id"] == "existing-1"
    assert result["resource"]["latest_resource_version"] == 2
    assert result["resource"]["state_version"] == 2
    assert result["resource"]["versions"][0]["label"] == "B"


def test_existing_resource_revision_fails_closed_when_cas_tokens_are_missing():
    repo = RecordingRepository()
    repo.conn = type("Conn", (), {"transaction": lambda self: nullcontext()})()

    with pytest.raises(ValueError, match="expected_resource_version"):
        save_generated_copy_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            resource_id="existing-1",
            title="Polished title",
            body="Polished body",
            tags=[],
        )


def test_save_generated_content_requires_non_empty_payloads():
    repo = RecordingRepository()

    with pytest.raises(ValueError, match="direction"):
        save_generated_topic_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            direction=" ",
            topics=["有效"],
        )
    with pytest.raises(ValueError, match="topics"):
        save_generated_topic_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            direction="露营",
            topics=[" "],
        )
    with pytest.raises(ValueError, match="title"):
        save_generated_copy_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            title=" ",
            body="正文",
            tags=["#标签"],
        )
    with pytest.raises(ValueError, match="body"):
        save_generated_copy_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            title="标题",
            body=" ",
            tags=["#标签"],
        )


def test_save_user_feedback_persists_feedback_and_optional_target_edge(preference_memory):
    repo = RecordingRepository()

    result = save_user_feedback_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        feedback="标题再狠一点",
        target_resource_id="generated-0",
        target_resource_version=3,
        feedback_type="revision_request",
    )

    assert result["ok"] is True
    assert result["resource"]["type"] == "revision_request"
    assert repo.upserts[0]["resource_type"] == "revision_request"
    assert repo.upserts[0]["title"] == "修改意见"
    assert repo.upserts[0]["summary"] == "标题再狠一点"
    assert repo.upserts[0]["content_text"] == "标题再狠一点"
    assert repo.upserts[0]["content_json"]["feedback"] == "标题再狠一点"
    assert repo.upserts[0]["content_json"]["target_resource_id"] == "generated-0"
    assert repo.upserts[0]["content_json"]["target_resource_version"] == 3
    assert repo.upserts[0]["content_json"]["feedback_type"] == "revision_request"
    assert repo.upserts[0]["content_json"]["idempotency_key"]
    assert [edge for edge in repo.edges if edge[2] == "feedback_on"] == [
        (result["resource"]["resource_id"], "generated-0", "feedback_on")
    ]
    assert len(preference_memory.observations) == 1


def test_save_user_feedback_retry_reuses_resource_and_preference_event(preference_memory):
    repo = RecordingRepository()
    kwargs = {
        "tenant_id": "default",
        "actor_open_id": "ou_user",
        "feedback": "再短一点",
        "target_resource_id": "generated-0",
        "target_resource_version": 3,
        "feedback_type": "revision_request",
        "idempotency_key": "tool-call-1",
    }

    first = save_user_feedback_resource(repo, **kwargs)
    replay = save_user_feedback_resource(repo, **kwargs)

    assert replay["resource"]["resource_id"] == first["resource"]["resource_id"]
    assert replay["resource"]["version"] == first["resource"]["version"] == 1
    assert replay["idempotent_replay"] is True
    assert len(preference_memory.observations) == 1


def test_save_user_feedback_validates_type_and_text():
    repo = RecordingRepository()

    with pytest.raises(ValueError, match="feedback is required"):
        save_user_feedback_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            feedback=" ",
        )
    with pytest.raises(ValueError, match="feedback_type"):
        save_user_feedback_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            feedback="很好",
            feedback_type="other",
        )
    with pytest.raises(ValueError, match="target_resource_id"):
        save_user_feedback_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            feedback="标题再狠一点",
            feedback_type="revision_request",
        )


class AssocRepo:
    """记录 add_edge 的 (source, target, edge_type, weight),支持读权限闸门。"""

    def __init__(self, unreadable: set[str] | None = None):
        self.edges: list[tuple[str, str, str, float]] = []
        self.edge_versions: list[tuple[int, int]] = []
        self.unreadable = unreadable or set()
        self.conn = None

    def add_edge(
        self,
        *,
        tenant_id,
        source_resource_id,
        source_resource_version,
        target_resource_id,
        target_resource_version,
        edge_type,
        weight=1.0,
        properties=None,
    ):
        self.edges.append((source_resource_id, target_resource_id, edge_type, weight))
        self.edge_versions.append((source_resource_version, target_resource_version))

    def get_resource_version(self, tenant_id, actor_open_id, resource_id, resource_version):
        if resource_id in self.unreadable:
            return None
        return SimpleNamespace(id=resource_id, version=resource_version)


def test_associate_links_semantic_neighbors_capped_and_weighted():
    """§0:对可读邻居建 semantically_related 边,weight=score,取前 max_edges 条。"""
    repo = AssocRepo()
    out = associate_ingested_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="new-1",
        resource_version=2,
        neighbors=[
            {"resource_id": "n1", "resource_version": 1, "score": 0.9},
            {"resource_id": "n2", "resource_version": 2, "score": 0.7},
            {"resource_id": "n3", "resource_version": 3, "score": 0.5},
            {"resource_id": "n4", "resource_version": 4, "score": 0.4},  # 超过 max_edges=3,应被截断
        ],
        co_ingested_resources=[{"resource_id": "new-1", "resource_version": 2}],
        max_edges=3,
    )
    sem = [e for e in repo.edges if e[2] == "semantically_related"]
    assert len(sem) == 3
    assert sem[0] == ("new-1", "n1", "semantically_related", 0.9)
    assert out == {"semantic": 3, "co_ingested": 0, "isolated": False}


def test_associate_dedupes_self_and_repeats():
    """自身与重复 target 去重,不建自环/重边。"""
    repo = AssocRepo()
    out = associate_ingested_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="new-1",
        resource_version=2,
        neighbors=[
            {"resource_id": "new-1", "resource_version": 2, "score": 0.99},  # 自身,跳过
            {"resource_id": "n1", "resource_version": 1, "score": 0.8},
            {"resource_id": "n1", "resource_version": 1, "score": 0.6},  # 重复,跳过
        ],
        co_ingested_resources=[],
    )
    assert len(repo.edges) == 1
    assert out["semantic"] == 1


def test_associate_co_ingested_fallback_when_no_neighbors():
    """无语义邻居时退化为同批 co_ingested,保证不孤岛。"""
    repo = AssocRepo()
    out = associate_ingested_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="new-1",
        resource_version=2,
        neighbors=[],
        co_ingested_resources=[
            {"resource_id": "new-1", "resource_version": 2},
            {"resource_id": "new-2", "resource_version": 3},
            {"resource_id": "new-3", "resource_version": 4},
        ],
    )
    co = [e for e in repo.edges if e[2] == "co_ingested"]
    assert {e[1] for e in co} == {"new-2", "new-3"}
    assert out == {"semantic": 0, "co_ingested": 2, "isolated": False}


def test_associate_isolated_when_nothing_to_link():
    """全库第一条(无邻居、无同批伙伴):唯一允许的孤岛,如实标记。"""
    repo = AssocRepo()
    out = associate_ingested_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="new-1",
        resource_version=2,
        neighbors=[],
        co_ingested_resources=[{"resource_id": "new-1", "resource_version": 2}],
    )
    assert repo.edges == []
    assert out["isolated"] is True


def test_associate_skips_unreadable_neighbor():
    """越权闸门:不可读邻居不建边(防连他人私有资源)。"""
    repo = AssocRepo(unreadable={"private"})
    out = associate_ingested_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="new-1",
        resource_version=2,
        neighbors=[{"resource_id": "private", "resource_version": 9, "score": 0.9}],
        co_ingested_resources=[],
    )
    assert repo.edges == []
    assert out["isolated"] is True


def test_link_imitation_source_builds_edge():
    """§5:成品 → 范本建 imitated_from 边。"""
    repo = AssocRepo()
    ok = link_imitation_source(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        copy_resource_id="copy-1",
        copy_resource_version=3,
        reference_resource_id="ref-1",
        reference_resource_version=8,
    )
    assert ok is True
    assert repo.edges == [("copy-1", "ref-1", "imitated_from", 1.0)]
    assert repo.edge_versions == [(3, 8)]


def test_link_imitation_source_gated_and_guarded():
    """不可读范本不建边;空/自环范本返回 False。"""
    repo = AssocRepo(unreadable={"ref-private"})
    assert link_imitation_source(
        repo, tenant_id="default", actor_open_id="ou_user",
        copy_resource_id="copy-1", copy_resource_version=3,
        reference_resource_id="ref-private", reference_resource_version=8,
    ) is False
    assert link_imitation_source(
        repo, tenant_id="default", actor_open_id="ou_user",
        copy_resource_id="copy-1", copy_resource_version=3,
        reference_resource_id=" ", reference_resource_version=8,
    ) is False
    assert link_imitation_source(
        repo, tenant_id="default", actor_open_id="ou_user",
        copy_resource_id="copy-1", copy_resource_version=3,
        reference_resource_id="copy-1", reference_resource_version=3,
    ) is False
    assert repo.edges == []


def test_creation_memory_writes_real_resource_edges(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    source = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_type="feishu_base_record",
        title="轻量露营样本",
        summary="清单型内容收藏高",
        content_text="轻量露营清单",
        content_json={},
        visibility="team",
        owner_open_id="ou_user",
    )

    result = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        title="露营别乱买",
        body="这份清单够了",
        tags=["#露营"],
        source_topic="轻量露营",
        evidence=[{
            "resource_id": source.id,
            "resource_version": int(source.version),
            "summary": "清单型内容收藏高",
        }],
    )
    resource_id = result["resource"]["resource_id"]
    resource_version = result["resource"]["resource_version"]
    edge = migrated_conn.execute(
        """
        select source_resource_id::text, source_resource_version,
               target_resource_id::text, target_resource_version, edge_type
        from resource_edges
        where tenant_id = %s
          and source_resource_id = %s
          and source_resource_version = %s
          and target_resource_id = %s
          and target_resource_version = %s
          and edge_type = 'derived_from'
        """,
        ("default", resource_id, resource_version, source.id, int(source.version)),
    ).fetchone()
    assert edge == (
        resource_id,
        resource_version,
        source.id,
        int(source.version),
        "derived_from",
    )


def test_creation_memory_rolls_back_when_valid_evidence_edge_write_fails(
    migrated_conn, monkeypatch
):
    repo = ResourceRepository(migrated_conn)
    source = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_type="xhs_note",
        title="可读来源",
        content_text="真实来源正文",
        visibility="team",
        owner_open_id="ou_user",
    )
    baseline = repo.debug_counts()
    baseline_edges = migrated_conn.execute(
        "select count(*) from resource_edges"
    ).fetchone()[0]

    def reject_edge(**_kwargs):
        raise ValueError("edge write failed")

    monkeypatch.setattr(repo, "add_edge", reject_edge)

    with pytest.raises(ValueError, match="edge write failed"):
        save_generated_copy_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            title="露营别乱买",
            body="这份清单够了",
            tags=["#露营"],
            evidence=[{
                "resource_id": source.id,
                "resource_version": int(source.version),
            }],
        )

    counts = repo.debug_counts()
    assert counts["resources"] == baseline["resources"]
    assert counts["resource_versions"] == baseline["resource_versions"]
    assert counts["resource_outbox"] == baseline["resource_outbox"]
    assert migrated_conn.execute(
        "select count(*) from resource_edges"
    ).fetchone()[0] == baseline_edges
