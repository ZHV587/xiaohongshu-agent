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


class LosingLease(RecordingLease):
    async def assert_owned(self) -> None:
        await super().assert_owned()
        if self.renewed == 2:
            raise RuntimeError("SOURCE_LEASE_LOST")


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
                {"record_id": "rec1", "table_id": "tbl", "fields": {"标题": "露营", "正文": "正文"}},
                {"record_id": "rec2", "table_id": "tbl", "fields": {"title": "收纳", "content": "内容"}},
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
async def test_feishu_base_source_renews_lease_between_bounded_write_chunks():
    repo = RecordingResourceRepository(_resource())
    lease = RecordingLease()
    rows = [
        {
            "record_id": f"rec-{index}",
            "table_id": "tbl",
            "fields": {"标题": f"标题 {index}", "正文": "正文"},
        }
        for index in range(51)
    ]

    result = await FeishuBaseSourceProcessor(
        loader=lambda _context: {"app_token": "base-app", "sync_rows": rows},
        resource_repo=repo,
    ).sync(_context("feishu_base"), lease)

    assert result.status == "succeeded"
    assert result.created_count == 51
    assert lease.renewed == 3


@pytest.mark.asyncio
async def test_feishu_base_source_stops_before_next_chunk_after_lease_loss():
    repo = RecordingResourceRepository(_resource())
    rows = [
        {
            "record_id": f"rec-{index}",
            "table_id": "tbl",
            "fields": {"标题": f"标题 {index}", "正文": "正文"},
        }
        for index in range(51)
    ]

    with pytest.raises(RuntimeError, match="SOURCE_LEASE_LOST"):
        await FeishuBaseSourceProcessor(
            loader=lambda _context: {"app_token": "base-app", "sync_rows": rows},
            resource_repo=repo,
        ).sync(_context("feishu_base"), LosingLease())

    assert len(repo.upserts) == 25


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


def test_default_loaders_pass_actor_identity_not_bot(monkeypatch):
    """回归:默认 loader 必须用 actor 的身份(UAT)读飞书,而非 config=None 退回无 token 的 bot。

    之前 _default_base_loader/_default_wiki_loader 写死 config=None,导致 lark_cli 退回
    bot 身份,而 bot 无 access token → sync 读多维表失败、数据进不了库。
    """
    from data_foundation.sources import feishu as feishu_mod

    captured = {}

    def fake_read_xhs_data_func(config=None):
        captured["base_config"] = config
        return {"sync_rows": [], "app_token": "a", "table_id": "t"}

    def fake_read_wiki_func(config=None):
        captured["wiki_config"] = config
        return {"documents": [], "wiki_space_id": "s"}

    monkeypatch.setattr("tools.feishu_bitable.read_xhs_data.func", fake_read_xhs_data_func)
    monkeypatch.setattr("tools.feishu_wiki.read_feishu_wiki.func", fake_read_wiki_func)

    ctx = SourceContext(
        source=_source("feishu_base"),
        secrets=SourceSecrets(credentials={}),
        actor_open_id="ou_actor_123",
    )

    feishu_mod._default_base_loader(ctx)
    feishu_mod._default_wiki_loader(ctx)

    # 关键:传入的 config 不是 None,且携带 actor 身份(server_info.user.identity)
    from tools.runtime_identity import actor_open_id_from_config
    assert captured["base_config"] is not None
    assert actor_open_id_from_config(captured["base_config"]) == "ou_actor_123"
    assert captured["wiki_config"] is not None
    assert actor_open_id_from_config(captured["wiki_config"]) == "ou_actor_123"


def test_default_loaders_use_bot_when_as_bot(monkeypatch):
    """后台自动同步(as_bot=True)走 bot:loader 传 config=None(应用身份),不带用户 UAT。"""
    from data_foundation.sources import feishu as feishu_mod

    captured = {}

    def fake_read_xhs_data_func(config=None):
        captured["base_config"] = config
        return {"sync_rows": [], "app_token": "a", "table_id": "t"}

    def fake_read_wiki_func(config=None):
        captured["wiki_config"] = config
        return {"documents": [], "wiki_space_id": "s"}

    monkeypatch.setattr("tools.feishu_bitable.read_xhs_data.func", fake_read_xhs_data_func)
    monkeypatch.setattr("tools.feishu_wiki.read_feishu_wiki.func", fake_read_wiki_func)

    ctx = SourceContext(
        source=_source("feishu_base"),
        secrets=SourceSecrets(credentials={}),
        actor_open_id="scheduler-instance-xyz",  # 调度实例 ID,非真实用户
        as_bot=True,
    )

    feishu_mod._default_base_loader(ctx)
    feishu_mod._default_wiki_loader(ctx)

    # bot 身份:config=None,lark_cli 据此走 --as bot(应用凭证由 config.json 提供)
    assert captured["base_config"] is None
    assert captured["wiki_config"] is None
