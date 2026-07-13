from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from data_foundation.preference_learning import (
    ExactResourceVersion,
    KnowledgeAsset,
    PreferenceLearningService,
    build_preference_observation,
    canonical_json,
    preference_event_key,
    rebuild_preference_profile,
    synthesize_pattern_candidates,
)
from tools.runtime_identity import identity_config


def _snapshot(title: str, body: str = "正文", **extra):
    return {"title": title, "body": body, "tags": ["#内容"], **extra}


def _observation(event_type: str, resource_id: str, version: int, **snapshot):
    return build_preference_observation(
        event_type=event_type,
        source=ExactResourceVersion(resource_id, version),
        source_event_id=f"event-{event_type}-{resource_id}-{version}",
        snapshot=snapshot or _snapshot("3 个方法"),
        event_payload={"score": 0.8, "metrics": {"likes": 20}}
        if event_type == "metric"
        else {},
    )


def test_preference_event_key_is_exact_and_retry_idempotent():
    source = ExactResourceVersion("copy-1", 2)
    first = preference_event_key(
        event_type="adopted",
        source=source,
        source_event_id="event-1",
        event_payload={"attempt": 1},
    )
    replay = preference_event_key(
        event_type="adopted",
        source=source,
        source_event_id="event-1",
        event_payload={"attempt": 999},
    )
    assert first == replay
    assert first != preference_event_key(
        event_type="adopted", source=source, source_event_id="event-2"
    )
    assert first != preference_event_key(
        event_type="adopted",
        source=ExactResourceVersion("copy-1", 3),
        source_event_id="event-1",
    )


def test_revision_observation_compares_two_exact_snapshots():
    observation = build_preference_observation(
        event_type="revision_saved",
        source=ExactResourceVersion("copy-1", 2),
        source_event_id="revision-event",
        snapshot=_snapshot("短标题", "第一段\n\n第二段", tags=["#新标签"]),
        previous_snapshot=_snapshot(
            "这是一个明显更长的旧标题", "只有一段", tags=["#旧标签"]
        ),
    )
    signal = observation.payload["signal"]
    assert observation.event_type == "revision"
    assert signal["title_length_delta"] < 0
    assert signal["paragraph_count_delta"] == 1
    assert signal["tags_added"] == ["#新标签"]
    assert signal["tags_removed"] == ["#旧标签"]


def test_profile_rebuild_is_deterministic_and_deduplicates_event_keys():
    adopted = _observation(
        "adopted", "copy-1", 1, **_snapshot("3 个方法", hook_type="数字清单")
    )
    published = _observation(
        "published", "copy-2", 4, **_snapshot("别再踩坑", hook_type="避坑警示")
    )
    metric = _observation(
        "metric", "copy-2", 4, **_snapshot("别再踩坑", hook_type="避坑警示")
    )
    first = rebuild_preference_profile("ou-owner", [adopted, published, metric, metric])
    second = rebuild_preference_profile("ou-owner", [metric, adopted, published])
    assert canonical_json(first) == canonical_json(second)
    assert first["observation_count"] == 3
    assert first["source_count"] == 2
    assert first["event_counts"] == {
        "adopted": 1,
        "finalized": 0,
        "published": 1,
        "metric": 1,
        "revision": 0,
        "feedback": 0,
    }
    assert first["preferences"]["hook_type"][0]["value"] == "避坑警示"
    assert first["sources"] == [
        {"resource_id": "copy-1", "resource_version": 1},
        {"resource_id": "copy-2", "resource_version": 4},
    ]


def test_explicit_feedback_becomes_private_traits_not_fake_writing_lengths():
    observation = build_preference_observation(
        event_type="revision_request",
        source=ExactResourceVersion("feedback-1", 1),
        source_event_id="feedback:feedback-1:v1",
        snapshot={"title": "修改意见", "content_text": "短一点，别这么有 AI 味"},
        event_payload={
            "feedback": "短一点，别这么有 AI 味，多写我的真实经历",
            "feedback_type": "revision_request",
        },
    )
    assert observation.event_type == "feedback"
    assert observation.payload["features"] == {}
    profile = rebuild_preference_profile("ou-owner", [observation])
    assert profile["preferred_ranges"] == {}
    assert profile["explicit_feedback_traits"] == [
        {"trait": "增强个人感", "count": 1},
        {"trait": "更简洁", "count": 1},
        {"trait": "降低AI腔", "count": 1},
    ]


