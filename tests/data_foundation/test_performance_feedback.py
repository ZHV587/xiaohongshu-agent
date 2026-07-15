from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from data_foundation.creation_memory import save_generated_copy_resource
from data_foundation.performance_feedback import (
    get_resource_performance_payload,
    save_performance_metric_resource,
)
from data_foundation.repositories.generated_copy import GeneratedCopyRepository
from data_foundation.repositories.resource import ResourceRepository
from data_foundation.writing_context import WritingContext


class _MemoryPreferenceRepository:
    def __init__(self):
        self.observations = {}
        self.state = None
        self.actor_locks = []

    def acquire_actor_lock(self, **kwargs):
        self.actor_locks.append((kwargs["tenant_id"], kwargs["actor_open_id"]))

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


def _save_published_copy(
    repo: ResourceRepository,
    *,
    actor_open_id: str,
    title: str,
    visibility: str = "team",
):
    source = repo.upsert_resource(
        tenant_id="default",
        actor_open_id=actor_open_id,
        resource_type="xhs_note",
        title=f"{title} 来源",
        content_text=f"{title} 的参考素材",
        visibility="team",
        owner_open_id=actor_open_id,
        outbox_requests=[],
    )
    saved = save_generated_copy_resource(
        repo,
        tenant_id="default",
        actor_open_id=actor_open_id,
        title=title,
        body="正文",
        tags=[],
        evidence=[
            {
                "resource_id": source.id,
                "resource_version": int(source.version),
            }
        ],
    )
    resource_id = saved["resource"]["resource_id"]
    resource_version = saved["resource"]["resource_version"]
    lifecycle = GeneratedCopyRepository(repo)
    finalized = lifecycle.finalize_for_schedule(
        tenant_id="default",
        actor_open_id=actor_open_id,
        resource_id=resource_id,
        target_resource_version=resource_version,
        expected_latest_resource_version=saved["resource"]["latest_resource_version"],
        expected_state_version=saved["resource"]["state_version"],
    )
    lifecycle.mark_published(
        tenant_id="default",
        actor_open_id=actor_open_id,
        resource_id=resource_id,
    )
    if visibility != "team":
        repo.conn.execute(
            "update resources set visibility = %s where tenant_id = 'default' and id = %s",
            (visibility, resource_id),
        )
        repo.conn.commit()
    return SimpleNamespace(
        id=resource_id,
        version=int(finalized.finalized_version),
    )


@dataclass
class RecordingRepository:
    upserts: list[dict[str, Any]]
    edges: list[tuple[str, str, str, float]]

    def __init__(self):
        self.conn = None
        self.account_repo = SimpleNamespace(
            get_resource_context=lambda **_kwargs: WritingContext()
        )
        self.upserts = []
        self.edges = []
        self.resources = {}
        self.target = {"type": "xhs_online_note", "version": 1, "visibility": "private", "owner_open_id": "ou_owner"}

    def unit_of_work(self):
        return nullcontext()

    def upsert_resource(self, **kwargs):
        self.upserts.append(kwargs)
        resource_id = kwargs.get("resource_id") or f"metric-{len(self.resources) + 1}"
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
            kwargs["weight"],
        ))

    def writable_resource_metadata(self, **kwargs):
        self.writable_kwargs = kwargs
        return self.target

    def get_resource_version(self, _tenant_id, actor_open_id, resource_id, resource_version):
        stored = self.resources.get((str(resource_id), int(resource_version)))
        if stored is not None:
            return stored
        return SimpleNamespace(
            id=resource_id,
            type=self.target["type"],
            title="目标文案",
            version=resource_version,
            content_text="目标正文",
            content_json={"title": "目标文案", "body": "目标正文", "tags": []},
            visibility=self.target["visibility"],
            owner_open_id=actor_open_id,
        )

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


def test_save_performance_metric_persists_metric_and_measured_by_edge(preference_memory):
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

    assert result["ok"] is True
    assert result["resource"] == {
        "resource_id": "metric-1",
        "type": "performance_metric",
        "title": "小红书效果 2026-06-20",
        "version": 1,
    }
    assert result["target_resource_version"] == 1
    normalized = result["normalized_performance"]
    assert result["score"] == normalized["score"]
    assert normalized["schema_version"] == 1
    assert normalized["raw_engagement_rate"] == pytest.approx(0.112)
    assert normalized["confidence"] >= 0.25
    assert normalized["learning_eligible"] is True
    assert repo.upserts[0]["resource_type"] == "performance_metric"
    assert repo.upserts[0]["title"] == "小红书效果 2026-06-20"
    assert repo.upserts[0]["summary"].startswith(f"score={result['score']:g} ")
    content = repo.upserts[0]["content_json"]
    assert content["target_resource_id"] == "generated-1"
    assert content["target_resource_version"] == 1
    assert content["metrics"] == {
        "likes": 120,
        "collects": 80,
        "comments": 12,
        "shares": 5,
        "views": 3000,
    }
    assert content["score"] == result["score"]
    assert content["normalized_performance"] == normalized
    assert content["resource_context"] == {
        "schema_version": 1,
        "account_id": None,
        "niche": None,
        "scope_key": "global",
    }
    assert content["published_at"] == "2026-06-20T08:00:00+00:00"
    assert content["channel"] == "xiaohongshu"
    assert content["note_url"] == "https://example.com/note/1"
    assert repo.upserts[0]["visibility"] == "private"
    assert repo.upserts[0]["owner_open_id"] == "ou_owner"
    assert [request.topic for request in repo.upserts[0]["outbox_requests"]] == ["knowledge_enrich"]
    assert [edge for edge in repo.edges if edge[2] == "measured_by"] == [
        ("generated-1", "metric-1", "measured_by", result["score"])
    ]
    assert len(preference_memory.observations) == 1


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
                "normalized_performance": {},
                "metrics": {"likes": 120, "collects": 80, "comments": 12, "shares": 5, "views": 3000},
                "channel": "xiaohongshu",
                "target_resource_version": None,
                "updated_at": "2026-06-20T08:00:00+00:00",
            }
        ],
    }


