from __future__ import annotations

from tools.runtime_identity import identity_config


class RecordingRepository:
    def data_foundation_status(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "resources": {"total": 0, "by_type": {}},
            "sync": {
                "running": False,
                "last_status": None,
                "last_success_at": None,
                "last_error": None,
                "last_counts": None,
            },
            "outbox": {"pending": 0, "processing": 0, "succeeded": 0, "failed": 0},
        }


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


def test_sync_feishu_resources_tool_loads_real_feishu_sources(monkeypatch):
    from data_foundation import tools as df_tools

    captured = {}
    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))
    monkeypatch.setattr(
        df_tools,
        "load_feishu_sources",
        lambda config: {
            "base_rows": [{"record_id": "rec1", "fields": {"标题": "一"}}],
            "wiki_documents": [{"obj_token": "doc1", "node_token": "wik1", "title": "文档"}],
            "source_errors": ["wiki document doc2 failed"],
            "app_token": "app-real",
            "table_id": "tbl-real",
            "wiki_space_id": "space-real",
        },
    )

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

    result = df_tools.sync_feishu_resources.func(config=identity_config("ou_user"))

    assert result["ok"] is True
    assert result["run_id"] == "run-1"
    assert captured["repo"] is repo
    assert captured["kwargs"] == {
        "tenant_id": "default",
        "actor_open_id": "ou_user",
        "triggered_by": "manual",
        "base_rows": [{"record_id": "rec1", "fields": {"标题": "一"}}],
        "wiki_documents": [{"obj_token": "doc1", "node_token": "wik1", "title": "文档"}],
        "source_errors": ["wiki document doc2 failed"],
        "app_token": "app-real",
        "table_id": "tbl-real",
        "wiki_space_id": "space-real",
    }


def test_sync_feishu_resources_tool_fails_when_sources_return_nothing(monkeypatch):
    from data_foundation import tools as df_tools

    captured = {}
    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _RepoContext(repo))
    monkeypatch.setattr(
        df_tools,
        "load_feishu_sources",
        lambda config: {
            "base_rows": [],
            "wiki_documents": [],
            "source_errors": [],
            "app_token": "",
            "table_id": "",
            "wiki_space_id": "",
        },
    )

    def _sync(repo_arg, **kwargs):
        captured["kwargs"] = kwargs
        return {
            "ok": False,
            "run_id": "run-1",
            "status": "failed",
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 1,
            "errors": kwargs["source_errors"],
        }

    monkeypatch.setattr(df_tools, "sync_feishu_sources", _sync)

    result = df_tools.sync_feishu_resources.func(config=identity_config("ou_user"))

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert captured["kwargs"]["source_errors"] == [
        "No readable Feishu resources were returned from configured sources"
    ]