def _asset(
    resource_id: str,
    family_id: str,
    *,
    version: int = 1,
    visibility: str = "team",
    quality: float = 0.5,
    normalized_hash: str | None = None,
):
    return KnowledgeAsset(
        source=ExactResourceVersion(resource_id, version),
        duplicate_family_id=family_id,
        visibility=visibility,
        quality_score=quality,
        normalized_hash=normalized_hash,
        content_json={"title": "标题", "hook_type": "反常识"},
    )


def test_pattern_threshold_counts_independent_families_not_duplicate_copies():
    same_family_copies = [
        _asset("copy-1", "family-1", version=1),
        _asset("copy-1", "family-1", version=2, quality=0.9),
        _asset("copy-duplicate", "family-1", version=1),
    ]
    assert synthesize_pattern_candidates(same_family_copies) == []

    candidates = synthesize_pattern_candidates(
        same_family_copies
        + [
            _asset("copy-2", "family-2"),
            _asset("copy-3", "family-3", visibility="private"),
        ]
    )
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.dimension == "hook_type"
    assert candidate.value == "反常识"
    assert candidate.source_family_ids == ("family-1", "family-2", "family-3")
    assert candidate.sources[0].source == ExactResourceVersion("copy-1", 2)
    assert candidate.visibility == "private"


def test_pattern_threshold_collapses_equal_hashes_even_if_old_acl_split_families():
    assets = [
        _asset("copy-1", "family-1", normalized_hash="a" * 64),
        _asset("copy-2", "family-2", normalized_hash="a" * 64),
        _asset("copy-3", "family-3", normalized_hash="b" * 64),
    ]

    assert synthesize_pattern_candidates(assets) == []


def test_pattern_threshold_collapses_distinct_versions_of_same_stable_resource():
    assets = [
        _asset("copy-1", "family-1", version=1, normalized_hash="a" * 64),
        _asset("copy-1", "family-2", version=2, normalized_hash="b" * 64),
        _asset("copy-1", "family-3", version=3, normalized_hash="c" * 64),
    ]

    assert synthesize_pattern_candidates(assets) == []


def test_pattern_repository_only_reads_current_qualified_version(migrated_conn):
    from data_foundation.knowledge.service import KnowledgeService
    from data_foundation.repositories.preference import PreferenceRepository
    from data_foundation.repositories.resource import ResourceRepository

    resources = ResourceRepository(migrated_conn)
    first = resources.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="ou-owner",
        resource_type="feishu_doc",
        title="第一版",
        content_text="第一版正文，采用反常识开头",
        content_json={"title": "第一版", "hook_type": "反常识"},
        owner_open_id="ou-owner",
        outbox_requests=[],
    )
    knowledge = KnowledgeService(migrated_conn)
    knowledge.enrich_exact_version(
        tenant_id="tenant-a", resource_id=str(first.id), resource_version=1
    )
    second = resources.upsert_resource(
        tenant_id="tenant-a",
        actor_open_id="ou-owner",
        resource_id=str(first.id),
        resource_type="feishu_doc",
        title="第二版",
        content_text="第二版正文，换成痛点提问开头并重写全文",
        content_json={"title": "第二版", "hook_type": "痛点提问"},
        owner_open_id="ou-owner",
        outbox_requests=[],
    )
    knowledge.enrich_exact_version(
        tenant_id="tenant-a",
        resource_id=str(second.id),
        resource_version=int(second.version),
    )

    assets = PreferenceRepository(migrated_conn).list_eligible_assets(
        tenant_id="tenant-a", actor_open_id="ou-owner"
    )
    exact_versions = [
        asset.source.resource_version
        for asset in assets
        if asset.source.resource_id == str(first.id)
    ]
    assert exact_versions == [2]


