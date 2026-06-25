from __future__ import annotations

import httpx
import pytest

from data_foundation.embedding_repository import EmbeddingRepository
from data_foundation.models import OutboxItem
from data_foundation.outbox_repository import OutboxRepository
from data_foundation.processors.base import LeaseGuard
from data_foundation.processors.embedding import (
    EmbeddingProcessor,
    EmbeddingProviderConfig,
    PermanentProcessingError,
    chunk_text,
    embedding_config_from_env,
)
from data_foundation.repositories.resource import ResourceRepository


def _embedding(first: float = 0.1) -> list[float]:
    return [first] + [0.0] * 1535


def _resource(conn, *, tenant_id: str = "tenant-a", content: str = "第一段内容\n第二段内容"):
    return ResourceRepository(conn).upsert_resource(
        tenant_id=tenant_id,
        actor_open_id="ou_owner",
        resource_type="doc",
        title="文档",
        content_text=content,
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "test", "external_type": "doc", "external_id": tenant_id},
    )


def _item(resource, *, index_id: str) -> OutboxItem:
    return OutboxItem(
        id="00000000-0000-0000-0000-000000000001",
        tenant_id=resource.tenant_id,
        resource_id=resource.id,
        resource_version=resource.version,
        topic="embedding_generate",
        dedupe_key="key",
        payload={
            "resource_id": resource.id,
            "version": resource.version,
            "embedding_index_id": index_id,
            "chunker_version": "text-v1",
        },
        status="processing",
        attempts=1,
        next_attempt_at=None,
        lease_owner="worker-a",
        lease_expires_at=None,
        error_code=None,
        error_summary=None,
        dead_at=None,
        created_at=None,
        updated_at=None,
    )


def _config() -> EmbeddingProviderConfig:
    return EmbeddingProviderConfig(
        base_url="https://embedding.example/v1",
        api_key="secret",
        model="model-a",
        config_version="cfg-a",
        dimensions=1536,
        timeout_seconds=5.0,
        batch_size=8,
    )


class _LeaseRepo:
    def __init__(self):
        self.renewed = 0

    def renew(self, **_kwargs):
        self.renewed += 1
        return True


def test_chunk_text_is_deterministic_and_overlaps():
    chunks = chunk_text("abcdef", max_chars=4, overlap=2)

    assert chunks == ["abcd", "cdef"]
    assert chunk_text("abcdef", max_chars=4, overlap=2) == chunks


@pytest.mark.asyncio
async def test_embedding_processor_posts_openai_compatible_request_and_stores_chunks(migrated_conn):
    resource = _resource(migrated_conn, content="露营装备清单")
    index = EmbeddingRepository(migrated_conn).create_index(
        tenant_id=resource.tenant_id,
        embedding_model="model-a",
        config_version="cfg-a",
        chunker_version="text-v1",
        expected_resources=1,
    )
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = request.read().decode("utf-8")
        assert '"model":"model-a"' in body
        assert '"input":["露营装备清单"]' in body
        assert '"dimensions":1536' in body
        assert request.headers["authorization"] == "Bearer secret"
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": _embedding(0.9)}]})

    transport = httpx.MockTransport(handler)
    lease_repo = _LeaseRepo()
    processor = EmbeddingProcessor(migrated_conn, config=_config(), transport=transport)
    result = await processor.process(
        _item(resource, index_id=index.id),
        LeaseGuard(
            lease_repo,
            item_id="00000000-0000-0000-0000-000000000001",
            tenant_id=resource.tenant_id,
            lease_owner="worker-a",
            lease_seconds=60,
        ),
    )

    assert result.status == "succeeded"
    assert lease_repo.renewed == 1
    assert len(requests) == 1
    row = migrated_conn.execute(
        "select chunk_text, embedding_model from resource_embeddings where resource_id = %s",
        (resource.id,),
    ).fetchone()
    assert row["chunk_text"] == "露营装备清单"
    assert row["embedding_model"] == "model-a"
    assert migrated_conn.execute(
        "select status from embedding_indexes where id = %s",
        (index.id,),
    ).fetchone()["status"] == "active"


