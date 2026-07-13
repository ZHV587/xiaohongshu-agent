from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Literal

from psycopg import Connection

from data_foundation.db import transaction
from data_foundation.models import EmbeddingIndex


@dataclass(frozen=True)
class VectorChunk:
    chunk_index: int
    chunk_text: str
    embedding: list[float]


class EmbeddingRepository:
    def __init__(self, conn: Connection):
        # 连接在 db.connect() 已统一为 dict_row(单一事实源);不改写共享连接的 row_factory,
        # 避免污染其它共用该连接的组件(见 processors/meili.py 注释)。
        self.conn = conn

    def create_index(
        self,
        *,
        tenant_id: str,
        embedding_model: str,
        config_version: str,
        chunker_version: str,
        expected_resources: int,
    ) -> EmbeddingIndex:
        row = self.conn.execute(
            """
            insert into embedding_indexes (
              tenant_id, embedding_model, config_version, dimensions,
              chunker_version, expected_resources
            )
            values (%s, %s, %s, 1536, %s, %s)
            on conflict(tenant_id, embedding_model, config_version, chunker_version)
            do update set expected_resources = excluded.expected_resources,
                          updated_at = now()
            returning *
            """,
            (tenant_id, embedding_model, config_version, chunker_version, expected_resources),
        ).fetchone()
        self.conn.commit()
        return self._index_from_row(row)

    def active_index(self, tenant_id: str) -> EmbeddingIndex | None:
        row = self.conn.execute(
            """
            select *
            from embedding_indexes
            where tenant_id = %s and status = 'active'
            order by activated_at desc, created_at desc
            limit 1
            """,
            (tenant_id,),
        ).fetchone()
        return None if row is None else self._index_from_row(row)

    def store_batch(
        self,
        *,
        tenant_id: str,
        embedding_index_id: str,
        resource_id: str,
        resource_version: int,
        chunks: list[VectorChunk],
    ) -> Literal["stored", "superseded"]:
        prepared = [
            (
                chunk.chunk_index,
                chunk.chunk_text,
                self._vector_literal(chunk.embedding),
            )
            for chunk in chunks
        ]
        if any(chunk_index < 0 for chunk_index, _, _ in prepared):
            raise ValueError("Chunk index must be zero or greater")

        with transaction(self.conn):
            resource = self.conn.execute(
                """
                select id
                from resources
                where tenant_id = %s and id = %s
                for update
                """,
                (tenant_id, resource_id),
            ).fetchone()
            if resource is None:
                raise PermissionError("Resource not found for tenant")

            index = self.conn.execute(
                """
                select *
                from embedding_indexes
                where tenant_id = %s and id = %s
                for update
                """,
                (tenant_id, embedding_index_id),
            ).fetchone()
            if index is None:
                raise PermissionError("Embedding index not found for tenant")

            target = self.conn.execute(
                """
                select case
                         when r.type = 'generated_copy' then gcs.knowledge_target_version
                         else (select max(rv.version) from resource_versions rv
                               where rv.tenant_id = r.tenant_id and rv.resource_id = r.id)
                       end as version
                from resources r
                left join generated_copy_states gcs
                  on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
                where r.tenant_id = %s and r.id = %s
                """,
                (tenant_id, resource_id),
            ).fetchone()
            if target is None or target["version"] is None:
                return "superseded"
            if int(target["version"]) != int(resource_version):
                return "superseded"

            self.conn.execute(
                """
                delete from resource_embeddings
                where tenant_id = %s
                  and embedding_index_id = %s
                  and resource_id = %s
                  and resource_version = %s
                """,
                (tenant_id, embedding_index_id, resource_id, resource_version),
            )
            if prepared:
                with self.conn.cursor() as cursor:
                    cursor.executemany(
                        """
                        insert into resource_embeddings (
                          tenant_id, resource_id, resource_version, embedding_index_id,
                          chunk_index, chunk_text, chunker_version, embedding_model, embedding
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s::public.vector)
                        """,
                        [
                            (
                                tenant_id,
                                resource_id,
                                resource_version,
                                embedding_index_id,
                                chunk_index,
                                chunk_text,
                                index["chunker_version"],
                                index["embedding_model"],
                                vector_literal,
                            )
                            for chunk_index, chunk_text, vector_literal in prepared
                        ],
                    )
            self._recount_index(embedding_index_id, tenant_id=tenant_id)
        return "stored"

    def activate_if_complete(self, index_id: str, *, tenant_id: str) -> bool:
        with transaction(self.conn):
            self.conn.execute(
                """
                select id
                from resources
                where tenant_id = %s
                order by id
                for update
                """,
                (tenant_id,),
            ).fetchall()
            self.conn.execute(
                """
                select id
                from embedding_indexes
                where tenant_id = %s
                order by created_at, id
                for update
                """,
                (tenant_id,),
            ).fetchall()
            index = self.conn.execute(
                """
                select *
                from embedding_indexes
                where tenant_id = %s and id = %s
                for update
                """,
                (tenant_id, index_id),
            ).fetchone()
            if index is None:
                raise PermissionError("Embedding index not found for tenant")
            self._recount_index(index_id, tenant_id=tenant_id)
            index = self.conn.execute(
                """
                select *
                from embedding_indexes
                where tenant_id = %s and id = %s
                for update
                """,
                (tenant_id, index_id),
            ).fetchone()
            if (
                index["failed_resources"] != 0
                or index["completed_resources"] != index["expected_resources"]
            ):
                return False

            self.conn.execute(
                """
                update embedding_indexes
                set status = 'retired', updated_at = now()
                where tenant_id = %s and status = 'active' and id <> %s
                """,
                (tenant_id, index_id),
            )
            self.conn.execute(
                """
                update embedding_indexes
                set status = 'active',
                    activated_at = coalesce(activated_at, now()),
                    updated_at = now()
                where tenant_id = %s and id = %s
                """,
                (tenant_id, index_id),
            )
        return True

    def recount_index(self, index_id: str, *, tenant_id: str) -> EmbeddingIndex:
        with transaction(self.conn):
            self.conn.execute(
                """
                select id
                from resources
                where tenant_id = %s
                order by id
                for update
                """,
                (tenant_id,),
            ).fetchall()
            index = self.conn.execute(
                """
                select *
                from embedding_indexes
                where tenant_id = %s and id = %s
                for update
                """,
                (tenant_id, index_id),
            ).fetchone()
            if index is None:
                raise PermissionError("Embedding index not found for tenant")
            self._recount_index(index_id, tenant_id=tenant_id)
            row = self.conn.execute(
                """
                select *
                from embedding_indexes
                where tenant_id = %s and id = %s
                """,
                (tenant_id, index_id),
            ).fetchone()
        return self._index_from_row(row)

    def _recount_index(self, index_id: str, *, tenant_id: str) -> None:
        self.conn.execute(
            """
            with version_targets as (
              select r.id, r.tenant_id,
                     case when r.type = 'generated_copy'
                          then gcs.knowledge_target_version
                          else max(rv.version)
                     end as resource_version
              from resources r
              join resource_versions rv
                on rv.tenant_id = r.tenant_id
               and rv.resource_id = r.id
              left join generated_copy_states gcs
                on gcs.tenant_id = r.tenant_id and gcs.resource_id = r.id
              where r.tenant_id = %s
                and r.status = 'active'
              group by r.id, r.tenant_id, r.type, gcs.knowledge_target_version
            ), current_resources as (
              select vt.id, vt.resource_version
              from version_targets vt
              join resource_versions target_rv
                on target_rv.tenant_id = vt.tenant_id
               and target_rv.resource_id = vt.id
               and target_rv.version = vt.resource_version
              where vt.resource_version is not null
                and nullif(trim(coalesce(target_rv.content_text, '')), '') is not null
            ), counts as (
              select count(*)::int as expected_resources,
                     count(*) filter (
                       where exists (
                         select 1
                         from resource_embeddings re
                         where re.tenant_id = %s
                           and re.embedding_index_id = %s
                           and re.resource_id = current_resources.id
                           and re.resource_version = current_resources.resource_version
                       )
                     )::int as completed_resources
              from current_resources
            )
            update embedding_indexes ei
            set expected_resources = counts.expected_resources,
                completed_resources = counts.completed_resources,
                updated_at = now()
            from counts
            where ei.tenant_id = %s and ei.id = %s
            """,
            (
                tenant_id,
                tenant_id,
                index_id,
                tenant_id,
                index_id,
            ),
        )

    @staticmethod
    def _vector_literal(embedding: list[float]) -> str:
        if len(embedding) != 1536:
            raise ValueError("Embedding must contain exactly 1536 finite numbers")
        values = []
        for value in embedding:
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError("Embedding must contain exactly 1536 finite numbers") from exc
            if not math.isfinite(number):
                raise ValueError("Embedding must contain exactly 1536 finite numbers")
            values.append(str(number))
        return "[" + ",".join(values) + "]"

    @staticmethod
    def _index_from_row(row: Any) -> EmbeddingIndex:
        return EmbeddingIndex(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            embedding_model=row["embedding_model"],
            config_version=row["config_version"],
            dimensions=row["dimensions"],
            chunker_version=row["chunker_version"],
            status=row["status"],
            expected_resources=row["expected_resources"],
            completed_resources=row["completed_resources"],
            failed_resources=row["failed_resources"],
            activated_at=row["activated_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