def test_synthesis_completion_replay_is_idempotent_but_old_revision_is_rejected(
    migrated_conn,
):
    from data_foundation.repositories.preference import PreferenceRepository

    migrated_conn.execute(
        """
        insert into preference_synthesis_states (
          tenant_id, owner_open_id, requested_revision, completed_revision
        ) values ('tenant-a', 'ou-idempotent', 3, 0)
        """
    )
    repository = PreferenceRepository(migrated_conn)

    assert repository.mark_synthesis_completed(
        tenant_id="tenant-a",
        actor_open_id="ou-idempotent",
        requested_revision=3,
    ) is True
    # Simulates a crash after the completion transaction committed but before the
    # outbox row was acknowledged.
    assert repository.mark_synthesis_completed(
        tenant_id="tenant-a",
        actor_open_id="ou-idempotent",
        requested_revision=3,
    ) is True

    migrated_conn.execute(
        """
        update preference_synthesis_states
        set requested_revision = 4
        where tenant_id = 'tenant-a' and owner_open_id = 'ou-idempotent'
        """
    )
    assert repository.mark_synthesis_completed(
        tenant_id="tenant-a",
        actor_open_id="ou-idempotent",
        requested_revision=3,
    ) is False
    assert repository.mark_synthesis_completed(
        tenant_id="tenant-a",
        actor_open_id="ou-idempotent",
        requested_revision=4,
    ) is True


def test_pattern_inputs_follow_owner_team_and_explicit_permission_acl(migrated_conn):
    from data_foundation.knowledge.service import KnowledgeService
    from data_foundation.repositories.preference import PreferenceRepository
    from data_foundation.repositories.resource import ResourceRepository

    resources = ResourceRepository(migrated_conn)
    knowledge = KnowledgeService(migrated_conn)

    def _qualified(*, tenant_id, owner, visibility, title):
        resource = resources.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=owner,
            resource_type="feishu_doc",
            title=title,
            content_text=f"{title}的正文",
            content_json={"title": title, "hook_type": "反常识"},
            visibility=visibility,
            owner_open_id=owner,
            outbox_requests=[],
        )
        result = knowledge.enrich_exact_version(
            tenant_id=tenant_id,
            resource_id=str(resource.id),
            resource_version=int(resource.version),
        )
        assert result.status == "qualified"
        return resource

    owned = _qualified(
        tenant_id="tenant-a", owner="ou-viewer", visibility="private", title="本人私有"
    )
    team = _qualified(
        tenant_id="tenant-a", owner="ou-source", visibility="team", title="团队素材"
    )
    granted = {
        permission: _qualified(
            tenant_id="tenant-a",
            owner="ou-source",
            visibility="private",
            title=f"显式{permission}授权",
        )
        for permission in ("read", "write", "admin")
    }
    denied = _qualified(
        tenant_id="tenant-a", owner="ou-source", visibility="private", title="未授权私有"
    )
    stale_visibility = _qualified(
        tenant_id="tenant-a", owner="ou-source", visibility="team", title="资格快照仍是团队"
    )
    unknown_visibility = _qualified(
        tenant_id="tenant-a", owner="ou-source", visibility="team", title="未知可见性"
    )
    inactive = _qualified(
        tenant_id="tenant-a", owner="ou-source", visibility="team", title="已撤销素材"
    )
    migrated_conn.execute(
        "update resources set visibility = 'private' where tenant_id = %s and id = %s",
        ("tenant-a", stale_visibility.id),
    )
    migrated_conn.execute(
        "update resources set visibility = 'future_visibility' where tenant_id = %s and id = %s",
        ("tenant-a", unknown_visibility.id),
    )
    migrated_conn.execute(
        "update resources set status = 'inactive' where tenant_id = %s and id = %s",
        ("tenant-a", inactive.id),
    )
    other_tenant = _qualified(
        tenant_id="tenant-b", owner="ou-source", visibility="private", title="其他租户"
    )
    for permission, resource in granted.items():
        migrated_conn.execute(
            """
            insert into resource_permissions (
              tenant_id, resource_id, subject_type, subject_id, permission
            ) values (%s, %s, 'user', %s, %s)
            """,
            ("tenant-a", resource.id, "ou-viewer", permission),
        )
    migrated_conn.execute(
        """
        insert into resource_permissions (
          tenant_id, resource_id, subject_type, subject_id, permission
        ) values (%s, %s, 'user', %s, 'read')
        """,
        ("tenant-b", other_tenant.id, "ou-viewer"),
    )

    visible_ids = {
        asset.source.resource_id
        for asset in PreferenceRepository(migrated_conn).list_eligible_assets(
            tenant_id="tenant-a", actor_open_id="ou-viewer"
        )
    }
    expected = {
        str(owned.id),
        str(team.id),
        *(str(resource.id) for resource in granted.values()),
    }
    assert expected <= visible_ids
    assert str(denied.id) not in visible_ids
    assert str(stale_visibility.id) not in visible_ids
    assert str(unknown_visibility.id) not in visible_ids
    assert str(inactive.id) not in visible_ids
    assert str(other_tenant.id) not in visible_ids


