from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from data_foundation.writing_teardown import save_writing_teardown_resource


class _Repo:
    def __init__(self, source=None):
        self.source = source
        self.exact_reads = []
        self.upserts = []
        self.edges = []
        self.resources = {}

    def unit_of_work(self):
        return nullcontext()

    def get_resource_for_knowledge(self, tenant, actor, resource_id, resource_version):
        self.exact_reads.append((tenant, actor, resource_id, resource_version))
        return self.source

    def upsert_resource(self, **kwargs):
        self.upserts.append(kwargs)
        resource_id = kwargs["resource_id"]
        previous = self.resources.get(resource_id)
        version = 1 if previous is None else previous.version + (
            previous.content_json != kwargs["content_json"]
        )
        resource = SimpleNamespace(
            id=resource_id,
            version=version,
            content_json=dict(kwargs["content_json"]),
            content_text=kwargs["content_text"],
        )
        self.resources[resource_id] = resource
        return resource

    def get_resource(self, _tenant, _actor, resource_id):
        return self.resources.get(resource_id)

    def add_edge(self, **kwargs):
        self.edges.append(kwargs)


def _source(*, visibility="team"):
    return SimpleNamespace(title="爆款原文", visibility=visibility)


def _save(repo, **overrides):
    values = {
        "tenant_id": "default",
        "actor_open_id": "ou_user",
        "source_resource_id": "source-1",
        "source_resource_version": 7,
        "niche": "职场成长",
        "hook": "工作三年后我才发现",
        "cta": "收藏后照着检查",
        "structure": ["反常识钩子", "亲历证据", "步骤清单"],
        "success_factors": ["具体数字", "低门槛行动"],
        "style_tags": ["克制", "口语"],
        "quality": 92,
    }
    values.update(overrides)
    return save_writing_teardown_resource(repo, **values)


def test_teardown_uses_exact_acl_snapshot_and_writes_versioned_edge():
    repo = _Repo(_source())

    result = _save(repo)

    assert repo.exact_reads == [("default", "ou_user", "source-1", 7)]
    assert repo.upserts[0]["resource_type"] == "writing_teardown"
    assert repo.upserts[0]["visibility"] == "team"
    assert repo.upserts[0]["content_json"]["source_resource_version"] == 7
    assert repo.upserts[0]["content_json"]["quality_score"] == 0.92
    assert repo.upserts[0]["content_json"]["raw_quality"] == 92.0
    assert len(repo.edges) == 1
    edge = repo.edges[0]
    assert edge["source_resource_id"] == result["resource_id"]
    assert edge["source_resource_version"] == 1
    assert edge["target_resource_id"] == "source-1"
    assert edge["target_resource_version"] == 7
    assert edge["edge_type"] == "teardown_of"
    assert edge["weight"] == 0.92
    assert edge["properties"] == {"analysis_kind": "writing_teardown"}
    assert result["source_resource_version"] == 7
    assert result["idempotent_replay"] is False


def test_private_source_produces_private_teardown_owned_by_actor():
    repo = _Repo(_source(visibility="private"))
    _save(repo)
    assert repo.upserts[0]["visibility"] == "private"
    assert repo.upserts[0]["owner_open_id"] == "ou_user"


def test_teardown_replay_reuses_stable_resource_and_exact_version():
    repo = _Repo(_source())

    first = _save(repo)
    replay = _save(repo)

    assert replay["resource_id"] == first["resource_id"]
    assert replay["resource_version"] == first["resource_version"] == 1
    assert replay["idempotent_replay"] is True
    assert repo.upserts[0]["mapping"]["external_type"] == "writing_teardown"


def test_teardown_fails_closed_when_exact_version_is_not_current_qualified_knowledge():
    repo = _Repo(None)
    with pytest.raises(PermissionError, match="not current qualified knowledge"):
        _save(repo, source_resource_version=8)
    assert repo.upserts == []
    assert repo.edges == []


