from __future__ import annotations

import hashlib
import json
import math
from contextlib import AbstractContextManager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.db import transaction
from data_foundation.models import Resource
from data_foundation.permissions import readable_resource_where


class ResourceRepository:
    def __init__(self, conn: Connection):
        self.conn = conn
        self.conn.row_factory = dict_row

    def unit_of_work(self) -> AbstractContextManager[Connection]:
        return transaction(self.conn)

    def upsert_resource(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_type: str,
        title: str,
        content_text: str | None,
        content_json: dict[str, Any],
        visibility: str,
        owner_open_id: str | None,
        summary: str | None = None,
        mapping: dict[str, Any] | None = None,
        outbox_topics: list[str] | None = None,
    ) -> Resource:
        payload_json = json.dumps(content_json, sort_keys=True, ensure_ascii=False)
        content_hash = hashlib.sha256(f"{content_text or ''}\n{payload_json}".encode("utf-8")).hexdigest()
        topics = outbox_topics or []

        with transaction(self.conn):
            self._lock_mapping(tenant_id, mapping)
            resource_id = self._resource_id_for_mapping(tenant_id, mapping)
            if resource_id is None:
                row = self.conn.execute(
                    """
                    insert into resources (
                      tenant_id, type, title, summary, content_text, content_json,
                      visibility, owner_open_id
                    )
                    values (%s, %s, %s, %s, %s, %s::jsonb, %s, %s)
                    returning *
                    """,
                    (
                        tenant_id,
                        resource_type,
                        title,
                        summary,
                        content_text,
                        payload_json,
                        visibility,
                        owner_open_id,
                    ),
                ).fetchone()
            else:
                current = self.conn.execute(
                    "select * from resources where id = %s and tenant_id = %s for update",
                    (resource_id, tenant_id),
                ).fetchone()
                if current is None:
                    raise PermissionError("Resource mapping points to another tenant")
                latest = self._latest_version(resource_id)
                if self._resource_is_unchanged(
                    current,
                    latest,
                    resource_type=resource_type,
                    title=title,
                    summary=summary,
                    content_text=content_text,
                    content_json=content_json,
                    content_hash=content_hash,
                    visibility=visibility,
                    owner_open_id=owner_open_id,
                ):
                    if mapping is not None:
                        self._upsert_mapping(tenant_id=tenant_id, resource_id=resource_id, mapping=mapping)
                    return self._resource_from_row(current, version=latest["version"])
                row = self.conn.execute(
                    """
                    update resources
                    set type = %s,
                        title = %s,
                        summary = %s,
                        content_text = %s,
                        content_json = %s::jsonb,
                        visibility = %s,
                        owner_open_id = %s,
                        updated_at = now()
                    where id = %s and tenant_id = %s
                    returning *
                    """,
                    (
                        resource_type,
                        title,
                        summary,
                        content_text,
                        payload_json,
                        visibility,
                        owner_open_id,
                        resource_id,
                        tenant_id,
                    ),
                ).fetchone()
                if row is None:
                    raise PermissionError("Resource mapping points to another tenant")

            version = self._next_version(row["id"])
            self.conn.execute(
                """
                insert into resource_versions (
                  resource_id, version, content_hash, content_text, content_json, changed_by
                )
                values (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (row["id"], version, content_hash, content_text, payload_json, actor_open_id),
            )

            event = self.conn.execute(
                """
                insert into resource_events (tenant_id, resource_id, event_type, actor_open_id, payload)
                values (%s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                (
                    tenant_id,
                    row["id"],
                    "updated" if version > 1 else "imported",
                    actor_open_id,
                    json.dumps({"version": version}, sort_keys=True),
                ),
            ).fetchone()

            if mapping is not None:
                self._upsert_mapping(tenant_id=tenant_id, resource_id=row["id"], mapping=mapping)

            for topic in topics:
                self.conn.execute(
                    """
                    insert into resource_outbox (tenant_id, resource_id, event_id, topic, payload)
                    values (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        tenant_id,
                        row["id"],
                        event["id"],
                        topic,
                        json.dumps({"resource_id": str(row["id"]), "version": version}, sort_keys=True),
                    ),
                )

        return self._resource_from_row(row, version=version)

    def get_resource(self, tenant_id: str, actor_open_id: str, resource_id: str) -> Resource | None:
        row = self.conn.execute(
            f"""
            select r.*,
                   (
                     select max(rv.version)
                     from resource_versions rv
                     where rv.resource_id = r.id
                   ) as version
            from resources r
            where r.id = %(resource_id)s
              and {readable_resource_where("r")}
            """,
            {"tenant_id": tenant_id, "actor_open_id": actor_open_id, "resource_id": resource_id},
        ).fetchone()
        if row is None:
            return None
        return self._resource_from_row(row, version=row["version"])

    def grant_permission(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        subject_type: str,
        subject_id: str,
        permission: str,
    ) -> None:
        self.conn.execute(
            """
            insert into resource_permissions (tenant_id, resource_id, subject_type, subject_id, permission)
            values (%s, %s, %s, %s, %s)
            on conflict(resource_id, subject_type, subject_id, permission) do nothing
            """,
            (tenant_id, resource_id, subject_type, subject_id, permission),
        )
        self.conn.commit()

    def debug_counts(self) -> dict[str, int]:
        tables = [
            "resources",
            "resource_versions",
            "resource_events",
            "resource_mappings",
            "resource_outbox",
            "resource_permissions",
        ]
        return {
            table: self.conn.execute(f"select count(*) as count from {table}").fetchone()["count"]
            for table in tables
        }

    def replace_embedding_chunks(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        chunks: list[str],
        embedding_model: str = "pending",
    ) -> None:
        with transaction(self.conn):
            resource = self.conn.execute(
                "select id from resources where id = %s and tenant_id = %s for update",
                (resource_id, tenant_id),
            ).fetchone()
            if resource is None:
                raise PermissionError("Resource is not writable in this tenant")
            current_model = self.conn.execute(
                """
                select embedding_model
                from resource_embeddings
                where resource_id = %s
                order by (embedding_model = 'pending') desc, created_at desc
                limit 1
                """,
                (resource_id,),
            ).fetchone()
            if current_model is not None:
                current_chunks = self.conn.execute(
                    """
                    select chunk_text
                    from resource_embeddings
                    where resource_id = %s and embedding_model = %s
                    order by chunk_index
                    """,
                    (resource_id, current_model["embedding_model"]),
                ).fetchall()
                if [row["chunk_text"] for row in current_chunks] == chunks:
                    return
            elif not chunks:
                return
            self.conn.execute("delete from resource_embeddings where resource_id = %s", (resource_id,))
            self.conn.executemany(
                """
                insert into resource_embeddings (resource_id, chunk_index, chunk_text, embedding_model)
                values (%s, %s, %s, %s)
                """,
                [
                    (resource_id, chunk_index, chunk_text, embedding_model)
                    for chunk_index, chunk_text in enumerate(chunks)
                ],
            )

    def keyword_rows(self, *, tenant_id: str, actor_open_id: str, query: str, limit: int):
        return self.conn.execute(
            f"""
            select r.*,
                   greatest(
                     ts_rank(
                       to_tsvector('simple', coalesce(r.title, '') || ' ' || coalesce(r.summary, '') || ' ' || coalesce(r.content_text, '')),
                       plainto_tsquery('simple', %(query)s)
                     ),
                     case when coalesce(r.title, '') || ' ' || coalesce(r.summary, '') || ' ' || coalesce(r.content_text, '')
                               ilike '%%' || %(query)s || '%%' then 1.0 else 0.0 end
                   ) as score
            from resources r
            where {readable_resource_where('r')}
              and (
                to_tsvector('simple', coalesce(r.title, '') || ' ' || coalesce(r.summary, '') || ' ' || coalesce(r.content_text, ''))
                  @@ plainto_tsquery('simple', %(query)s)
                or coalesce(r.title, '') || ' ' || coalesce(r.summary, '') || ' ' || coalesce(r.content_text, '')
                  ilike '%%' || %(query)s || '%%'
              )
            order by score desc, r.updated_at desc
            limit %(limit)s
            """,
            {"tenant_id": tenant_id, "actor_open_id": actor_open_id, "query": query, "limit": limit},
        ).fetchall()

    def set_embedding(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        chunk_index: int,
        chunk_text: str,
        embedding: list[float],
        embedding_model: str,
    ) -> None:
        if chunk_index < 0:
            raise ValueError("Chunk index must be zero or greater")
        embedding_model = embedding_model.strip()
        if not embedding_model:
            raise ValueError("Embedding model is required")
        vector_literal = self._vector_literal(embedding)
        with transaction(self.conn):
            resource = self.conn.execute(
                "select id from resources where id = %s and tenant_id = %s for update",
                (resource_id, tenant_id),
            ).fetchone()
            if resource is None:
                raise PermissionError("Resource is not writable in this tenant")
            self.conn.execute(
                """
                insert into resource_embeddings (resource_id, chunk_index, chunk_text, embedding, embedding_model)
                values (%s, %s, %s, %s::vector, %s)
                on conflict(resource_id, chunk_index, embedding_model)
                do update set chunk_text = excluded.chunk_text, embedding = excluded.embedding
                """,
                (resource_id, chunk_index, chunk_text, vector_literal, embedding_model),
            )

    def semantic_rows(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        embedding: list[float],
        embedding_model: str,
        top_k: int,
    ):
        embedding_model = embedding_model.strip()
        if not embedding_model:
            raise ValueError("Embedding model is required")
        vector_literal = self._vector_literal(embedding)
        return self.conn.execute(
            f"""
            with candidates as (
              select r.*, e.chunk_index, e.chunk_text,
                     1 - (e.embedding <=> %(embedding)s::vector) as score,
                     row_number() over (
                       partition by r.id
                       order by e.embedding <=> %(embedding)s::vector, e.chunk_index
                     ) as resource_rank
              from resource_embeddings e
              join resources r on r.id = e.resource_id
              where e.embedding_model = %(embedding_model)s
                and e.embedding is not null
                and {readable_resource_where('r')}
            )
            select * from candidates
            where resource_rank = 1
            order by score desc, updated_at desc
            limit %(top_k)s
            """,
            {
                "tenant_id": tenant_id,
                "actor_open_id": actor_open_id,
                "embedding": vector_literal,
                "embedding_model": embedding_model,
                "top_k": top_k,
            },
        ).fetchall()

    def add_edge(
        self,
        *,
        tenant_id: str,
        source_resource_id: str,
        target_resource_id: str,
        edge_type: str,
        weight: float = 1.0,
    ) -> None:
        edge_type = edge_type.strip()
        if not edge_type:
            raise ValueError("Edge type is required")
        if not math.isfinite(float(weight)):
            raise ValueError("Edge weight must be finite")
        endpoint_ids = list({source_resource_id, target_resource_id})
        with transaction(self.conn):
            endpoints = self.conn.execute(
                "select count(*) as count from resources where tenant_id = %s and id = any(%s::uuid[])",
                (tenant_id, endpoint_ids),
            ).fetchone()
            if endpoints["count"] != len(endpoint_ids):
                raise PermissionError("Both edge endpoints must belong to this tenant")
            self.conn.execute(
                """
                insert into resource_edges (tenant_id, source_resource_id, target_resource_id, edge_type, weight)
                values (%s, %s, %s, %s, %s)
                on conflict(source_resource_id, target_resource_id, edge_type)
                do update set weight = excluded.weight
                """,
                (tenant_id, source_resource_id, target_resource_id, edge_type, weight),
            )

    def graph_rows(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_ids: list[str],
        hops: int,
        edge_types: list[str] | None,
    ):
        return self.conn.execute(
            f"""
            with recursive visible as materialized (
              select r.id, r.title, r.type
              from resources r
              where {readable_resource_where('r')}
            ),
            starts as (
              select v.id, v.title, v.type
              from visible v
              where v.id = any(%(resource_ids)s::uuid[])
            ),
            walk(source_id, target_id, edge_type, weight, depth, path) as (
              select e.source_resource_id, e.target_resource_id, e.edge_type, e.weight, 1,
                     array[e.source_resource_id, e.target_resource_id]
              from resource_edges e
              join starts s on s.id = e.source_resource_id
              join visible target on target.id = e.target_resource_id
              where e.tenant_id = %(tenant_id)s
                and (%(edge_types)s::text[] is null or e.edge_type = any(%(edge_types)s::text[]))
              union all
              select e.source_resource_id, e.target_resource_id, e.edge_type, e.weight, w.depth + 1,
                     w.path || e.target_resource_id
              from walk w
              join resource_edges e on e.source_resource_id = w.target_id
              join visible source on source.id = e.source_resource_id
              join visible target on target.id = e.target_resource_id
              where e.tenant_id = %(tenant_id)s
                and w.depth < %(hops)s
                and e.target_resource_id <> all(w.path)
                and (%(edge_types)s::text[] is null or e.edge_type = any(%(edge_types)s::text[]))
            ),
            node_depths as (
              select id, 0 as depth from starts
              union all
              select target_id, depth from walk
            ),
            nodes as (
              select id, min(depth) as depth from node_depths group by id
            ),
            edges as (
              select source_id, target_id, edge_type, max(weight) as weight, min(depth) as depth
              from walk
              group by source_id, target_id, edge_type
            )
            select 'node'::text as kind, v.id, v.title, v.type, n.depth,
                   null::uuid as source_resource_id, null::uuid as target_resource_id,
                   null::text as edge_type, null::double precision as weight
            from nodes n
            join visible v on v.id = n.id
            union all
            select 'edge'::text, null::uuid, null::text, null::text, e.depth,
                   e.source_id, e.target_id, e.edge_type, e.weight
            from edges e
            order by depth, kind desc
            """,
            {
                "tenant_id": tenant_id,
                "actor_open_id": actor_open_id,
                "resource_ids": resource_ids,
                "hops": hops,
                "edge_types": edge_types,
            },
        ).fetchall()

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

    def upsert_mapping(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        system: str,
        external_type: str,
        external_id: str,
        sync_status: str = "synced",
    ) -> None:
        with transaction(self.conn):
            self._upsert_mapping(
                tenant_id=tenant_id,
                resource_id=resource_id,
                mapping={
                    "system": system,
                    "external_type": external_type,
                    "external_id": external_id,
                    "sync_status": sync_status,
                },
            )

    def mark_mapping_failed(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        system: str,
        external_type: str,
        external_id: str,
        error: str,
    ) -> None:
        with transaction(self.conn):
            cursor = self.conn.execute(
                """
                update resource_mappings
                set sync_status = 'failed', last_error = %s, updated_at = now()
                where tenant_id = %s and system = %s and external_type = %s and external_id = %s
                """,
                (error, tenant_id, system, external_type, external_id),
            )
            if cursor.rowcount == 0:
                self.conn.execute(
                    """
                    insert into resource_events (tenant_id, resource_id, event_type, actor_open_id, payload)
                    values (%s, null, 'sync_failed', %s, %s::jsonb)
                    """,
                    (
                        tenant_id,
                        actor_open_id,
                        json.dumps(
                            {
                                "system": system,
                                "external_type": external_type,
                                "external_id": external_id,
                                "error": error,
                            },
                            sort_keys=True,
                            ensure_ascii=False,
                        ),
                    ),
                )

    def start_sync_run(
        self,
        *,
        tenant_id: str,
        source: str,
        triggered_by: str,
        actor_open_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        row = self.conn.execute(
            """
            insert into sync_runs (tenant_id, source, triggered_by, actor_open_id, metadata)
            values (%s, %s, %s, %s, %s::jsonb)
            returning id::text as id
            """,
            (
                tenant_id,
                source,
                triggered_by,
                actor_open_id,
                json.dumps(metadata or {}, sort_keys=True, ensure_ascii=False),
            ),
        ).fetchone()
        self.conn.commit()
        return row["id"]

    def finish_sync_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        status: str,
        created_count: int = 0,
        updated_count: int = 0,
        skipped_count: int = 0,
        failed_count: int = 0,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            update sync_runs
            set status = %s,
                finished_at = now(),
                created_count = %s,
                updated_count = %s,
                skipped_count = %s,
                failed_count = %s,
                error = %s,
                updated_at = now()
            where tenant_id = %s and id = %s
            """,
            (
                status,
                created_count,
                updated_count,
                skipped_count,
                failed_count,
                error,
                tenant_id,
                run_id,
            ),
        )
        self.conn.commit()

    def data_foundation_status(self, tenant_id: str) -> dict[str, Any]:
        resource_rows = self.conn.execute(
            """
            select type, count(*) as count
            from resources
            where tenant_id = %s
            group by type
            order by type
            """,
            (tenant_id,),
        ).fetchall()
        outbox_rows = self.conn.execute(
            """
            select status, count(*) as count
            from resource_outbox
            where tenant_id = %s
            group by status
            """,
            (tenant_id,),
        ).fetchall()
        last_sync = self.conn.execute(
            """
            select *
            from sync_runs
            where tenant_id = %s and source = 'feishu'
            order by started_at desc, id desc
            limit 1
            """,
            (tenant_id,),
        ).fetchone()
        running = self.conn.execute(
            """
            select count(*) as count
            from sync_runs
            where tenant_id = %s and status = 'running'
            """,
            (tenant_id,),
        ).fetchone()["count"]
        by_type = {row["type"]: row["count"] for row in resource_rows}
        outbox = {row["status"]: row["count"] for row in outbox_rows}
        return {
            "tenant_id": tenant_id,
            "resources": {"total": sum(by_type.values()), "by_type": by_type},
            "sync": {
                "running": running > 0,
                "last_status": None if last_sync is None else last_sync["status"],
                "last_success_at": None
                if last_sync is None or last_sync["status"] not in ("success", "partial_success")
                else last_sync["finished_at"],
                "last_error": None if last_sync is None else last_sync["error"],
                "last_counts": None
                if last_sync is None
                else {
                    "created": last_sync["created_count"],
                    "updated": last_sync["updated_count"],
                    "skipped": last_sync["skipped_count"],
                    "failed": last_sync["failed_count"],
                },
            },
            "outbox": {
                "pending": outbox.get("pending", 0),
                "processing": outbox.get("processing", 0),
                "succeeded": outbox.get("succeeded", 0),
                "failed": outbox.get("failed", 0),
            },
        }

    def lease_outbox(self, *, tenant_id: str, batch_size: int) -> list[dict[str, Any]]:
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select id::text as id
                from resource_outbox
                where tenant_id = %s
                  and status = 'pending'
                  and available_at <= now()
                order by created_at, id
                limit %s
                for update skip locked
                """,
                (tenant_id, batch_size),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return []
            leased = self.conn.execute(
                """
                update resource_outbox
                set status = 'processing',
                    attempts = attempts + 1,
                    updated_at = now()
                where id = any(%s::uuid[])
                returning id::text, tenant_id, resource_id::text, event_id::text, topic, payload, attempts
                """,
                (ids,),
            ).fetchall()
        return [dict(row) for row in leased]

    def complete_outbox(self, outbox_id: str, *, status: str = "succeeded", error: str | None = None) -> None:
        self.conn.execute(
            """
            update resource_outbox
            set status = %s,
                last_error = %s,
                updated_at = now()
            where id = %s
            """,
            (status, error, outbox_id),
        )
        self.conn.commit()

    def _lock_mapping(self, tenant_id: str, mapping: dict[str, Any] | None) -> None:
        if mapping is None:
            return
        lock_key = "|".join(
            [
                tenant_id,
                str(mapping["system"]),
                str(mapping["external_type"]),
                str(mapping["external_id"]),
            ]
        )
        self.conn.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))

    def _resource_id_for_mapping(self, tenant_id: str, mapping: dict[str, Any] | None) -> Any | None:
        if mapping is None:
            return None
        row = self.conn.execute(
            """
            select resource_id
            from resource_mappings
            where tenant_id = %s and system = %s and external_type = %s and external_id = %s
            """,
            (tenant_id, mapping["system"], mapping["external_type"], mapping["external_id"]),
        ).fetchone()
        return None if row is None else row["resource_id"]

    def _upsert_mapping(self, *, tenant_id: str, resource_id: Any, mapping: dict[str, Any]) -> None:
        resource = self.conn.execute(
            "select id from resources where id = %s and tenant_id = %s",
            (resource_id, tenant_id),
        ).fetchone()
        if resource is None:
            raise PermissionError("Cannot map a resource from another tenant")
        self.conn.execute(
            """
            insert into resource_mappings (
              tenant_id, resource_id, system, external_type, external_id, external_url,
              external_updated_at, sync_cursor, sync_status, last_error, updated_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, 'pending'), null, now())
            on conflict(tenant_id, system, external_type, external_id)
            do update set resource_id = excluded.resource_id,
                          external_url = excluded.external_url,
                          external_updated_at = excluded.external_updated_at,
                          sync_cursor = excluded.sync_cursor,
                          sync_status = excluded.sync_status,
                          last_error = null,
                          updated_at = now()
            """,
            (
                tenant_id,
                resource_id,
                mapping["system"],
                mapping["external_type"],
                mapping["external_id"],
                mapping.get("external_url"),
                mapping.get("external_updated_at"),
                mapping.get("sync_cursor"),
                mapping.get("sync_status"),
            ),
        )

    def _latest_version(self, resource_id: Any) -> Any:
        row = self.conn.execute(
            """
            select version, content_hash
            from resource_versions
            where resource_id = %s
            order by version desc
            limit 1
            """,
            (resource_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("Mapped resource has no version")
        return row

    @staticmethod
    def _resource_is_unchanged(
        row: Any,
        latest: Any,
        *,
        resource_type: str,
        title: str,
        summary: str | None,
        content_text: str | None,
        content_json: dict[str, Any],
        content_hash: str,
        visibility: str,
        owner_open_id: str | None,
    ) -> bool:
        return (
            latest["content_hash"] == content_hash
            and row["type"] == resource_type
            and row["title"] == title
            and row["summary"] == summary
            and row["content_text"] == content_text
            and dict(row["content_json"]) == content_json
            and row["visibility"] == visibility
            and row["owner_open_id"] == owner_open_id
        )

    def _next_version(self, resource_id: Any) -> int:
        row = self.conn.execute(
            "select coalesce(max(version), 0) + 1 as version from resource_versions where resource_id = %s",
            (resource_id,),
        ).fetchone()
        return int(row["version"])

    def _resource_from_row(self, row: Any, *, version: int | None = None) -> Resource:
        return Resource(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            type=row["type"],
            title=row["title"],
            summary=row["summary"],
            content_text=row["content_text"],
            content_json=dict(row["content_json"]),
            status=row["status"],
            visibility=row["visibility"],
            owner_open_id=row["owner_open_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=None if version is None else int(version),
        )