@pytest.mark.asyncio
async def test_embedding_processor_reorders_response_by_index(migrated_conn):
    resource = _resource(migrated_conn, content="abcdef", tenant_id="tenant-b")
    index = EmbeddingRepository(migrated_conn).create_index(
        tenant_id=resource.tenant_id,
        embedding_model="model-a",
        config_version="cfg-a",
        chunker_version="text-v1",
        expected_resources=1,
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": _embedding(0.2)},
                    {"index": 0, "embedding": _embedding(0.1)},
                ]
            },
        )

    processor = EmbeddingProcessor(
        migrated_conn,
        config=_config(),
        transport=httpx.MockTransport(handler),
        max_chunk_chars=4,
        chunk_overlap=2,
    )
    await processor.process(_item(resource, index_id=index.id), LeaseGuard(_LeaseRepo(), item_id="1", tenant_id=resource.tenant_id, lease_owner="worker-a", lease_seconds=60))

    rows = migrated_conn.execute(
        "select chunk_index, chunk_text from resource_embeddings where resource_id = %s order by chunk_index",
        (resource.id,),
    ).fetchall()
    assert [(row["chunk_index"], row["chunk_text"]) for row in rows] == [(0, "abcd"), (1, "cdef")]


@pytest.mark.asyncio
async def test_embedding_processor_rejects_dimension_mismatch_without_writing(migrated_conn):
    resource = _resource(migrated_conn, tenant_id="tenant-c")
    index = EmbeddingRepository(migrated_conn).create_index(
        tenant_id=resource.tenant_id,
        embedding_model="model-a",
        config_version="cfg-a",
        chunker_version="text-v1",
        expected_resources=1,
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1]}]})

    processor = EmbeddingProcessor(migrated_conn, config=_config(), transport=httpx.MockTransport(handler))

    with pytest.raises(PermanentProcessingError, match="dimensions"):
        await processor.process(_item(resource, index_id=index.id), LeaseGuard(_LeaseRepo(), item_id="1", tenant_id=resource.tenant_id, lease_owner="worker-a", lease_seconds=60))

    assert migrated_conn.execute("select count(*) as count from resource_embeddings").fetchone()["count"] == 0


@pytest.mark.asyncio
async def test_embedding_processor_returns_superseded_without_calling_provider_for_stale_item(migrated_conn):
    resource = _resource(migrated_conn, tenant_id="tenant-d")
    updated = ResourceRepository(migrated_conn).upsert_resource(
        tenant_id=resource.tenant_id,
        actor_open_id="ou_owner",
        resource_type="doc",
        title="文档新版",
        content_text="新版",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "test", "external_type": "doc", "external_id": resource.tenant_id},
    )
    index = EmbeddingRepository(migrated_conn).create_index(
        tenant_id=resource.tenant_id,
        embedding_model="model-a",
        config_version="cfg-a",
        chunker_version="text-v1",
        expected_resources=1,
    )
    item = _item(resource, index_id=index.id)
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": _embedding()}]})

    result = await EmbeddingProcessor(
        migrated_conn,
        config=_config(),
        transport=httpx.MockTransport(handler),
    ).process(item, LeaseGuard(_LeaseRepo(), item_id="1", tenant_id=resource.tenant_id, lease_owner="worker-a", lease_seconds=60))

    assert updated.version == resource.version + 1
    assert result.status == "superseded"
    assert calls == 0


@pytest.mark.asyncio
async def test_embedding_processor_treats_unauthorized_provider_as_permanent(migrated_conn):
    resource = _resource(migrated_conn, tenant_id="tenant-e")
    index = EmbeddingRepository(migrated_conn).create_index(
        tenant_id=resource.tenant_id,
        embedding_model="model-a",
        config_version="cfg-a",
        chunker_version="text-v1",
        expected_resources=1,
    )

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with pytest.raises(PermanentProcessingError, match="401"):
        await EmbeddingProcessor(
            migrated_conn,
            config=_config(),
            transport=httpx.MockTransport(handler),
        ).process(_item(resource, index_id=index.id), LeaseGuard(_LeaseRepo(), item_id="1", tenant_id=resource.tenant_id, lease_owner="worker-a", lease_seconds=60))