def test_teardown_cannot_launder_a_readable_unqualified_candidate(migrated_conn):
    from data_foundation.repositories.resource import ResourceRepository

    repo = ResourceRepository(migrated_conn)
    candidate = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_type="generated_copy",
        title="未采纳候选",
        content_text="这只是模型候选。",
        visibility="team",
        owner_open_id="ou_user",
        outbox_requests=[],
    )

    with pytest.raises(PermissionError, match="not current qualified knowledge"):
        _save(
            repo,
            source_resource_id=candidate.id,
            source_resource_version=int(candidate.version),
        )
    assert migrated_conn.execute(
        "select count(*) from resources where type = 'writing_teardown'"
    ).fetchone()[0] == 0


def test_teardown_leaves_current_gate_when_exact_source_is_replaced(migrated_conn):
    from data_foundation.knowledge.service import KnowledgeService
    from data_foundation.repositories.resource import ResourceRepository

    repo = ResourceRepository(migrated_conn)
    source = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_type="feishu_doc",
        title="爆款原文",
        content_text="第一版原文",
        content_json={"title": "爆款原文", "hook_type": "反常识"},
        visibility="team",
        owner_open_id="ou_user",
        outbox_requests=[],
    )
    knowledge = KnowledgeService(migrated_conn)
    knowledge.enrich_exact_version(
        tenant_id="default", resource_id=str(source.id), resource_version=1
    )
    teardown = _save(
        repo,
        source_resource_id=str(source.id),
        source_resource_version=1,
    )
    qualified = knowledge.enrich_exact_version(
        tenant_id="default",
        resource_id=teardown["resource_id"],
        resource_version=teardown["resource_version"],
    )
    assert qualified.status == "qualified"
    assert migrated_conn.execute(
        """
        select 1 from current_knowledge_targets
        where tenant_id = 'default' and resource_id = %s and resource_version = %s
        """,
        (teardown["resource_id"], teardown["resource_version"]),
    ).fetchone() is not None

    replacement = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_user",
        resource_id=str(source.id),
        resource_type="feishu_doc",
        title="爆款原文第二版",
        content_text="第二版原文",
        content_json={"title": "爆款原文第二版", "hook_type": "痛点提问"},
        visibility="team",
        owner_open_id="ou_user",
        outbox_requests=[],
    )

    # The view is dependency-aware, so there is no exposure window while the source's
    # new exact version is still awaiting qualification.
    assert migrated_conn.execute(
        """
        select 1 from current_knowledge_targets
        where tenant_id = 'default' and resource_id = %s and resource_version = %s
        """,
        (teardown["resource_id"], teardown["resource_version"]),
    ).fetchone() is None
    knowledge.enrich_exact_version(
        tenant_id="default",
        resource_id=str(source.id),
        resource_version=int(replacement.version),
    )
    dependent_job = migrated_conn.execute(
        """
        select status from resource_outbox
        where tenant_id = 'default' and resource_id = %s
          and resource_version = %s and topic = 'knowledge_enrich'
        order by created_at desc, id desc limit 1
        """,
        (teardown["resource_id"], teardown["resource_version"]),
    ).fetchone()
    assert dependent_job is not None
    rejected = knowledge.enrich_exact_version(
        tenant_id="default",
        resource_id=teardown["resource_id"],
        resource_version=teardown["resource_version"],
    )
    assert rejected.status == "rejected"
    assert migrated_conn.execute(
        """
        select 1 from current_knowledge_targets
        where tenant_id = 'default' and resource_id = %s and resource_version = %s
        """,
        (teardown["resource_id"], teardown["resource_version"]),
    ).fetchone() is None


@pytest.mark.parametrize("bad_version", [None, 0, -1, True, 1.5, "1"])
def test_teardown_rejects_missing_or_non_exact_source_version(bad_version):
    repo = _Repo(_source())
    with pytest.raises(ValueError, match="source_resource_version"):
        _save(repo, source_resource_version=bad_version)
    assert repo.exact_reads == []
