from __future__ import annotations

import inspect
from contextlib import nullcontext

import pytest

from data_foundation.preference_learning import ExactResourceVersion
from tools.runtime_identity import identity_config


def test_resource_repository_exact_version_acl_signature_is_stable():
    from data_foundation.repositories.resource import ResourceRepository

    params = list(inspect.signature(ResourceRepository.get_resource_version).parameters)
    assert params[:5] == [
        "self",
        "tenant_id",
        "actor_open_id",
        "resource_id",
        "resource_version",
    ], params


class RecordingRepository:
    def __init__(self):
        self.edges = []
        self.upserts = []
        self.resources = {}
        self.conn = object()
        self.session_rows = []

    def unit_of_work(self):
        return nullcontext()

    def data_foundation_status(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "resources": {"total": 0, "by_type": {}},
            "sync": {
                "running": False,
                "last_status": None,
                "last_success_at": None,
                "last_error_summary": None,
                "last_counts": None,
            },
            "outbox": {"pending": 0, "processing": 0, "succeeded": 0, "failed": 0},
        }

    def upsert_resource(self, **kwargs):
        self.upsert = kwargs
        self.upserts.append(kwargs)
        resource_id = kwargs.get("resource_id") or f"generated-{len(self.resources) + 1}"
        resource = type(
            "Resource",
            (),
            {
                "id": resource_id,
                "type": kwargs["resource_type"],
                "title": kwargs["title"],
                "version": 1,
                "content_text": kwargs.get("content_text"),
                "content_json": dict(kwargs.get("content_json") or {}),
                "visibility": kwargs.get("visibility", "private"),
                "owner_open_id": kwargs.get("owner_open_id"),
            },
        )()
        self.resources[(str(resource_id), 1)] = resource
        return resource

    def add_edge(self, **kwargs):
        self.edge = kwargs
        self.edges.append(kwargs)

    def get_resource_version(self, tenant_id, actor_open_id, resource_id, resource_version):
        stored = self.resources.get((str(resource_id), int(resource_version)))
        if stored is not None:
            return stored
        return type(
            "Resource",
            (),
            {
                "id": resource_id,
                "version": resource_version,
                "title": "爆款原文",
                "type": "xhs_online_note",
                "content_text": "爆款原文正文",
                "content_json": {"title": "爆款原文", "body": "爆款原文正文"},
                "visibility": "team",
                "owner_open_id": actor_open_id,
            },
        )()

    def get_resource_for_knowledge(
        self, tenant_id, actor_open_id, resource_id, resource_version
    ):
        return self.get_resource_version(
            tenant_id, actor_open_id, resource_id, resource_version
        )

    def writable_resource_metadata(self, **kwargs):
        self.writable_kwargs = kwargs
        return {"type": "xhs_online_note", "version": 1, "visibility": "team", "owner_open_id": kwargs["actor_open_id"]}

    def list_owned_session_snapshots(self, **kwargs):
        self.session_list_kwargs = kwargs
        return list(self.session_rows)

    def find_performance_metric_id(self, **kwargs):
        return None

    def performance_rows(self, **kwargs):
        self.performance_kwargs = kwargs
        return [{
            "resource_id": "metric-1",
            "title": "小红书效果 2026-06-20",
            "content_json": {"metrics": {"likes": 10}, "score": 10, "channel": "xiaohongshu"},
            "weight": 10,
            "updated_at": None,
        }]


class RecordingSourceRepository:
    def __init__(self, conn):
        self.conn = conn


class _RepoContext:
    def __init__(self, repo):
        self.repo = repo

    def __enter__(self):
        return self.repo

    def __exit__(self, exc_type, exc, tb):
        return False


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

    def list_eligible_assets(self, **_kwargs):
        return []

    def list_actor_patterns(self, **_kwargs):
        return []

    def mark_synthesis_completed(self, **_kwargs):
        return True


def _patch_preference_repository(monkeypatch):
    from data_foundation.repositories import preference as preference_repository

    memory = _MemoryPreferenceRepository()
    monkeypatch.setattr(preference_repository, "PreferenceRepository", lambda _conn: memory)
    return memory


