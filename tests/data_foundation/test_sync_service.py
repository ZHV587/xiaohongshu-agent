from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_foundation.feishu_sync import SyncResult


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


def test_sync_service_records_success(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    monkeypatch.setattr(
        "data_foundation.sync_service.sync_base_rows",
        lambda *_args, **_kwargs: SyncResult(imported=2, errors=[]),
    )
    monkeypatch.setattr(
        "data_foundation.sync_service.sync_wiki_documents",
        lambda *_args, **_kwargs: SyncResult(imported=1, errors=[]),
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
        "status": "success",
        "created": 3,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
    }
    assert repo.started is not None
    assert repo.started["source"] == "feishu"
    assert repo.started["metadata"] == {"base_rows": 1, "wiki_documents": 1}
    assert repo.finished is not None
    assert repo.finished["status"] == "success"
    assert repo.finished["created_count"] == 3
    assert repo.finished["failed_count"] == 0
    assert repo.finished["error"] is None


def test_sync_service_records_partial_success(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    monkeypatch.setattr(
        "data_foundation.sync_service.sync_base_rows",
        lambda *_args, **_kwargs: SyncResult(imported=1, errors=["bad row"]),
    )
    monkeypatch.setattr(
        "data_foundation.sync_service.sync_wiki_documents",
        lambda *_args, **_kwargs: SyncResult(imported=0, errors=[]),
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
    assert result["status"] == "partial_success"
    assert result["created"] == 1
    assert result["failed"] == 1
    assert result["errors"] == ["bad row"]
    assert repo.finished is not None
    assert repo.finished["status"] == "partial_success"
    assert repo.finished["error"] == "bad row"


def test_sync_service_records_failed_when_everything_fails(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    monkeypatch.setattr(
        "data_foundation.sync_service.sync_base_rows",
        lambda *_args, **_kwargs: SyncResult(imported=0, errors=["bad base"]),
    )
    monkeypatch.setattr(
        "data_foundation.sync_service.sync_wiki_documents",
        lambda *_args, **_kwargs: SyncResult(imported=0, errors=["bad wiki"]),
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
    assert repo.finished["error"] == "bad base\nbad wiki"


def test_sync_service_records_failed_when_sync_raises(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    def raise_sync_error(*_args, **_kwargs):
        raise RuntimeError("feishu import crashed")

    repo = RecordingRepository()
    monkeypatch.setattr(
        "data_foundation.sync_service.sync_base_rows",
        lambda *_args, **_kwargs: SyncResult(imported=0, errors=[]),
    )
    monkeypatch.setattr("data_foundation.sync_service.sync_wiki_documents", raise_sync_error)

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
    assert repo.finished["error"] == "RuntimeError: feishu import crashed"
