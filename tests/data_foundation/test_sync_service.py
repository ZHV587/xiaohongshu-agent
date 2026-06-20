from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_foundation.sources.base import SourceSyncResult


@dataclass
class RecordingRepository:
    run_id: str = "run-1"
    started: dict[str, Any] | None = None
    finished: dict[str, Any] | None = None
    finish_calls: list[dict[str, Any]] = field(default_factory=list)

    def start_sync_run(self, **kwargs):
        self.started = kwargs
        return self.run_id

    def finish_sync_run(self, **kwargs):
        self.finished = kwargs
        self.finish_calls.append(kwargs)


def _install_processors(
    monkeypatch,
    *,
    base_result: SourceSyncResult | Exception,
    wiki_result: SourceSyncResult | Exception,
):
    from data_foundation import sync_service

    class FakeBaseProcessor:
        def __init__(self, *, loader, resource_repo):
            self.loader = loader
            self.resource_repo = resource_repo

        async def sync(self, context, lease):
            await lease.assert_owned()
            if isinstance(base_result, Exception):
                raise base_result
            return base_result

    class FakeWikiProcessor:
        def __init__(self, *, loader, resource_repo):
            self.loader = loader
            self.resource_repo = resource_repo

        async def sync(self, context, lease):
            await lease.assert_owned()
            if isinstance(wiki_result, Exception):
                raise wiki_result
            return wiki_result

    monkeypatch.setattr(sync_service, "FeishuBaseSourceProcessor", FakeBaseProcessor)
    monkeypatch.setattr(sync_service, "FeishuWikiSourceProcessor", FakeWikiProcessor)


def test_sync_service_records_success(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    _install_processors(
        monkeypatch,
        base_result=SourceSyncResult("succeeded", 1, 2, 0, 0, 0, [], {}),
        wiki_result=SourceSyncResult("succeeded", 1, 1, 0, 0, 0, [], {}),
    )

    result = sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
        base_rows=[{"record_id": "rec1", "fields": {"标题": "a"}}],
        wiki_documents=[{"obj_token": "doc1", "node_token": "wik1", "title": "b"}],
    )

    assert result == {
        "ok": True,
        "run_id": "run-1",
        "status": "succeeded",
        "created": 3,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }
    assert repo.started is not None
    assert repo.started["source_type"] == "feishu_base"
    assert repo.started["read_count"] == 2
    assert repo.finished is not None
    assert repo.finished["status"] == "succeeded"
    assert repo.finished["created_count"] == 3
    assert repo.finished["failed_count"] == 0
    assert repo.finished["error_summary"] is None


def test_sync_service_invokes_feishu_source_processors(monkeypatch):
    from data_foundation import sync_service

    repo = RecordingRepository()
    calls = []

    class FakeBaseProcessor:
        def __init__(self, *, loader, resource_repo):
            self.loader = loader
            self.resource_repo = resource_repo

        async def sync(self, context, lease):
            calls.append(("base", context.source.config, self.loader(context)))
            await lease.assert_owned()
            return SourceSyncResult("succeeded", 1, 1, 0, 0, 0, [], {})

    class FakeWikiProcessor:
        def __init__(self, *, loader, resource_repo):
            self.loader = loader
            self.resource_repo = resource_repo

        async def sync(self, context, lease):
            calls.append(("wiki", context.source.config, self.loader(context)))
            await lease.assert_owned()
            return SourceSyncResult("succeeded", 1, 2, 0, 0, 0, [], {})

    monkeypatch.setattr(sync_service, "FeishuBaseSourceProcessor", FakeBaseProcessor)
    monkeypatch.setattr(sync_service, "FeishuWikiSourceProcessor", FakeWikiProcessor)

    result = sync_service.sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
        base_rows=[{"record_id": "rec1", "fields": {"标题": "a"}}],
        wiki_documents=[{"obj_token": "doc1", "node_token": "wik1", "title": "b"}],
        app_token="base-app",
        table_id="tbl",
        wiki_space_id="sp1",
    )

    assert result["status"] == "succeeded"
    assert result["created"] == 3
    assert calls[0][0] == "base"
    assert calls[0][1] == {"app_token": "base-app", "table_id": "tbl"}
    assert calls[0][2]["sync_rows"] == [{"record_id": "rec1", "fields": {"标题": "a"}}]
    assert calls[1][0] == "wiki"
    assert calls[1][1] == {"wiki_space_id": "sp1"}
    assert calls[1][2]["documents"] == [{"obj_token": "doc1", "node_token": "wik1", "title": "b"}]


def test_sync_service_records_partial_success(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    _install_processors(
        monkeypatch,
        base_result=SourceSyncResult("partial", 1, 1, 0, 0, 1, ["bad row"], {}),
        wiki_result=SourceSyncResult("succeeded", 0, 0, 0, 0, 0, [], {}),
    )

    result = sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
        base_rows=[],
        wiki_documents=[],
    )

    assert result["ok"] is False
    assert result["status"] == "partial"
    assert result["created"] == 1
    assert result["failed"] == 1
    assert result["errors"] == ["bad row"]
    assert repo.finished is not None
    assert repo.finished["status"] == "partial"
    assert repo.finished["error_summary"] == "bad row"


def test_sync_service_records_failed_when_everything_fails(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    _install_processors(
        monkeypatch,
        base_result=SourceSyncResult("failed", 0, 0, 0, 0, 1, ["bad base"], {}),
        wiki_result=SourceSyncResult("failed", 0, 0, 0, 0, 1, ["bad wiki"], {}),
    )

    result = sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["created"] == 0
    assert result["failed"] == 2
    assert result["errors"] == ["bad base", "bad wiki"]
    assert repo.finished is not None
    assert repo.finished["status"] == "failed"
    assert repo.finished["error_summary"] == "bad base\nbad wiki"


def test_sync_service_includes_source_loader_errors(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    _install_processors(
        monkeypatch,
        base_result=SourceSyncResult("succeeded", 0, 0, 0, 0, 0, [], {}),
        wiki_result=SourceSyncResult("succeeded", 0, 0, 0, 0, 0, [], {}),
    )

    result = sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
        source_errors=["base: not configured"],
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["failed"] == 1
    assert result["errors"] == ["base: not configured"]
    assert repo.finished is not None
    assert repo.finished["error_summary"] == "base: not configured"


def test_sync_service_records_failed_when_sync_raises(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    _install_processors(
        monkeypatch,
        base_result=SourceSyncResult("succeeded", 0, 0, 0, 0, 0, [], {}),
        wiki_result=RuntimeError("feishu import crashed"),
    )

    result = sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
    )

    assert result["ok"] is False
    assert result["status"] == "failed"
    assert result["created"] == 0
    assert result["failed"] == 1
    assert result["errors"] == ["RuntimeError: feishu import crashed"]
    assert repo.finished is not None
    assert repo.finished["status"] == "failed"
    assert repo.finished["error_summary"] == "RuntimeError: feishu import crashed"