class _FakePreferenceRepository:
    def __init__(self, assets=None):
        self.observations = {}
        self.state = None
        self.assets = list(assets or [])
        self.actor_locks = []
        self.patterns = []

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

    def list_eligible_assets(self, **_kwargs):
        return list(self.assets)

    def list_actor_patterns(self, **_kwargs):
        return list(self.patterns)

    def mark_synthesis_completed(self, **_kwargs):
        return True


class _FakeResourceRepository:
    def __init__(self):
        self.snapshots = {}
        self.latest = {}
        self.writes = []
        self.edges = {}

    def unit_of_work(self):
        return nullcontext()

    def add_snapshot(self, resource_id, version, *, visibility="private", **content):
        resource = SimpleNamespace(
            id=resource_id,
            version=version,
            type="generated_copy",
            title=content.get("title", ""),
            content_text=content.get("body", ""),
            content_json=dict(content),
            visibility=visibility,
        )
        self.snapshots[(resource_id, version)] = resource
        return resource

    def get_resource_version(self, _tenant_id, _actor_open_id, resource_id, resource_version):
        return self.snapshots.get((resource_id, resource_version))

    def upsert_resource(self, **kwargs):
        resource_id = kwargs["resource_id"]
        fingerprint = canonical_json(
            {
                "type": kwargs["resource_type"],
                "title": kwargs["title"],
                "summary": kwargs.get("summary"),
                "text": kwargs.get("content_text"),
                "json": kwargs.get("content_json"),
                "visibility": kwargs.get("visibility"),
                "owner": kwargs.get("owner_open_id"),
            }
        )
        current = self.latest.get(resource_id)
        if current and current["fingerprint"] == fingerprint:
            return current["resource"]
        version = 1 if current is None else current["resource"].version + 1
        resource = SimpleNamespace(
            id=resource_id,
            version=version,
            type=kwargs["resource_type"],
            title=kwargs["title"],
            content_text=kwargs.get("content_text"),
            content_json=dict(kwargs.get("content_json") or {}),
            visibility=kwargs["visibility"],
        )
        self.latest[resource_id] = {"fingerprint": fingerprint, "resource": resource}
        self.snapshots[(resource_id, version)] = resource
        self.writes.append(dict(kwargs))
        return resource

    def add_edge(self, **kwargs):
        key = (
            kwargs["source_resource_id"],
            kwargs["source_resource_version"],
            kwargs["target_resource_id"],
            kwargs["target_resource_version"],
            kwargs["edge_type"],
        )
        self.edges[key] = dict(kwargs)


