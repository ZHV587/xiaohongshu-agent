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

    def discover_reconcile_tenants(self, *, limit: int) -> list[str]:
        rows = self.conn.execute(
            """
            with current_resources as (
              select r.tenant_id, r.id, max(rv.version) as version
              from resources r
              join resource_versions rv
                on rv.tenant_id = r.tenant_id
               and rv.resource_id = r.id
              where r.status = 'active'
                and nullif(trim(coalesce(r.content_text, '')), '') is not null
              group by r.tenant_id, r.id
            ), current_counts as (
              select tenant_id, count(*)::int as expected_resources
              from current_resources
              group by tenant_id
            ), matching_indexes as (
              select *
              from embedding_indexes
              where embedding_model = %s
                and config_version = %s
                and chunker_version = %s
                and status in ('active', 'building')
            ), missing_resources as (
              select distinct cr.tenant_id
              from current_resources cr
              where not exists (
                select 1
                from matching_indexes ei
                join resource_embeddings re
                  on re.tenant_id = ei.tenant_id
                 and re.embedding_index_id = ei.id
                 and re.resource_id = cr.id
                 and re.resource_version = cr.version
                where ei.tenant_id = cr.tenant_id
              )
            ), stale_indexes as (
              select distinct ei.tenant_id
              from matching_indexes ei
              left join current_counts cc on cc.tenant_id = ei.tenant_id
              where ei.expected_resources <> coalesce(cc.expected_resources, 0)
                 or ei.completed_resources <> (
                   select count(*)::int
                   from current_resources cr
                   where cr.tenant_id = ei.tenant_id
                     and exists (
                       select 1
                       from resource_embeddings re
                       where re.tenant_id = ei.tenant_id
                         and re.embedding_index_id = ei.id
                         and re.resource_id = cr.id
                         and re.resource_version = cr.version
                     )
                 )
            )
            select tenant_id from missing_resources
            union
            select tenant_id from stale_indexes
            order by tenant_id
            limit %s
            """,
            (
                self.profile.embedding_model,
                self.profile.config_version,
                self.profile.chunker_version,
                max(1, min(limit, 100)),
            ),
        ).fetchall()
        return [row["tenant_id"] for row in rows]

    def reconcile_tenant(self, tenant_id: str) -> EmbeddingReconcileResult:
        current_resources = self._current_embeddable_resources(tenant_id)
        index = self.embedding_repo.create_index(
            tenant_id=tenant_id,
            embedding_model=self.profile.embedding_model,
            config_version=self.profile.config_version,
            chunker_version=self.profile.chunker_version,
            expected_resources=len(current_resources),
        )
        index = self.embedding_repo.recount_index(index.id, tenant_id=tenant_id)
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

        if index.status == "active":
            activated = True
        else:
            activated = self.embedding_repo.activate_if_complete(index.id, tenant_id=tenant_id)
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
