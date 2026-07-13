from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from data_foundation.performance_feedback import (
    get_resource_performance_payload,
    save_performance_metric_resource,
)
from data_foundation.repositories.resource import ResourceRepository


@dataclass
class RecordingRepository:
    upserts: list[dict[str, Any]]
    edges: list[tuple[str, str, str, float]]

    def __init__(self):
        self.upserts = []
        self.edges = []
        self.target = {"type": "xhs_online_note", "version": 1, "visibility": "private", "owner_open_id": "ou_owner"}

    def unit_of_work(self):
        return nullcontext()

    def upsert_resource(self, **kwargs):
        self.upserts.append(kwargs)
        return SimpleNamespace(
            id=f"metric-{len(self.upserts)}",
            type=kwargs["resource_type"],
            title=kwargs["title"],
            version=1,
        )

    def add_edge(self, **kwargs):
        self.edges.append((
            kwargs["source_resource_id"],
            kwargs["target_resource_id"],
            kwargs["edge_type"],
            kwargs["weight"],
        ))

    def writable_resource_metadata(self, **kwargs):
        self.writable_kwargs = kwargs
        return self.target

    def find_performance_metric_id(self, **kwargs):
        return getattr(self, "existing_metric_id", None)

    def performance_rows(self, **kwargs):
        return [
            {
                "resource_id": "metric-1",
                "title": "小红书效果 2026-06-20",
                "content_json": {
                    "metrics": {"likes": 120, "collects": 80, "comments": 12, "shares": 5, "views": 3000},
                    "score": 0.112,
                    "channel": "xiaohongshu",
                    "target_resource_version": None,
                },
                "weight": 0.112,
                "updated_at": SimpleNamespace(isoformat=lambda: "2026-06-20T08:00:00+00:00"),
            }
        ]


def test_save_performance_metric_persists_metric_and_measured_by_edge():
    repo = RecordingRepository()

    result = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        target_resource_id="generated-1",
        metrics={"likes": 120, "collects": 80, "comments": 12, "shares": 5, "views": 3000},
        published_at="2026-06-20T08:00:00+00:00",
        channel="xiaohongshu",
        note_url="https://example.com/note/1",
    )

    assert result == {
        "ok": True,
        "resource": {
            "resource_id": "metric-1",
            "type": "performance_metric",
            "title": "小红书效果 2026-06-20",
            "version": 1,
        },
        "score": 0.112,
        "target_resource_version": 1,
    }
    assert repo.upserts[0]["resource_type"] == "performance_metric"
    assert repo.upserts[0]["title"] == "小红书效果 2026-06-20"
    assert repo.upserts[0]["summary"] == "score=0.112 likes=120 collects=80 comments=12 shares=5 views=3000"
    assert repo.upserts[0]["content_json"] == {
        "target_resource_id": "generated-1",
        "target_resource_version": 1,
        "metrics": {"likes": 120, "collects": 80, "comments": 12, "shares": 5, "views": 3000},
        "score": 0.112,
        "published_at": "2026-06-20T08:00:00+00:00",
        "channel": "xiaohongshu",
        "note_url": "https://example.com/note/1",
    }
    assert repo.upserts[0]["visibility"] == "private"
    assert repo.upserts[0]["owner_open_id"] == "ou_owner"
    assert [request.topic for request in repo.upserts[0]["outbox_requests"]] == ["meili_index", "graph_ingest"]
    assert repo.edges == [("generated-1", "metric-1", "measured_by", 0.112)]


def test_save_performance_metric_validates_target_and_metrics():
    repo = RecordingRepository()

    with pytest.raises(ValueError, match="target_resource_id"):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            target_resource_id=" ",
            metrics={"likes": 1},
        )
    with pytest.raises(ValueError, match="metrics"):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            target_resource_id="generated-1",
            metrics={"unknown": 1},
        )
    with pytest.raises(ValueError, match="non-negative"):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            target_resource_id="generated-1",
            metrics={"likes": -1},
        )
    with pytest.raises(ValueError, match="finite non-negative"):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            target_resource_id="generated-1",
            metrics={"likes": "NaN"},
        )
    with pytest.raises(ValueError, match="finite non-negative"):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_user",
            target_resource_id="generated-1",
            metrics={"likes": "1万"},
        )


def test_get_resource_performance_payload_returns_metrics():
    repo = RecordingRepository()

    result = get_resource_performance_payload(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id="generated-1",
    )

    assert result == {
        "ok": True,
        "target_resource_id": "generated-1",
        "metrics": [
            {
                "resource_id": "metric-1",
                "title": "小红书效果 2026-06-20",
                "score": 0.112,
                "metrics": {"likes": 120, "collects": 80, "comments": 12, "shares": 5, "views": 3000},
                "channel": "xiaohongshu",
                "target_resource_version": None,
                "updated_at": "2026-06-20T08:00:00+00:00",
            }
        ],
    }