def test_service_rebuilds_private_profile_resource_and_exact_learned_from_edges():
    resources = _FakeResourceRepository()
    resources.add_snapshot(
        "copy-1",
        2,
        title="3 个写法",
        body="正文",
        tags=["#方法"],
        hook_type="数字清单",
    )
    observations = _FakePreferenceRepository()
    service = PreferenceLearningService(resources, observations)

    first = service.record_exact_event(
        tenant_id="tenant-a",
        actor_open_id="ou-owner",
        event_type="adopted",
        source_resource_id="copy-1",
        source_resource_version=2,
        source_event_id="event-adopt-1",
    )
    replay = service.record_exact_event(
        tenant_id="tenant-a",
        actor_open_id="ou-owner",
        event_type="adopted",
        source_resource_id="copy-1",
        source_resource_version=2,
        source_event_id="event-adopt-1",
    )

    assert first["inserted"] is True and replay["inserted"] is False
    assert first["profile"]["resource_id"] == replay["profile"]["resource_id"]
    assert first["profile"]["resource_version"] == replay["profile"]["resource_version"] == 1
    profile_write = next(
        write for write in resources.writes if write["resource_type"] == "writing_preference_profile"
    )
    assert profile_write["visibility"] == "private"
    assert profile_write["owner_open_id"] == "ou-owner"
    assert profile_write["outbox_requests"] == []
    assert observations.state["input_digest"] == first["profile"]["input_digest"]
    learned_edges = [edge for edge in resources.edges.values() if edge["edge_type"] == "learned_from"]
    assert len(learned_edges) == 1
    assert learned_edges[0]["source_resource_version"] == 1
    assert learned_edges[0]["target_resource_id"] == "copy-1"
    assert learned_edges[0]["target_resource_version"] == 2
    assert service.get_profile(tenant_id="tenant-a", actor_open_id="ou-owner")["profile"][
        "resource_version"
    ] == 1


def test_service_saves_only_cross_family_patterns_with_exact_authority_and_edges():
    assets = [
        _asset("copy-1", "family-1"),
        _asset("copy-1-duplicate", "family-1"),
        _asset("copy-2", "family-2"),
        _asset("copy-3", "family-3", visibility="private"),
    ]
    resources = _FakeResourceRepository()
    service = PreferenceLearningService(resources, _FakePreferenceRepository(assets))
    saved = service.synthesize_patterns(
        tenant_id="tenant-a", actor_open_id="ou-owner"
    )

    assert len(saved) == 1
    assert saved[0]["source_family_count"] == 3
    assert saved[0]["visibility"] == "private"
    pattern_write = next(
        write for write in resources.writes if write["resource_type"] == "writing_pattern"
    )
    payload = pattern_write["content_json"]
    assert payload["source_family_ids"] == ["family-1", "family-2", "family-3"]
    assert payload["synthesis_threshold"] == 3
    assert len(payload["source_authority"]) == 3
    assert pattern_write["outbox_requests"]
    exact_edges = [edge for edge in resources.edges.values() if edge["edge_type"] == "synthesized_from"]
    assert len(exact_edges) == 3
    assert {edge["target_resource_id"] for edge in exact_edges} == {
        "copy-1",
        "copy-2",
        "copy-3",
    }


def test_service_retires_pattern_when_current_acl_inputs_no_longer_support_it():
    preferences = _FakePreferenceRepository(
        [
            _asset("copy-1", "family-1"),
            _asset("copy-2", "family-2"),
            _asset("copy-3", "family-3"),
        ]
    )
    resources = _FakeResourceRepository()
    service = PreferenceLearningService(resources, preferences)
    first = service.synthesize_patterns(
        tenant_id="tenant-a", actor_open_id="ou-owner"
    )[0]
    current = resources.latest[first["resource_id"]]["resource"]
    preferences.patterns = [{
        "resource_id": first["resource_id"],
        "resource_version": current.version,
        "status": "active",
        "title": current.title,
        "summary": "由 3 个独立素材家族确定性归纳",
        "content_text": current.content_text,
        "content_json": current.content_json,
        "visibility": current.visibility,
        "owner_open_id": "ou-owner",
    }]
    preferences.assets = []

    retired = service.synthesize_patterns(
        tenant_id="tenant-a", actor_open_id="ou-owner"
    )

    assert retired[0]["status"] == "retired"
    retirement_write = resources.writes[-1]
    assert retirement_write["resource_id"] == first["resource_id"]
    assert retirement_write["status"] == "inactive"
    assert retirement_write["content_json"]["retired_reason"]


