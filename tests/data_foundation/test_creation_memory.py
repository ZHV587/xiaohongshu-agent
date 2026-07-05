from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

from data_foundation.graph import expand_graph
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.creation_memory import (
    associate_ingested_resource,
    link_imitation_source,
    save_generated_copy_resource,
    save_generated_topic_resource,
    save_user_feedback_resource,
)


@dataclass
class RecordingRepository:
    upserts: list[dict[str, Any]]
    edges: list[tuple[str, str, str]]

    def __init__(self):
        self.upserts = []
        self.edges = []

    def unit_of_work(self):
        return nullcontext()

    def upsert_resource(self, **kwargs):
        self.upserts.append(kwargs)
        return SimpleNamespace(
            id=f"generated-{len(self.upserts)}",
            type=kwargs["resource_type"],
            title=kwargs["title"],
            version=1,
        )

    def add_edge(self, **kwargs):
        self.edges.append((
            kwargs["source_resource_id"],
            kwargs["target_resource_id"],
            kwargs["edge_type"],
        ))


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
                "title": "轻量露营样本",
                "summary": "轻量清单收藏高",
                "source_updated_at": "2026-05-01T08:00:00+00:00",
                "indexed_at": "2026-06-19T12:30:00+00:00",
            },
            {"resource_id": "source-1", "summary": "重复来源应去重"},
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
            "title": "轻量露营样本",
            "summary": "轻量清单收藏高",
            "source_updated_at": "2026-05-01T08:00:00+00:00",
            "indexed_at": "2026-06-19T12:30:00+00:00",
        }],
    }
    assert repo.upserts[0]["visibility"] == "team"
    assert repo.upserts[0]["owner_open_id"] == "ou_user"
    assert [request.topic for request in repo.upserts[0]["outbox_requests"]] == ["meili_index", "graph_ingest"]
    assert repo.edges == [("generated-1", "source-1", "derived_from")]


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
        "source_topic": "轻量露营",
        "evidence": [{
            "resource_id": "source-1",
            "title": "轻量露营样本",
            "summary": "清单型内容收藏高",
            "source_updated_at": "未知",
            "indexed_at": "2026-06-19T12:30:00+00:00",
        }],
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
        evidence=[{"resource_id": "source-1", "summary": "清单收藏高"}],
        reference_resource_id="ref-note-1",
    )
    assert result["ok"] is True
    assert ("generated-1", "source-1", "derived_from") in repo.edges
    assert ("generated-1", "ref-note-1", "imitated_from") in repo.edges


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


def test_save_user_feedback_persists_feedback_and_optional_target_edge():
    repo = RecordingRepository()

    result = save_user_feedback_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        feedback="标题再狠一点",
        target_resource_id="generated-0",
        feedback_type="revision_request",
    )

    assert result["ok"] is True
    assert result["resource"]["type"] == "revision_request"
    assert repo.upserts[0]["resource_type"] == "revision_request"
    assert repo.upserts[0]["title"] == "修改意见"
    assert repo.upserts[0]["summary"] == "标题再狠一点"
    assert repo.upserts[0]["content_text"] == "标题再狠一点"
    assert repo.upserts[0]["content_json"] == {
        "feedback": "标题再狠一点",
        "target_resource_id": "generated-0",
    }
    assert repo.edges == [("generated-1", "generated-0", "feedback_on")]


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
        self.unreadable = unreadable or set()
        self.conn = None

    def add_edge(self, *, tenant_id, source_resource_id, target_resource_id, edge_type, weight=1.0):
        self.edges.append((source_resource_id, target_resource_id, edge_type, weight))

    def check_permission(self, resource_id, actor, permission="read", conn=None):
        if resource_id in self.unreadable:
            raise PermissionError("not readable")
        return True