def test_performance_metric_writes_real_resource_edges(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    target = _save_published_copy(
        repo,
        actor_open_id="ou_user",
        title="露营别乱买",
    )

    saved = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        target_resource_id=target.id,
        target_resource_version=target.version,
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
    assert result["metrics"][0]["score"] == saved["score"]
    assert result["metrics"][0]["target_resource_version"] == target.version
    assert migrated_conn.execute(
        """
        select source_resource_id::text, source_resource_version,
               target_resource_id::text, target_resource_version, edge_type
        from resource_edges
        where tenant_id = 'default'
          and source_resource_id = %s and source_resource_version = %s
          and target_resource_id = %s and target_resource_version = %s
          and edge_type = 'measured_by'
        """,
        (
            target.id,
            target.version,
            saved["resource"]["resource_id"],
            saved["resource"]["version"],
        ),
    ).fetchone() == (
        target.id,
        target.version,
        saved["resource"]["resource_id"],
        saved["resource"]["version"],
        "measured_by",
    )


def test_non_owner_cannot_save_metric_for_private_target(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    target = _save_published_copy(
        repo,
        actor_open_id="ou_owner",
        title="私有文案",
        visibility="private",
    )
    baseline = repo.debug_counts()

    with pytest.raises(PermissionError):
        save_performance_metric_resource(
            repo,
            tenant_id="default",
            actor_open_id="ou_other",
            target_resource_id=target.id,
            target_resource_version=target.version,
            metrics={"likes": 10},
        )

    assert repo.debug_counts() == baseline


def test_get_resource_performance_filters_unreadable_metric(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    target = _save_published_copy(
        repo,
        actor_open_id="ou_owner",
        title="团队文案",
    )
    metric = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou_owner",
        target_resource_id=target.id,
        target_resource_version=target.version,
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
        self.conn = None
        self.account_repo = SimpleNamespace(
            get_resource_context=lambda **_kwargs: WritingContext()
        )
        self.metric_by_target: dict[str, str] = {}
        self.metric_content: dict[str, dict] = {}
        self.edges: set[tuple[str, str, str]] = set()
        self.edge_weight: dict[tuple[str, str, str], float] = {}
        self._seq = 0
        self.resource_versions: dict[str, int] = {}
        self.resources = {}
        self.target = {"type": "xhs_online_note", "version": 1, "visibility": "team", "owner_open_id": "ou_feishu"}

    def unit_of_work(self):
        return nullcontext()

    def writable_resource_metadata(self, **kwargs):
        return self.target

    def find_performance_metric_id(self, *, tenant_id, target_resource_id, conn=None):
        return self.metric_by_target.get(target_resource_id)

    def upsert_resource(self, **kwargs):
        if kwargs["resource_type"] == "writing_preference_profile":
            rid = kwargs["resource_id"]
            version = self.resource_versions.get(rid, 0) + 1
            self.resource_versions[rid] = version
            resource = SimpleNamespace(
                id=rid, type=kwargs["resource_type"], title=kwargs["title"], version=version,
                content_text=kwargs.get("content_text"),
                content_json=dict(kwargs.get("content_json") or {}),
                visibility=kwargs["visibility"], owner_open_id=kwargs["owner_open_id"],
            )
            self.resources[(rid, version)] = resource
            return resource
        rid = kwargs.get("resource_id")
        target = kwargs["content_json"]["target_resource_id"]
        if rid is None:
            self._seq += 1
            rid = f"metric-{self._seq}"
        self.metric_by_target[target] = rid
        self.metric_content[rid] = dict(kwargs["content_json"])
        version = self.resource_versions.get(rid, 0) + 1
        self.resource_versions[rid] = version
        resource = SimpleNamespace(
            id=rid, type=kwargs["resource_type"], title=kwargs["title"], version=version,
            content_text=kwargs.get("content_text"),
            content_json=dict(kwargs.get("content_json") or {}),
            visibility=kwargs["visibility"], owner_open_id=kwargs["owner_open_id"],
        )
        self.resources[(rid, version)] = resource
        return resource

    def add_edge(self, **kwargs):
        key = (kwargs["source_resource_id"], kwargs["target_resource_id"], kwargs["edge_type"])
        self.edges.add(key)
        self.edge_weight[key] = kwargs["weight"]

    def get_resource_version(self, _tenant_id, actor_open_id, resource_id, resource_version):
        stored = self.resources.get((str(resource_id), int(resource_version)))
        if stored is not None:
            return stored
        return SimpleNamespace(
            id=resource_id, type=self.target["type"], title="目标", version=resource_version,
            content_text="正文", content_json={"title": "目标", "body": "正文", "tags": []},
            visibility=self.target["visibility"], owner_open_id=actor_open_id,
        )


def test_save_performance_metric_is_idempotent_per_target(preference_memory):
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
    assert len([edge for edge in repo.edges if edge[2] == "measured_by"]) == 1
    assert len(preference_memory.observations) == 3
    only_rid = repo.metric_by_target["feishu-rec-1"]
    assert repo.metric_content[only_rid]["metrics"]["likes"] == 99999
    # metric 继承 target 的 visibility/owner(R7.1)
    assert repo.target["visibility"] == "team"


def test_two_targets_get_two_metrics(preference_memory):
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
    assert len([edge for edge in repo.edges if edge[2] == "measured_by"]) == 2
    assert len(preference_memory.observations) == 2
