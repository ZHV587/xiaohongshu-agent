from __future__ import annotations

from dataclasses import dataclass
import math
import os
from typing import Any

import httpx
from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.config import EmbeddingConfigSnapshot, embedding_snapshot, runtime_embedding_snapshot
from data_foundation.embedding_repository import EmbeddingRepository, VectorChunk
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


@dataclass(frozen=True)
class EmbeddingProviderConfig:
    base_url: str
    api_key: str
    model: str
    config_version: str
    dimensions: int = 1536
    timeout_seconds: float = 30.0
    batch_size: int = 64
    state: str = "enabled"
    reason_code: str | None = None


def embedding_config_from_env() -> EmbeddingProviderConfig | None:
    values = {
        "XHS_EMBEDDING_BASE_URL": os.environ.get("XHS_EMBEDDING_BASE_URL", ""),
        "XHS_EMBEDDING_API_KEY": os.environ.get("XHS_EMBEDDING_API_KEY", ""),
        "XHS_EMBEDDING_MODEL": os.environ.get("XHS_EMBEDDING_MODEL", ""),
        "XHS_EMBEDDING_DIMENSIONS": os.environ.get("XHS_EMBEDDING_DIMENSIONS", ""),
        "XHS_EMBEDDING_BATCH_SIZE": os.environ.get("XHS_EMBEDDING_BATCH_SIZE", ""),
        "XHS_EMBEDDING_TIMEOUT_SECONDS": os.environ.get("XHS_EMBEDDING_TIMEOUT_SECONDS", ""),
    }
    return embedding_config_from_snapshot(embedding_snapshot(
        values,
        version=os.environ.get("XHS_EMBEDDING_CONFIG_VERSION", "env").strip() or "env",
    ))


def embedding_config_from_runtime() -> EmbeddingProviderConfig | None:
    return embedding_config_from_snapshot(runtime_embedding_snapshot())


def embedding_config_from_snapshot(snapshot: EmbeddingConfigSnapshot) -> EmbeddingProviderConfig | None:
    if snapshot.state == "disabled":
        return None
    return EmbeddingProviderConfig(
        base_url=snapshot.base_url,
        api_key=snapshot.api_key,
        model=snapshot.model,
        config_version=snapshot.version,
        dimensions=snapshot.dimensions,
        timeout_seconds=snapshot.timeout_seconds,
        batch_size=snapshot.batch_size,
        state=snapshot.state,
        reason_code="EMBEDDING_CONFIG_INVALID" if snapshot.state == "misconfigured" else None,
    )


