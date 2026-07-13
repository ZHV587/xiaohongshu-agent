from __future__ import annotations

import inspect
from contextlib import nullcontext

from tools.runtime_identity import identity_config


def test_resource_repository_check_permission_signature_is_stable():
    """S2 护栏(不依赖 DB):creation_memory._actor_can_read 用 getattr(repo,"check_permission")
    软门调用真仓权限校验。若真方法被改名/改签名,getattr 取不到 → 软门退化成 allow-all 越权,
    而其余单测仍绿(假仓本就没这方法、真仓 ACL 测试默认 skip)。此处把签名钉死,漂移即在单元层炸。
    """
    from data_foundation.repositories.resource import ResourceRepository

    assert hasattr(ResourceRepository, "check_permission")
    params = list(inspect.signature(ResourceRepository.check_permission).parameters)
    # _actor_can_read 以 (resource_id, actor, permission=..., conn=...) 调用,这些形参必须在
    assert params[:3] == ["self", "resource_id", "actor"], params
    assert "permission" in params and "conn" in params, params


class RecordingRepository:
    def __init__(self):
        self.edges = []
        self.conn = object()

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
        return type(
            "Resource",
            (),
            {"id": "generated-1", "type": kwargs["resource_type"], "title": kwargs["title"], "version": 1},
        )()

    def add_edge(self, **kwargs):
        self.edge = kwargs
        self.edges.append(kwargs)

    def writable_resource_metadata(self, **kwargs):
        self.writable_kwargs = kwargs
        return {"type": "xhs_online_note", "version": 1, "visibility": "team", "owner_open_id": kwargs["actor_open_id"]}

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
                {"resource_id": "source-1", "summary": "依据"},
                {"resource_id": "source-2", "summary": "另一个依据"},
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
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["actor_open_id"] == "ou_user"
    assert repo.upsert["resource_type"] == "generated_copy"
    assert repo.upsert["content_json"]["source_topic"] == "轻量露营"


def test_save_user_feedback_tool_persists_revision_request(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_user_feedback.func(
        feedback="标题再狠一点",
        target_resource_id="generated-0",
        feedback_type="revision_request",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["resource_type"] == "revision_request"
    assert repo.edge["edge_type"] == "feedback_on"


def test_save_generated_topic_skips_edge_to_unreadable_evidence(monkeypatch):
    """P1 安全回归:用户提供的 evidence 指向 actor 无权读的资源时,不得建 derived_from 边
    (防越权连到他人私有资源 → graph_ingest 暴露其存在)。"""
    from data_foundation import tools as df_tools

    class _AclRepo(RecordingRepository):
        def check_permission(self, resource_id, actor, permission="write", conn=None):
            if resource_id == "11111111-1111-1111-1111-111111111111":  # 受害者私有资源
                raise PermissionError("not readable")
            # 其余(本人可读)放行

    repo = _AclRepo()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_generated_topic.func(
        direction="露营",
        topics=["轻量化装备清单"],
        selected_topic={
            "topic": "轻量化装备清单",
            "evidence": [
                {"resource_id": "22222222-2222-2222-2222-222222222222"},  # 可读
                {"resource_id": "11111111-1111-1111-1111-111111111111"},  # 不可读
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
        def check_permission(self, resource_id, actor, permission="write", conn=None):
            raise PermissionError("not readable")

    repo = _AclRepo()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_user_feedback.func(
        feedback="想抄这条",
        target_resource_id="11111111-1111-1111-1111-111111111111",
        feedback_type="revision_request",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.edges == []  # 越权边被跳过


def test_save_session_snapshot_tool_persists_for_current_actor(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_session_snapshot.func(
        project_name="露营账号",
        title="账号定位诊断",
        content="目标人群、卖点、内容方向……",
        metadata={"phase": "diagnosis"},
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["tenant_id"] == "default"
    assert repo.upsert["actor_open_id"] == "ou_user"
    assert repo.upsert["resource_type"] == "session_snapshot"
    assert repo.upsert["title"] == "[露营账号] 账号定位诊断"
    # outbox 副作用必须被显式投递(P0 回归:default_write_requests 曾因缺 import 抛 NameError)
    assert repo.upsert["outbox_requests"] is not None


def test_save_performance_metric_tool_persists_for_current_actor(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))

    result = df_tools.save_performance_metric.func(
        target_resource_id="generated-1",
        metrics={"likes": 10, "collects": 5, "views": 100},
        published_at="2026-06-20T08:00:00+00:00",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["tenant_id"] == "default"
    assert repo.upsert["actor_open_id"] == "ou_user"
    assert repo.upsert["resource_type"] == "performance_metric"
    assert repo.edge["source_resource_id"] == "generated-1"
    assert repo.edge["edge_type"] == "measured_by"


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


def test_search_resources_integrates_ranking_fields(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()

    # Define bulk_performance_metrics on our mock RecordingRepository
    def _bulk_perf(tenant_id, resource_ids):
        return {rid: [{"metrics": {"likes": 100}}] for rid in resource_ids}
    repo.bulk_performance_metrics = _bulk_perf

    def _readable_rows(tenant_id, actor_open_id, resource_ids, resource_versions):
        assert resource_versions == [1]
        return [
            {
                "id": rid,
                "type": "doc",
                "title": "露营装备",
                "summary": "露营",
                "visibility": "team",
                "updated_at": None,
                "source_updated_at": None,
                "score": 1.0
            }
            for rid in resource_ids
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
            return [("res-1", 0.8, 1)]
        def ensure_index(self):
            pass

    import data_foundation.meili_client as meili_client
    monkeypatch.setattr(meili_client, "MeiliResourceIndex", MockIndex)

    result = df_tools.search_resources.func(query="露营", config=identity_config("ou_user"))

    assert result["ok"] is True
    assert len(result["results"]) == 1
    assert "why_selected" in result["results"][0]
    assert "rank_signals" in result["results"][0]



def test_search_local_note_cards_returns_detailed_cards(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()

    def _readable_rows(tenant_id, actor_open_id, resource_ids, resource_versions):
        assert resource_versions == [1]
        return [
            {
                "id": "res-1",
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
            return [("res-1", 0.8, 1)]

    import data_foundation.meili_client as meili_client
    monkeypatch.setattr(meili_client, "MeiliResourceIndex", MockIndex)

    result = df_tools.search_local_note_cards.func(keyword="护肤", config=identity_config("ou_user"))

    assert result["ok"] is True
    assert len(result["results"]) == 1
    card = result["results"][0]
    # 细致字段(rank_evidence 路径拿不到的)
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