def test_get_writing_profile_tool_routes_current_actor_to_private_state(monkeypatch):
    from data_foundation import preference_learning
    from data_foundation import tools as df_tools

    captured = {}
    repo = object()

    class _RepoContext:
        def __enter__(self):
            return repo

        def __exit__(self, *_args):
            return False

    class _Service:
        def __init__(self, repo_arg):
            captured["repo"] = repo_arg

        def get_profile(self, **kwargs):
            captured.update(kwargs)
            return {"ok": True, "profile": None}

    monkeypatch.setattr(df_tools, "_repository", _RepoContext)
    monkeypatch.setattr(preference_learning, "PreferenceLearningService", _Service)
    result = df_tools.get_writing_profile.func(config=identity_config("ou-owner"))

    assert result == {"ok": True, "profile": None}
    assert captured == {
        "repo": repo,
        "tenant_id": "default",
        "actor_open_id": "ou-owner",
    }
    assert df_tools.get_writing_profile in df_tools.data_foundation_tools


def test_real_lifecycle_feedback_and_metrics_automatically_rebuild_one_exact_profile(
    migrated_conn,
):
    from data_foundation.creation_memory import save_user_feedback_resource
    from data_foundation.performance_feedback import save_performance_metric_resource
    from data_foundation.repositories.generated_copy import GeneratedCopyRepository
    from data_foundation.repositories.resource import ResourceRepository

    repo = ResourceRepository(migrated_conn)
    copy = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_type="generated_copy",
        title="初稿标题",
        content_text="初稿正文",
        content_json={
            "title": "初稿标题",
            "body": "初稿正文",
            "tags": ["#初稿"],
            "variant_label": "A",
        },
        visibility="team",
        owner_open_id="ou-owner",
        outbox_requests=[],
    )
    lifecycle = GeneratedCopyRepository(repo)
    initial = lifecycle.initialize_candidate(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=str(copy.id),
        resource_version=int(copy.version),
        label="A",
    )
    revised = lifecycle.save_revision(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=str(copy.id),
        expected_resource_version=initial.latest_resource_version,
        expected_state_version=initial.state_version,
        title="别再写这种长标题",
        body="第一段\n\n第二段",
        tags=["#避坑"],
        label="A",
    )
    adopted = lifecycle.adopt_version(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=str(copy.id),
        resource_version=revised.selected_version,
        expected_state_version=revised.state_version,
    )
    finalized = lifecycle.finalize_for_schedule(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=str(copy.id),
        target_resource_version=adopted.selected_version,
        expected_latest_resource_version=adopted.latest_resource_version,
        expected_state_version=adopted.state_version,
    )
    published = lifecycle.mark_published(
        tenant_id="default", actor_open_id="ou-owner", resource_id=str(copy.id)
    )
    assert published.published_version == finalized.finalized_version

    metric = save_performance_metric_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou-owner",
        target_resource_id=str(copy.id),
        target_resource_version=published.published_version,
        metrics={"views": 1000, "likes": 120, "collects": 30},
    )
    feedback = save_user_feedback_resource(
        repo,
        tenant_id="default",
        actor_open_id="ou-owner",
        feedback="再短一点，少点 AI 味，多写我的经历",
        target_resource_id=str(copy.id),
        target_resource_version=published.published_version,
        feedback_type="revision_request",
    )

    observations = migrated_conn.execute(
        """
        select observation_type, resource_id::text, resource_version, idempotency_key
        from preference_observations
        where tenant_id = 'default' and owner_open_id = 'ou-owner'
        order by observation_type
        """
    ).fetchall()
    assert [row["observation_type"] for row in observations] == [
        "adopted",
        "feedback",
        "finalized",
        "metric",
        "published",
        "revision",
    ]
    state = migrated_conn.execute(
        """
        select profile_resource_id::text, profile_resource_version,
               input_digest, observation_count
        from writing_profile_states
        where tenant_id = 'default' and owner_open_id = 'ou-owner'
        """
    ).fetchone()
    assert state["observation_count"] == 6
    profile = migrated_conn.execute(
        """
        select r.type, r.visibility, r.owner_open_id, rv.content_json
        from resources r
        join resource_versions rv
          on rv.tenant_id = r.tenant_id and rv.resource_id = r.id
         and rv.version = %s
        where r.tenant_id = 'default' and r.id = %s
        """,
        (state["profile_resource_version"], state["profile_resource_id"]),
    ).fetchone()
    assert (profile["type"], profile["visibility"], profile["owner_open_id"]) == (
        "writing_preference_profile",
        "private",
        "ou-owner",
    )
    assert profile["content_json"]["explicit_feedback_traits"]

    exact_targets = {
        (row["target_resource_id"], row["target_resource_version"])
        for row in migrated_conn.execute(
            """
            select target_resource_id::text, target_resource_version
            from resource_edges
            where tenant_id = 'default'
              and source_resource_id = %s
              and source_resource_version = %s
              and edge_type = 'learned_from'
            """,
            (state["profile_resource_id"], state["profile_resource_version"]),
        ).fetchall()
    }
    assert (str(copy.id), 1) in exact_targets  # revision base
    assert (str(copy.id), int(published.published_version)) in exact_targets
    assert (str(metric["resource"]["resource_id"]), int(metric["resource"]["version"])) in exact_targets
    assert (str(feedback["resource"]["resource_id"]), int(feedback["resource"]["version"])) in exact_targets

    # Replaying the same resource_event is an idempotent observation and cannot append
    # another profile version.
    adopted_event = migrated_conn.execute(
        """
        select id::text, payload from resource_events
        where resource_id = %s and event_type = 'adopted'
        order by created_at limit 1
        """,
        (str(copy.id),),
    ).fetchone()
    replay = PreferenceLearningService(repo).record_exact_event(
        tenant_id="default",
        actor_open_id="ou-owner",
        event_type="adopted",
        source_resource_id=str(copy.id),
        source_resource_version=int(adopted_event["payload"]["version"]),
        source_event_id=adopted_event["id"],
        event_payload=dict(adopted_event["payload"]),
    )
    assert replay["inserted"] is False
    assert replay["profile"]["resource_version"] == state["profile_resource_version"]