def chunk_text(text: str, *, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than zero")
    if overlap < 0 or overlap >= max_chars:
        raise ValueError("overlap must be zero or greater and smaller than max_chars")

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = end - overlap
    return chunks


class EmbeddingProcessor:
    topic = "embedding_generate"

    def __init__(
        self,
        conn: Connection,
        *,
        config: EmbeddingProviderConfig | None,
        transport: httpx.AsyncBaseTransport | None = None,
        max_chunk_chars: int = 2000,
        chunk_overlap: int = 200,
    ):
        # 不改写共享连接的 row_factory:连接在 db.connect() 已统一为 dict_row,
        # 改写共享连接会污染其它共用该连接的组件(见 processors/meili.py 注释)。
        self.conn = conn
        self.config = config
        self.transport = transport
        self.max_chunk_chars = max_chunk_chars
        self.chunk_overlap = chunk_overlap
        self.embedding_repo = EmbeddingRepository(conn)

    def state(self) -> ProcessorState:
        if self.config is None:
            return ProcessorState(
                topic=self.topic,
                status="disabled",
                config_version=None,
                reason_code="EMBEDDING_CONFIG_MISSING",
            )
        return ProcessorState(
            topic=self.topic,
            status="active" if self.config.state == "enabled" else self.config.state,
            config_version=self.config.config_version,
            reason_code=self.config.reason_code,
        )

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        if self.config is None:
            raise PermanentProcessingError("Embedding provider config is missing")

        payload = item.payload
        resource_id = str(payload.get("resource_id") or item.resource_id or "")
        resource_version = int(payload.get("version") or item.resource_version or 0)
        embedding_index_id = str(payload.get("embedding_index_id") or "")
        if not resource_id or resource_version <= 0 or not embedding_index_id:
            raise PermanentProcessingError("Embedding outbox payload is missing resource_id/version/index")

        job = self._load_current_job(
            tenant_id=item.tenant_id,
            resource_id=resource_id,
            resource_version=resource_version,
            embedding_index_id=embedding_index_id,
        )
        if job is None:
            return ProcessResult(status="superseded")
        if job["embedding_model"] != self.config.model:
            raise PermanentProcessingError("Embedding provider model does not match index profile")
        if int(job["dimensions"]) != self.config.dimensions:
            raise PermanentProcessingError("Embedding provider dimensions do not match index profile")
        payload_chunker_version = str(payload.get("chunker_version") or "")
        if payload_chunker_version and payload_chunker_version != job["chunker_version"]:
            raise PermanentProcessingError("Embedding payload chunker version does not match index profile")

        chunks = chunk_text(
            job["content_text"] or "",
            max_chars=self.max_chunk_chars,
            overlap=self.chunk_overlap,
        )
        if not chunks:
            raise PermanentProcessingError("Embedding resource has no embeddable text")

        embeddings = await self._embed(chunks)
        await lease.assert_owned()
        status = self.embedding_repo.store_batch(
            tenant_id=item.tenant_id,
            embedding_index_id=embedding_index_id,
            resource_id=resource_id,
            resource_version=resource_version,
            chunks=[
                VectorChunk(chunk_index=index, chunk_text=chunk, embedding=embedding)
                for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True))
            ],
        )
        if status == "stored":
            self.embedding_repo.activate_if_complete(
                embedding_index_id,
                tenant_id=item.tenant_id,
            )
        return ProcessResult(status="superseded" if status == "superseded" else "succeeded")

    def _load_current_job(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
        embedding_index_id: str,
    ) -> dict[str, Any] | None:
        with self.conn.cursor(row_factory=dict_row) as cur:
            row = cur.execute(
                """
                select rv.content_text,
                       idx.embedding_model,
                       idx.dimensions,
                       idx.chunker_version,
                       idx.config_version
                from resource_versions rv
                join resources r
                  on r.tenant_id = rv.tenant_id and r.id = rv.resource_id
                left join generated_copy_states gcs
                  on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
                join embedding_indexes idx
                  on idx.tenant_id = rv.tenant_id
                 and idx.id = %s
                where rv.tenant_id = %s
                  and rv.resource_id = %s
                  and rv.version = %s
                  and (
                    (r.type = 'generated_copy' and gcs.knowledge_target_version = rv.version)
                    or
                    (r.type <> 'generated_copy' and rv.version = (
                      select max(latest.version)
                      from resource_versions latest
                      where latest.tenant_id = rv.tenant_id
                        and latest.resource_id = rv.resource_id
                    ))
                  )
                """,
                (embedding_index_id, tenant_id, resource_id, resource_version),
            ).fetchone()
        return None if row is None else dict(row)

    async def _embed(self, chunks: list[str]) -> list[list[float]]:
        assert self.config is not None
        vectors: list[list[float] | None] = [None] * len(chunks)
        url = self.config.base_url.rstrip("/") + "/embeddings"
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=self.config.timeout_seconds,
        ) as client:
            for start in range(0, len(chunks), self.config.batch_size):
                batch = chunks[start:start + self.config.batch_size]
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.config.api_key}"},
                    json={
                        "model": self.config.model,
                        "input": batch,
                        "dimensions": self.config.dimensions,
                    },
                )
                if response.status_code in {401, 403}:
                    raise PermanentProcessingError(f"Embedding provider returned {response.status_code}")
                response.raise_for_status()
                for item in response.json().get("data", []):
                    index = start + int(item["index"])
                    embedding = [float(value) for value in item["embedding"]]
                    self._validate_embedding(embedding)
                    if index < start or index >= start + len(batch):
                        raise PermanentProcessingError("Embedding response index is out of range")
                    vectors[index] = embedding

        if any(vector is None for vector in vectors):
            raise PermanentProcessingError("Embedding response did not include all inputs")
        return [vector for vector in vectors if vector is not None]

    def _validate_embedding(self, embedding: list[float]) -> None:
        assert self.config is not None
        if len(embedding) != self.config.dimensions:
            raise PermanentProcessingError("Embedding response dimensions do not match config")
        if any(not math.isfinite(value) for value in embedding):
            raise PermanentProcessingError("Embedding response contains non-finite values")


__all__ = [
    "EmbeddingProcessor",
    "EmbeddingProviderConfig",
    "PermanentProcessingError",
    "chunk_text",
    "embedding_config_from_env",
    "embedding_config_from_runtime",
    "embedding_config_from_snapshot",
]
