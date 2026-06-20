from __future__ import annotations

from dataclasses import dataclass
import json

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.embedding_repository import EmbeddingRepository
from data_foundation.outbox_repository import OutboxRepository


@dataclass(frozen=True)
class EmbeddingIndexProfile:
    embedding_model: str
    config_version: str
    chunker_version: str


@dataclass(frozen=True)
class EmbeddingReconcileResult:
    embedding_index_id: str
    enqueued: int
    activated: bool


class EmbeddingIndexService:
    def __init__(self, conn: Connection, *, profile: EmbeddingIndexProfile):
        self.conn = conn
        self.conn.row_factory = dict_row
        self.profile = profile
        self.embedding_repo = EmbeddingRepository(conn)
        self.outbox_repo = OutboxRepository(conn)

    def reconcile_tenant(self, tenant_id: str) -> EmbeddingReconcileResult:
        current_resources = self._current_embeddable_resources(tenant_id)
        index = self.embedding_repo.create_index(
            tenant_id=tenant_id,
            embedding_model=self.profile.embedding_model,
            config_version=self.profile.config_version,
            chunker_version=self.profile.chunker_version,
            expected_resources=len(current_resources),
        )
        enqueued = 0
        for resource in current_resources:
            dedupe_key = self._dedupe_key(
                tenant_id=tenant_id,
                embedding_index_id=index.id,
                resource_id=resource["id"],
                resource_version=resource["version"],
            )
            before = self.conn.execute(
                """
                select id
                from resource_outbox
                where tenant_id = %s and dedupe_key = %s
                """,
                (tenant_id, dedupe_key),
            ).fetchone()
            self.outbox_repo.enqueue(
                tenant_id=tenant_id,
                topic="embedding_generate",
                dedupe_key=dedupe_key,
                payload={
                    "resource_id": str(resource["id"]),
                    "version": int(resource["version"]),
                    "embedding_index_id": index.id,
                    "chunker_version": self.profile.chunker_version,
                },
                resource_id=str(resource["id"]),
                resource_version=int(resource["version"]),
            )
            if before is None:
                enqueued += 1

        activated = index.status == "active" or self.embedding_repo.activate_if_complete(
            index.id,
            tenant_id=tenant_id,
        )
        return EmbeddingReconcileResult(index.id, enqueued=enqueued, activated=activated)

    def _current_embeddable_resources(self, tenant_id: str):
        return self.conn.execute(
            """
            select r.id::text as id, max(rv.version) as version
            from resources r
            join resource_versions rv
              on rv.tenant_id = r.tenant_id
             and rv.resource_id = r.id
            where r.tenant_id = %s
              and r.status = 'active'
              and nullif(trim(coalesce(r.content_text, '')), '') is not null
            group by r.id
            order by r.id
            """,
            (tenant_id,),
        ).fetchall()

    @staticmethod
    def _dedupe_key(
        *,
        tenant_id: str,
        embedding_index_id: str,
        resource_id: str,
        resource_version: int,
    ) -> str:
        return json.dumps(
            [
                tenant_id,
                "embedding_generate",
                embedding_index_id,
                resource_id,
                resource_version,
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
