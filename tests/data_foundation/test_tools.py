from __future__ import annotations

from contextlib import nullcontext

from tools.runtime_identity import identity_config


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
        return {"visibility": "team", "owner_open_id": kwargs["actor_open_id"]}

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

    result = df_tools.save_generated_topic.func(
        direction="露营装备",
        topics=["轻量露营（收藏点强）"],
        evidence=[
            {"resource_id": "source-1", "summary": "依据"},
            {"resource_id": "source-2", "summary": "另一个依据"},
        ],
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert repo.upsert["tenant_id"] == "default"
    assert repo.upsert["actor_open_id"] == "ou_user"
    assert repo.upsert["resource_type"] == "generated_topic"
    assert [edge["target_resource_id"] for edge in repo.edges] == ["source-1", "source-2"]


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

    def _readable_rows(tenant_id, actor_open_id, resource_ids):
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
            return ["res-1"]
        def ensure_index(self):
            pass

    import data_foundation.meili_client as meili_client
    monkeypatch.setattr(meili_client, "MeiliResourceIndex", MockIndex)

    result = df_tools.search_resources.func(query="露营", config=identity_config("ou_user"))

    assert result["ok"] is True
    assert len(result["results"]) == 1
    assert "why_selected" in result["results"][0]
    assert "rank_signals" in result["results"][0]

