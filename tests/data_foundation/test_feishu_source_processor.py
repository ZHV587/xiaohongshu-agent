from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass, field

import pytest

from data_foundation.models import Resource, SourceSecrets, SyncSource
from data_foundation.sources.base import SourceContext, SourceLease
from data_foundation.sources.feishu import FeishuBaseSourceProcessor, FeishuWikiSourceProcessor
from data_foundation.sources.registry import SourceProcessorRegistry, default_feishu_source_registry


@dataclass
class RecordingResourceRepository:
    resource: Resource
    upserts: list[dict] = field(default_factory=list)
    mappings: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)

    def unit_of_work(self):
        return nullcontext()

    def upsert_resource(self, **kwargs):
        self.upserts.append(kwargs)
        return self.resource

    def upsert_mapping(self, **kwargs):
        self.mappings.append(kwargs)

    def mark_mapping_failed(self, **kwargs):
        self.failures.append(kwargs)


class RecordingLease(SourceLease):
    def __init__(self):
        self.renewed = 0

    async def assert_owned(self) -> None:
        self.renewed += 1


def _resource() -> Resource:
    return Resource(
        id="resource-1",
        tenant_id="tenant-a",
        type="feishu_doc",
        title="标题",
        summary=None,
        content_text="",
        content_json={},
        status="active",
        visibility="team",
        owner_open_id="ou_sync",
        created_at=None,
        updated_at=None,
        version=1,
    )


def _source(source_type: str, *, config: dict | None = None) -> SyncSource:
    return SyncSource(
        id="source-1",
        tenant_id="tenant-a",
        source_type=source_type,
        name="飞书源",
        external_id=None,
        config=config or {},
        enabled=True,
        schedule_seconds=60,
        next_run_at=None,
        last_dispatched_at=None,
        lease_owner="worker-a",
        lease_expires_at=None,
        cursor={},
        created_at=None,
        updated_at=None,
    )


def _context(source_type: str, *, config: dict | None = None, credentials: dict | None = None) -> SourceContext:
    return SourceContext(
        source=_source(source_type, config=config),
        secrets=SourceSecrets(credentials=credentials or {"access_token": "secret-token"}),
        actor_open_id="ou_sync",
    )


def test_source_processor_registry_resolves_feishu_processors():
    repo = RecordingResourceRepository(_resource())
    registry = default_feishu_source_registry(repo)

    assert isinstance(registry.processor_for("feishu_base"), FeishuBaseSourceProcessor)
    assert isinstance(registry.processor_for("feishu_wiki"), FeishuWikiSourceProcessor)
    assert registry.processor_for("postgres_table") is None
    assert SourceProcessorRegistry({}).source_types == []


@pytest.mark.asyncio
async def test_feishu_base_source_uses_registered_identity_and_repository():
    repo = RecordingResourceRepository(_resource())
    lease = RecordingLease()

    def loader(context: SourceContext):
        assert context.secrets.credentials == {"access_token": "secret-token"}
        return {
            "app_token": "base-app",
            "table_id": "tbl",
            "sync_rows": [
                {"record_id": "rec1", "fields": {"标题": "露营", "正文": "正文"}},
                {"record_id": "rec2", "fields": {"title": "收纳", "content": "内容"}},
            ],
        }

    result = await FeishuBaseSourceProcessor(loader=loader, resource_repo=repo).sync(
        _context("feishu_base"),
        lease,
    )

    assert result.status == "succeeded"
    assert result.read_count == 2
    assert result.created_count == 2
    assert result.errors == []
    assert lease.renewed == 1
    assert [upsert["mapping"]["system"] for upsert in repo.upserts] == ["feishu", "feishu"]
    assert repo.upserts[0]["mapping"]["external_id"] == "base-app:tbl:rec1"


@pytest.mark.asyncio
async def test_feishu_wiki_source_upserts_documents_and_node_mapping():
    repo = RecordingResourceRepository(_resource())
    lease = RecordingLease()

    def loader(_context: SourceContext):
        return {
            "wiki_space_id": "sp1",
            "documents": [
                {
                    "obj_token": "doc1",
                    "node_token": "wik1",
                    "title": "选题方法",
                    "content": "正文",
                }
            ],
        }

    result = await FeishuWikiSourceProcessor(loader=loader, resource_repo=repo).sync(
        _context("feishu_wiki"),
        lease,
    )

    assert result.status == "succeeded"
    assert result.read_count == 1
    assert result.created_count == 1
    assert repo.mappings[0]["external_type"] == "wiki_node"
    assert repo.mappings[0]["external_id"] == "sp1:wik1"


@pytest.mark.asyncio
async def test_feishu_credentials_never_appear_in_result_errors():
    repo = RecordingResourceRepository(_resource())

    def loader(_context: SourceContext):
        raise RuntimeError("access_token=secret-token failed")

    result = await FeishuWikiSourceProcessor(loader=loader, resource_repo=repo).sync(
        _context("feishu_wiki", credentials={"access_token": "secret-token"}),
        RecordingLease(),
    )

    assert result.status == "failed"
    assert result.failed_count == 1
    assert "secret-token" not in result.errors[0]
    assert "access_token=<redacted>" in result.errors[0]


@pytest.mark.asyncio
async def test_feishu_source_normalizes_invalid_external_updated_at():
    repo = RecordingResourceRepository(_resource())

    def loader(_context: SourceContext):
        return {
            "wiki_space_id": "sp1",
            "documents": [
                {
                    "obj_token": "doc1",
                    "node_token": "wik1",
                    "title": "选题方法",
                    "content": "正文",
                    "external_updated_at": "bad-date",
                }
            ],
        }

    result = await FeishuWikiSourceProcessor(loader=loader, resource_repo=repo).sync(
        _context("feishu_wiki"),
        RecordingLease(),
    )

    assert result.status == "partial"
    assert result.created_count == 1
    assert "invalid external_updated_at" in result.errors[0]
    assert "external_updated_at" not in repo.upserts[0]["mapping"]