def test_performance_metric_writes_real_resource_edges(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    target = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_type="generated_copy",
        title="露营别乱买",
        summary="轻量露营",
        content_text="正文",
        content_json={},
        visibility="team",
        owner_open_id="ou_user",
    )

    saved = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        target_resource_id=target.id,
        metrics={"likes": 10, "collects": 5, "views": 100},
        published_at="2026-06-20T08:00:00+00:00",
    )
    result = get_resource_performance_payload(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=target.id,
    )

    assert result["metrics"][0]["resource_id"] == saved["resource"]["resource_id"]
    assert result["metrics"][0]["score"] == 0.2


def test_non_owner_cannot_save_metric_for_private_target(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    target = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="generated_copy",
        title="私有文案",
        summary=None,
        content_text="正文",
        content_json={},
        visibility="private",
        owner_open_id="ou_owner",
    )

    with pytest.raises(PermissionError):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_other",
            target_resource_id=target.id,
            metrics={"likes": 10},
        )

    counts = repo.debug_counts()
    assert counts["resources"] == 1
    assert counts["resource_outbox"] == 0


def test_get_resource_performance_filters_unreadable_metric(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    target = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="generated_copy",
        title="团队文案",
        summary=None,
        content_text="正文",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )
    metric = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_owner",
        target_resource_id=target.id,
        metrics={"likes": 10},
    )
    repo.conn.execute(
        "update resources set visibility = 'private', owner_open_id = 'ou_owner' where id = %s",
        (metric["resource"]["resource_id"],),
    )
    repo.conn.commit()

    result = get_resource_performance_payload(
        repo,
        tenant_id="default",
        actor_open_id="ou_other",
        resource_id=target.id,
    )

    assert result["metrics"] == []


class _StatefulRepo:
    """模拟真实幂等:按 target 复用既有 metric,边按 (source,target,edge_type) 去重。"""

    def __init__(self):
        self.metric_by_target: dict[str, str] = {}
        self.metric_content: dict[str, dict] = {}
        self.edges: set[tuple[str, str, str]] = set()
        self.edge_weight: dict[tuple[str, str, str], float] = {}
        self._seq = 0
        self.target = {"type": "xhs_online_note", "version": 1, "visibility": "team", "owner_open_id": "ou_feishu"}

    def unit_of_work(self):
        return nullcontext()

    def writable_resource_metadata(self, **kwargs):
        return self.target

    def find_performance_metric_id(self, *, tenant_id, target_resource_id, conn=None):
        return self.metric_by_target.get(target_resource_id)

    def upsert_resource(self, **kwargs):
        rid = kwargs.get("resource_id")
        target = kwargs["content_json"]["target_resource_id"]
        if rid is None:
            self._seq += 1
            rid = f"metric-{self._seq}"
        self.metric_by_target[target] = rid
        self.metric_content[rid] = dict(kwargs["content_json"])
        return SimpleNamespace(id=rid, type=kwargs["resource_type"], title=kwargs["title"], version=1)

    def add_edge(self, **kwargs):
        key = (kwargs["source_resource_id"], kwargs["target_resource_id"], kwargs["edge_type"])
        self.edges.add(key)
        self.edge_weight[key] = kwargs["weight"]


def test_save_performance_metric_is_idempotent_per_target():
    repo = _StatefulRepo()
    for likes in (100, 5000, 99999):  # 同一 target 反复回填,数值变化
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_feishu",
            target_resource_id="feishu-rec-1",
            metrics={"likes": likes, "collects": 10},
        )
    # 幂等:恰 1 条 metric、1 条边,末次数值覆盖
    assert len(repo.metric_by_target) == 1
    assert len([rid for rid in repo.metric_content]) == 1
    assert len(repo.edges) == 1
    only_rid = repo.metric_by_target["feishu-rec-1"]
    assert repo.metric_content[only_rid]["metrics"]["likes"] == 99999
    # metric 继承 target 的 visibility/owner(R7.1)
    assert repo.target["visibility"] == "team"


def test_two_targets_get_two_metrics():
    repo = _StatefulRepo()
    save_performance_metric_resource(
        repo, tenant_id="default", actor_open_id="ou_feishu",
        target_resource_id="rec-1", metrics={"likes": 1},
    )
    save_performance_metric_resource(
        repo, tenant_id="default", actor_open_id="ou_feishu",
        target_resource_id="rec-2", metrics={"likes": 2},
    )
    assert len(repo.metric_by_target) == 2
    assert len(repo.edges) == 2
