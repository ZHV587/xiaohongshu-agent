from __future__ import annotations

from dataclasses import dataclass
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

from data_foundation.graph import expand_graph
from data_foundation.repository import ResourceRepository
from data_foundation.creation_memory import (
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
    assert repo.upserts[0]["outbox_topics"] == ["meili_index", "embedding_generate", "graph_ingest"]
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
        evidence=[{"resource_id": source.id, "summary": "清单型内容收藏高"}],
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