def test_lifecycle_preference_failure_rolls_back_state_and_event(migrated_conn, monkeypatch):
    from data_foundation.repositories.generated_copy import GeneratedCopyRepository
    from data_foundation.repositories.resource import ResourceRepository

    repo = ResourceRepository(migrated_conn)
    copy = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_type="generated_copy",
        title="候选",
        content_text="正文",
        content_json={"title": "候选", "body": "正文", "tags": [], "variant_label": "A"},
        visibility="team",
        owner_open_id="ou-owner",
        outbox_requests=[],
    )
    lifecycle = GeneratedCopyRepository(repo)
    state = lifecycle.initialize_candidate(
        tenant_id="default",
        actor_open_id="ou-owner",
        resource_id=str(copy.id),
        resource_version=int(copy.version),
        label="A",
    )

    def _fail(*_args, **_kwargs):
        raise RuntimeError("profile rebuild failed")

    monkeypatch.setattr(PreferenceLearningService, "record_exact_event", _fail)
    with pytest.raises(RuntimeError, match="profile rebuild failed"):
        lifecycle.adopt_version(
            tenant_id="default",
            actor_open_id="ou-owner",
            resource_id=str(copy.id),
            resource_version=int(copy.version),
            expected_state_version=state.state_version,
        )

    persisted = lifecycle.get_state(
        tenant_id="default", actor_open_id="ou-owner", resource_id=str(copy.id)
    )
    assert persisted.lifecycle_status == "candidate"
    assert persisted.adopted_version is None
    assert migrated_conn.execute(
        "select count(*) from resource_events where resource_id = %s and event_type = 'adopted'",
        (str(copy.id),),
    ).fetchone()[0] == 0
