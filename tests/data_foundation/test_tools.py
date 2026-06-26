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
            return [("res-1", 0.8)]
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

    def _readable_rows(tenant_id, actor_open_id, resource_ids):
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
            return [("res-1", 0.8)]

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