@pytest.mark.asyncio
async def test_embedding_processor_rejects_chunker_mismatch_without_calling_provider(migrated_conn):
    resource = _resource(migrated_conn, tenant_id="tenant-f")
    index = EmbeddingRepository(migrated_conn).create_index(
        tenant_id=resource.tenant_id,
        embedding_model="model-a",
        config_version="cfg-a",
        chunker_version="text-v2",
        expected_resources=1,
    )
    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": _embedding()}]})

    with pytest.raises(PermanentProcessingError, match="chunker"):
        await EmbeddingProcessor(
            migrated_conn,
            config=_config(),
            transport=httpx.MockTransport(handler),
        ).process(_item(resource, index_id=index.id), LeaseGuard(_LeaseRepo(), item_id="1", tenant_id=resource.tenant_id, lease_owner="worker-a", lease_seconds=60))

    assert calls == 0


def test_embedding_processor_state_is_disabled_without_config(migrated_conn):
    state = EmbeddingProcessor(migrated_conn, config=None).state()

    assert state.status == "disabled"
    assert state.reason_code == "EMBEDDING_CONFIG_MISSING"


def test_embedding_processor_state_is_active_for_enabled_config(migrated_conn):
    state = EmbeddingProcessor(migrated_conn, config=_config()).state()

    assert state.status == "active"
    assert state.config_version == "cfg-a"
    assert state.reason_code is None


def test_embedding_processor_state_is_misconfigured_for_invalid_config(migrated_conn):
    state = EmbeddingProcessor(
        migrated_conn,
        config=EmbeddingProviderConfig(
            base_url="https://embedding.example/v1",
            api_key="embedding-key",
            model="embedding-model",
            config_version="cfg-invalid",
            dimensions=3072,
            state="misconfigured",
            reason_code="EMBEDDING_CONFIG_INVALID",
        ),
    ).state()

    assert state.status == "misconfigured"
    assert state.config_version == "cfg-invalid"
    assert state.reason_code == "EMBEDDING_CONFIG_INVALID"


def test_embedding_config_from_env_uses_only_explicit_embedding_values(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "must-not-be-used")
    monkeypatch.setenv("LLM_BASE_URL", "https://chat.example/v1")
    monkeypatch.delenv("XHS_EMBEDDING_API_KEY", raising=False)

    assert embedding_config_from_env() is None

    monkeypatch.setenv("XHS_EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("XHS_EMBEDDING_BASE_URL", "https://embedding.example/v1")
    monkeypatch.setenv("XHS_EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("XHS_EMBEDDING_CONFIG_VERSION", "cfg-1")
    monkeypatch.setenv("XHS_EMBEDDING_BATCH_SIZE", "3")
    monkeypatch.setenv("XHS_EMBEDDING_TIMEOUT_SECONDS", "7")

    config = embedding_config_from_env()

    assert config == EmbeddingProviderConfig(
        base_url="https://embedding.example/v1",
        api_key="embedding-key",
        model="embedding-model",
        config_version="cfg-1",
        dimensions=1536,
        timeout_seconds=7.0,
        batch_size=3,
    )


def test_embedding_config_from_env_marks_invalid_values_misconfigured(monkeypatch):
    monkeypatch.setenv("XHS_EMBEDDING_API_KEY", "embedding-key")
    monkeypatch.setenv("XHS_EMBEDDING_BASE_URL", "https://embedding.example/v1")
    monkeypatch.setenv("XHS_EMBEDDING_MODEL", "embedding-model")
    monkeypatch.setenv("XHS_EMBEDDING_DIMENSIONS", "3072")
    monkeypatch.setenv("XHS_EMBEDDING_CONFIG_VERSION", "cfg-invalid")
    monkeypatch.delenv("XHS_EMBEDDING_BATCH_SIZE", raising=False)
    monkeypatch.delenv("XHS_EMBEDDING_TIMEOUT_SECONDS", raising=False)

    config = embedding_config_from_env()

    assert config == EmbeddingProviderConfig(
        base_url="https://embedding.example/v1",
        api_key="embedding-key",
        model="embedding-model",
        config_version="cfg-invalid",
        dimensions=3072,
        state="misconfigured",
        reason_code="EMBEDDING_CONFIG_INVALID",
    )