def test_associate_links_semantic_neighbors_capped_and_weighted():
    """§0:对可读邻居建 semantically_related 边,weight=score,取前 max_edges 条。"""
    repo = AssocRepo()
    out = associate_ingested_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="new-1",
        neighbors=[
            {"resource_id": "n1", "score": 0.9},
            {"resource_id": "n2", "score": 0.7},
            {"resource_id": "n3", "score": 0.5},
            {"resource_id": "n4", "score": 0.4},  # 超过 max_edges=3,应被截断
        ],
        co_ingested_ids=["new-1"],
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
        neighbors=[
            {"resource_id": "new-1", "score": 0.99},  # 自身,跳过
            {"resource_id": "n1", "score": 0.8},
            {"resource_id": "n1", "score": 0.6},  # 重复,跳过
        ],
        co_ingested_ids=[],
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
        neighbors=[],
        co_ingested_ids=["new-1", "new-2", "new-3"],
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
        neighbors=[],
        co_ingested_ids=["new-1"],
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
        neighbors=[{"resource_id": "private", "score": 0.9}],
        co_ingested_ids=[],
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
        reference_resource_id="ref-1",
    )
    assert ok is True
    assert repo.edges == [("copy-1", "ref-1", "imitated_from", 1.0)]


def test_link_imitation_source_gated_and_guarded():
    """不可读范本不建边;空/自环范本返回 False。"""
    repo = AssocRepo(unreadable={"ref-private"})
    assert link_imitation_source(
        repo, tenant_id="default", actor_open_id="ou_user",
        copy_resource_id="copy-1", reference_resource_id="ref-private",
    ) is False
    assert link_imitation_source(
        repo, tenant_id="default", actor_open_id="ou_user",
        copy_resource_id="copy-1", reference_resource_id=" ",
    ) is False
    assert link_imitation_source(
        repo, tenant_id="default", actor_open_id="ou_user",
        copy_resource_id="copy-1", reference_resource_id="copy-1",
    ) is False
    assert repo.edges == []


def test_creation_memory_writes_real_resource_edges(migrated_conn, monkeypatch):
    from unittest.mock import MagicMock
    
    repo = ResourceRepository(migrated_conn)
    fake_graph = MagicMock()
    monkeypatch.setenv("XHS_FALKOR_URL", "redis://127.0.0.1:6379")
    monkeypatch.setenv("XHS_FALKOR_GRAPH", "xhs")
    monkeypatch.setattr(
        "data_foundation.falkor_client.FalkorResourceGraph.from_config",
        classmethod(lambda cls, cfg: fake_graph),
    )

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
        evidence=[{"resource_id": source.id, "summary": "清单型内容收藏高"}],
    )

    fake_graph.expand.return_value = (
        [
            {"id": result["resource"]["resource_id"], "title": "露营别乱买", "type": "generated_copy"},
            {"id": source.id, "title": "轻量露营样本", "type": "feishu_base_record"}
        ],
        [
            {"source": result["resource"]["resource_id"], "target": source.id, "edge_type": "derived_from", "weight": 1.0}
        ]
    )

    graph = expand_graph(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_ids=[result["resource"]["resource_id"]],
        hops=1,
        edge_types=["derived_from"],
    )

    assert {node.resource_id for node in graph.nodes} == {
        result["resource"]["resource_id"],
        source.id,
    }
    assert [(edge.source_resource_id, edge.target_resource_id, edge.edge_type) for edge in graph.edges] == [
        (result["resource"]["resource_id"], source.id, "derived_from")
    ]



def test_creation_memory_rolls_back_when_evidence_edge_is_invalid(migrated_conn):
    repo = ResourceRepository(migrated_conn)

    with pytest.raises((PermissionError, ValueError)):
        save_generated_copy_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            title="露营别乱买",
            body="这份清单够了",
            tags=["#露营"],
            evidence=[{"resource_id": "00000000-0000-0000-0000-000000000000", "summary": "不存在"}],
        )

    counts = repo.debug_counts()
    assert counts["resources"] == 0
    assert counts["resource_outbox"] == 0