def test_get_data_foundation_status_tool_returns_structured_status(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.get_data_foundation_status.func(config=identity_config("ou_user"))

    assert result["ok"] is True
    assert result["status"]["tenant_id"] == "default"
    assert result["status"]["resources"]["total"] == 0


def test_sync_feishu_resources_tool_delegates_to_source_processors(monkeypatch):
    from data_foundation import tools as df_tools

    captured = {}
    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    def _sync(repo_arg, **kwargs):
        captured["repo"] = repo_arg
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "run_id": "run-1",
            "status": "success",
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }

    monkeypatch.setattr(df_tools, "sync_feishu_sources", _sync)
    monkeypatch.setattr(df_tools, "SourceRepository", RecordingSourceRepository)

    result = df_tools.sync_feishu_resources.func(config=identity_config("ou_user"))

    assert result["ok"] is True
    assert result["run_id"] == "run-1"
    assert captured["repo"] is repo
    assert isinstance(captured["kwargs"].pop("source_repo"), RecordingSourceRepository)
    assert captured["kwargs"] == {"tenant_id": "default", "actor_open_id": "ou_user", "triggered_by": "manual"}


def test_save_generated_topic_tool_persists_for_current_actor(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    # evidence 经 selected_topic(InjectedState)直传,不再是 LLM 参数;topics 以点选的卡为准。
    result = df_tools.save_generated_topic.func(
        direction="露营装备",
        topics=["LLM 占位(应被卡片覆盖)"],
        selected_topic={
            "topic": "轻量露营（收藏点强）",
            "evidence": [
                {"resource_id": "source-1", "resource_version": 2, "summary": "依据"},
                {"resource_id": "source-2", "resource_version": 3, "summary": "另一个依据"},
            ],
        },
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["tenant_id"] == "default"
    assert repo.upsert["actor_open_id"] == "ou_user"
    assert repo.upsert["resource_type"] == "generated_topic"
    # 落库的选题以用户点选的那张卡为准(覆盖 LLM 占位)
    assert repo.upsert["content_json"]["topics"] == ["轻量露营（收藏点强）"]
    assert [edge["target_resource_id"] for edge in repo.edges] == ["source-1", "source-2"]
    assert [edge["target_resource_version"] for edge in repo.edges] == [2, 3]


def test_save_generated_topic_evidence_not_llm_arg():
    """完整修复:evidence 不暴露给 LLM(只能经 selected_topic 的 InjectedState 注入)。"""
    from data_foundation import tools as df_tools

    llm_args = list(df_tools.save_generated_topic.args.keys())
    assert "evidence" not in llm_args
    assert "selected_topic" not in llm_args  # InjectedState 对模型不可见


def test_save_generated_copy_tool_persists_for_current_actor(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_generated_copy.func(
        title="露营别乱买",
        body="这份清单够了",
        tags=["#露营"],
        source_topic="轻量露营",
        evidence=[],
        knowledge_grounding={
            "status": "ready",
            "query": "写一篇轻量露营文案",
            "turn_id": None,
            "retrieval_mode": "insufficient_relevance",
            "evidence": [],
            "gaps": "暂无相关案例",
        },
        latest_user_request="写一篇轻量露营文案",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["actor_open_id"] == "ou_user"
    assert repo.upsert["resource_type"] == "generated_copy"
    assert repo.upsert["content_json"]["source_topic"] == "轻量露营"
    assert repo.upsert["content_json"]["knowledge_grounding"]["retrieval_mode"] == "insufficient_relevance"


def test_save_generated_copy_grounding_is_injected_not_llm_writable():
    from data_foundation import tools as df_tools

    llm_args = set(df_tools.save_generated_copy.args)
    assert "knowledge_grounding" not in llm_args
    assert "latest_user_request" not in llm_args


def test_save_generated_copy_requires_runtime_grounding(monkeypatch):
    from data_foundation import tools as df_tools

    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(RecordingRepository()))
    with pytest.raises(RuntimeError, match="retrieve_knowledge grounding"):
        df_tools.save_generated_copy.func(
            title="标题",
            body="正文",
            tags=[],
            config=identity_config("ou_user"),
        )


def test_revision_save_automatically_persists_exact_user_request(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))
    saved_calls = []
    feedback_calls = []
    monkeypatch.setattr(
        df_tools,
        "save_generated_copy_resource",
        lambda _repo, **kwargs: saved_calls.append(kwargs) or {
            "ok": True,
            "resource": {"resource_id": kwargs["resource_id"], "resource_version": 5},
        },
    )
    monkeypatch.setattr(
        df_tools,
        "save_user_feedback_resource",
        lambda _repo, **kwargs: feedback_calls.append(kwargs) or {
            "ok": True,
            "resource": {"resource_id": "feedback-1", "resource_version": 1},
        },
    )
    grounding = {
        "status": "ready",
        "query": "标题再狠一点",
        "turn_id": "turn-1",
        "retrieval_mode": "insufficient_relevance",
        "evidence": [],
        "gaps": "暂无相近案例",
    }

    result = df_tools.save_generated_copy.func(
        title="更狠的标题",
        body="正文",
        tags=[],
        resource_id="11111111-1111-4111-8111-111111111111",
        expected_resource_version=4,
        expected_state_version=2,
        knowledge_grounding=grounding,
        latest_user_request="标题再狠一点",
        config={
            "configurable": {
                "langgraph_auth_user": {"identity": "ou_user"},
                "turn_id": "turn-1",
            }
        },
    )

    assert result["feedback_resource"]["resource_id"] == "feedback-1"
    assert saved_calls[0]["evidence"] == []
    assert feedback_calls[0]["feedback"] == "标题再狠一点"
    assert feedback_calls[0]["target_resource_version"] == 4
    assert feedback_calls[0]["feedback_type"] == "revision_request"
    assert feedback_calls[0]["idempotency_key"] == "auto-revision-feedback:turn-1"


def test_save_user_feedback_tool_persists_revision_request(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    preferences = _patch_preference_repository(monkeypatch)
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_user_feedback.func(
        feedback="标题再狠一点",
        target_resource_id="generated-0",
        target_resource_version=4,
        feedback_type="revision_request",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    feedback_write = next(item for item in repo.upserts if item["resource_type"] == "revision_request")
    assert feedback_write["content_json"]["target_resource_version"] == 4
    feedback_edge = next(item for item in repo.edges if item["edge_type"] == "feedback_on")
    assert feedback_edge["target_resource_version"] == 4
    assert len(preferences.observations) == 1
    observation = next(iter(preferences.observations.values()))
    assert observation.event_type == "feedback"
    assert observation.source == ExactResourceVersion(
        result["resource"]["resource_id"], 1
    )


def test_save_writing_teardown_tool_persists_exact_source_link(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_writing_teardown.func(
        source_resource_id="source-1",
        source_resource_version=6,
        niche="职场成长",
        hook="工作三年后我才发现",
        cta="收藏后照着检查",
        structure=["反常识钩子", "亲历证据", "步骤清单"],
        success_factors=["具体数字", "低门槛行动"],
        style_tags=["克制", "口语"],
        quality=88,
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["resource_type"] == "writing_teardown"
    assert repo.upsert["content_json"]["source_resource_version"] == 6
    assert repo.edge["edge_type"] == "teardown_of"
    assert repo.edge["target_resource_version"] == 6


def test_save_generated_topic_skips_edge_to_unreadable_evidence(monkeypatch):
    """P1 安全回归:用户提供的 evidence 指向 actor 无权读的资源时,不得建 derived_from 边
    (防越权连到他人私有资源 → graph_ingest 暴露其存在)。"""
    from data_foundation import tools as df_tools

    class _AclRepo(RecordingRepository):
        def get_resource_version(self, tenant_id, actor_open_id, resource_id, resource_version):
            if resource_id == "11111111-1111-1111-1111-111111111111":  # 受害者私有资源
                return None
            return super().get_resource_version(
                tenant_id, actor_open_id, resource_id, resource_version
            )

    repo = _AclRepo()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_generated_topic.func(
        direction="露营",
        topics=["轻量化装备清单"],
        selected_topic={
            "topic": "轻量化装备清单",
            "evidence": [
                {"resource_id": "22222222-2222-2222-2222-222222222222", "resource_version": 1},  # 可读
                {"resource_id": "11111111-1111-1111-1111-111111111111", "resource_version": 1},  # 不可读
            ],
        },
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    linked = {e["target_resource_id"] for e in repo.edges}
    assert "22222222-2222-2222-2222-222222222222" in linked
    assert "11111111-1111-1111-1111-111111111111" not in linked  # 越权边被跳过


def test_save_user_feedback_skips_edge_to_unreadable_target(monkeypatch):
    """P1 安全回归:反馈 target 指向 actor 无权读的资源时,不得建 feedback_on 边。"""
    from data_foundation import tools as df_tools

    class _AclRepo(RecordingRepository):
        def get_resource_version(self, tenant_id, actor_open_id, resource_id, resource_version):
            if resource_id == "11111111-1111-1111-1111-111111111111":
                return None
            return super().get_resource_version(
                tenant_id, actor_open_id, resource_id, resource_version
            )

    repo = _AclRepo()
    preferences = _patch_preference_repository(monkeypatch)
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_user_feedback.func(
        feedback="想抄这条",
        target_resource_id="11111111-1111-1111-1111-111111111111",
        target_resource_version=1,
        feedback_type="revision_request",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert not [edge for edge in repo.edges if edge["edge_type"] == "feedback_on"]
    assert len(preferences.observations) == 1  # 反馈事实本身仍精确、私有地被观察


def test_save_session_snapshot_tool_persists_for_current_actor(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_session_snapshot.func(
        project_name="露营账号",
        title="账号定位诊断",
        content="目标人群、卖点、内容方向……",
        snapshot_kind="diagnosis",
        metadata={"phase": "diagnosis", "confirmed": True, "confirmed_by": "伪造"},
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["tenant_id"] == "default"
    assert repo.upsert["actor_open_id"] == "ou_user"
    assert repo.upsert["resource_type"] == "session_snapshot"
    assert repo.upsert["title"] == "[露营账号] 账号定位诊断"
    assert repo.upsert["visibility"] == "private"
    assert repo.upsert["content_json"] == {
        "phase": "diagnosis",
        "project_name": "露营账号",
        "snapshot_kind": "diagnosis",
    }
    assert result["resource_version"] == 1
    assert result["confirmation_status"] == "unconfirmed"
    # outbox 副作用必须被显式投递(P0 回归:default_write_requests 曾因缺 import 抛 NameError)
    assert repo.upsert["outbox_requests"] is not None


def test_get_session_snapshots_uses_owner_scoped_restore_path(monkeypatch):
    from datetime import datetime, timezone
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    repo.session_rows = [{
        "resource_id": "11111111-1111-1111-1111-111111111111",
        "resource_version": 3,
        "title": "[露营账号] 阶段状态",
        "summary": "阶段状态",
        "content_text": "本轮结论",
        "content_json": {"snapshot_kind": "workflow_state"},
        "updated_at": datetime(2026, 7, 13, tzinfo=timezone.utc),
    }]
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.get_session_snapshots.func(
        project_name="露营账号",
        limit=5,
        config=identity_config("ou_user"),
    )

    assert result["snapshots"][0]["resource_version"] == 3
    assert repo.session_list_kwargs["actor_open_id"] == "ou_user"
    assert repo.session_list_kwargs["project_name"] == "露营账号"


def test_confirm_session_snapshot_uses_permission_checked_confirmation_repository(monkeypatch):
    from data_foundation import tools as df_tools
    from data_foundation.knowledge import repository as knowledge_repository

    repo = RecordingRepository()
    captured = {}

    class _KnowledgeRepository:
        def __init__(self, conn):
            captured["conn"] = conn

        def confirm_exact_version(self, *args):
            captured["args"] = args
            return {
                "resource_id": args[2],
                "resource_version": args[3],
                "eligibility": "pending",
                "asset_kind": "strategy_fact",
            }

    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))
    monkeypatch.setattr(knowledge_repository, "KnowledgeRepository", _KnowledgeRepository)
    assert "snapshot_kind" not in df_tools.confirm_session_snapshot.args_schema.model_json_schema()[
        "properties"
    ]

    result = df_tools.confirm_session_snapshot.func(
        resource_id="11111111-1111-1111-1111-111111111111",
        resource_version=2,
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert captured["args"] == (
        "default",
        "ou_user",
        "11111111-1111-1111-1111-111111111111",
        2,
        "strategy_fact",
        {},
    )


def test_save_performance_metric_tool_persists_for_current_actor(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    preferences = _patch_preference_repository(monkeypatch)
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_performance_metric.func(
        target_resource_id="generated-1",
        target_resource_version=1,
        metrics={"likes": 10, "collects": 5, "views": 100},
        published_at="2026-06-20T08:00:00+00:00",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    metric_write = next(item for item in repo.upserts if item["resource_type"] == "performance_metric")
    assert metric_write["tenant_id"] == "default"
    assert metric_write["actor_open_id"] == "ou_user"
    measured_edge = next(item for item in repo.edges if item["edge_type"] == "measured_by")
    assert measured_edge["source_resource_id"] == "generated-1"
    assert measured_edge["source_resource_version"] == 1
    observation = next(iter(preferences.observations.values()))
    assert observation.event_type == "metric"
    assert observation.source == ExactResourceVersion("generated-1", 1)


def test_get_resource_performance_tool_reads_for_current_actor(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.get_resource_performance.func(
        resource_id="generated-1",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert result["metrics"][0]["resource_id"] == "metric-1"
    assert repo.performance_kwargs == {
        "tenant_id": "default",
        "actor_open_id": "ou_user",
        "resource_id": "generated-1",
    }


def test_retrieve_knowledge_delegates_to_unified_domain_service(monkeypatch):
    from data_foundation import tools as df_tools
    import data_foundation.retrieval as retrieval
    from data_foundation.evidence import EvidenceItem, EvidencePackage, RetrievalFilters

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))
    calls = []
    package = EvidencePackage(
        retrieval_mode="semantic_only",
        evidence=[
            EvidenceItem(
                resource_id="00000000-0000-0000-0000-000000000001",
                resource_version=1,
                type="generated_copy",
                asset_kind="copy",
                source_kind="user_adopted",
                niche="露营",
                title="露营装备",
                summary="露营",
                source_updated_at="未知",
                indexed_at="2026-07-13T00:00:00Z",
                score=0.8,
                relevance=1.0,
                freshness=0.5,
                quality=0.8,
                performance=0.0,
                retrieval_sources=["semantic"],
                why_selected="语义召回",
            )
        ],
        engines_used=["semantic"],
    )

    def _retrieve(repo_arg, **kwargs):
        assert repo_arg is repo
        calls.append(kwargs)
        return package

    monkeypatch.setattr(retrieval, "retrieve_for_actor", _retrieve)

    result = df_tools.retrieve_knowledge.func(
        query="露营",
        filters={"niches": ["露营"]},
        config=identity_config("ou_user"),
    )

    assert result == package.model_dump(mode="json")
    assert calls == [
        {
            "tenant_id": "default",
            "actor_open_id": "ou_user",
            "query": "露营",
            "limit": 10,
            "filters": RetrievalFilters(niches=["露营"]),
        }
    ]
    assert not hasattr(df_tools, "search_resources")
    assert not hasattr(df_tools, "semantic_search_resources")
    assert not hasattr(df_tools, "graph_expand")


def test_retrieve_knowledge_returns_only_safe_error_codes(monkeypatch):
    from data_foundation import tools as df_tools
    import data_foundation.retrieval as retrieval

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    invalid = df_tools.retrieve_knowledge.func(
        query="   ", config=identity_config("ou_user")
    )
    assert invalid == {"error": "INVALID_RETRIEVAL_REQUEST"}

    def _explode(*_args, **_kwargs):
        raise RuntimeError("Authorization: Bearer must-not-leak")

    monkeypatch.setattr(retrieval, "retrieve_for_actor", _explode)
    failed = df_tools.retrieve_knowledge.func(
        query="露营", config=identity_config("ou_user")
    )
    assert failed == {"error": "KNOWLEDGE_RETRIEVAL_FAILED"}
    assert "must-not-leak" not in str(failed)



def test_search_local_note_cards_returns_detailed_cards(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()

    def _readable_rows(tenant_id, actor_open_id, resource_ids, resource_versions):
        assert resource_versions == [1]
        return [
            {
                "id": "res-1",
                "resource_version": 1,
                "type": "feishu_base_record",
                "title": "秋冬护肤",
                "summary": "s",
                "visibility": "team",
                "updated_at": None,
                "source_updated_at": None,
                "content_json": {
                    "fields": {
                        "标题": "秋冬护肤攻略",
                        "正文": "正文内容",
                        "博主": "护肤老师",
                        "封面链接": "http://sns-webpic-qc.xhscdn.com/a.jpg",
                        "原文链接": "[查看原文](http://xhslink.com/o/abc)",
                        "话题标签": "护肤,秋冬",
                        "点赞数": 3000,
                        "收藏数": 1500,
                    }
                },
            }
        ]
    repo.readable_rows_by_ids = _readable_rows

    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))
    import data_foundation.engine_config as engine_config
    monkeypatch.setattr(engine_config, "meili_config_from_env", lambda: type("Cfg", (), {"state": "enabled"})())

    class MockIndex:
        @classmethod
        def from_config(cls, cfg):
            return cls()
        def search(self, query, tenant_id, limit):
            from data_foundation.meili_client import MeiliSearchHit

            return [
                MeiliSearchHit(
                    resource_id="res-1",
                    resource_version=1,
                    score=0.8,
                    resource_type="feishu_base_record",
                    asset_kind="benchmark",
                    source_kind="feishu_sync",
                    niche="护肤",
                    quality_score=0.8,
                    qualified_at_epoch=1,
                )
            ]

    import data_foundation.meili_client as meili_client
    monkeypatch.setattr(meili_client, "MeiliResourceIndex", MockIndex)

    result = df_tools.search_local_note_cards.func(keyword="护肤", config=identity_config("ou_user"))

    assert result["ok"] is True
    assert len(result["results"]) == 1
    card = result["results"][0]
    assert card["resource_version"] == 1
    # 细致字段（统一 EvidencePackage 不承载发现卡片媒体字段）
    assert card["cover_url"] == "http://sns-webpic-qc.xhscdn.com/a.jpg"
    assert card["note_url"] == "http://xhslink.com/o/abc"
    assert card["likes"] == 3000 and card["collects"] == 1500
    assert card["tags"] == ["护肤", "秋冬"]
    assert card["source"] == "local"
    assert card["already_local"] is True


def test_get_generated_copy_lifecycle_returns_exact_snapshots_and_cas_tokens(monkeypatch):
    from data_foundation import tools as df_tools
    import data_foundation.repositories.generated_copy as lifecycle_module

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    class _Lifecycle:
        def __init__(self, resource_repo):
            assert resource_repo is repo

        def get_state(self, **kwargs):
            assert kwargs["actor_open_id"] == "ou_user"
            return type(
                "State",
                (),
                {
                    "resource_id": kwargs["resource_id"],
                    "lifecycle_status": "selected",
                    "selected_version": 2,
                    "selected_label": "A",
                    "adopted_version": None,
                    "finalized_version": None,
                    "published_version": None,
                    "knowledge_target_version": None,
                    "latest_resource_version": 2,
                    "state_version": 4,
                },
            )()

        def list_versions(self, **_kwargs):
            return [
                {
                    "resourceVersion": 2,
                    "label": "A",
                    "title": "Exact title",
                    "body": "Exact body",
                    "tags": ["#exact"],
                    "cover": "cover",
                    "note": "note",
                }
            ]

    monkeypatch.setattr(lifecycle_module, "GeneratedCopyRepository", _Lifecycle)
    result = df_tools.get_generated_copy_lifecycle.func(
        "11111111-1111-1111-1111-111111111111",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    lifecycle = result["lifecycle"]
    assert lifecycle["latest_resource_version"] == 2
    assert lifecycle["state_version"] == 4
    assert lifecycle["versions"] == [
        {
            "resource_version": 2,
            "label": "A",
            "title": "Exact title",
            "body": "Exact body",
            "tags": ["#exact"],
            "cover": "cover",
            "note": "note",
        }
    ]
