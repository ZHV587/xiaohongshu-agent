from __future__ import annotations

import hashlib
import json
import math
from contextlib import AbstractContextManager
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.db import transaction
from data_foundation.models import OutboxRequest, Resource
from data_foundation.permissions import readable_resource_where


OUTBOX_STATUSES = ("pending", "retry", "processing", "blocked", "dead", "succeeded", "superseded")
EMBEDDING_RUNTIME_STATUSES = ("active", "building")
RUNTIME_RESOURCE_TYPES = (
    "feishu_base_record",
    "feishu_doc",
    "generated_topic",
    "generated_copy",
    "revision_request",
    "performance_metric",
    "draft",
    "topic",
    "doc",
)


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
        outbox_requests: list[OutboxRequest] | None = None,
    ) -> Resource:
        payload_json = json.dumps(content_json, sort_keys=True, ensure_ascii=False)
        content_hash = hashlib.sha256(f"{content_text or ''}\n{payload_json}".encode("utf-8")).hexdigest()
        requests = outbox_requests or []

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
                self._adjust_resource_type_count(tenant_id=tenant_id, resource_type=resource_type, delta=1)
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
                if current["type"] != resource_type:
                    self._adjust_resource_type_count(
                        tenant_id=tenant_id,
                        resource_type=current["type"],
                        delta=-1,
                    )
                    self._adjust_resource_type_count(
                        tenant_id=tenant_id,
                        resource_type=resource_type,
                        delta=1,
                    )

            version = self._next_version(row["id"])
            self.conn.execute(
                """
                insert into resource_versions (
                  tenant_id, resource_id, version, content_hash, content_text, content_json, changed_by
                )
                values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (tenant_id, row["id"], version, content_hash, content_text, payload_json, actor_open_id),
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

            self._enqueue_outbox(
                tenant_id=tenant_id,
                resource_id=row["id"],
                version=version,
                requests=requests,
                event_id=event["id"],
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
                   ) as version,
                   (
                     select max(rm.external_updated_at)
                     from resource_mappings rm
                     where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                   ) as source_updated_at
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
            on conflict(tenant_id, resource_id, subject_type, subject_id, permission) do nothing
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

    def readable_rows_by_ids(self, *, tenant_id: str, actor_open_id: str, resource_ids: list[str]):
        if not resource_ids:
            return []
        ordering = {rid: i for i, rid in enumerate(resource_ids)}
        rows = self.conn.execute(
            f"""
            select r.*,
                   (
                     select max(rm.external_updated_at)
                     from resource_mappings rm
                     where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                   ) as source_updated_at,
                   1.0::real as score
            from resources r
            where r.id = any(%(ids)s::uuid[])
              and {readable_resource_where('r')}
            """,
            {"tenant_id": tenant_id, "actor_open_id": actor_open_id, "ids": resource_ids},
        ).fetchall()
        return sorted(rows, key=lambda row: ordering.get(str(row["id"]), len(ordering)))

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
                     (
                       select max(rm.external_updated_at)
                       from resource_mappings rm
                       where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                     ) as source_updated_at,
                     1 - (e.embedding <=> %(embedding)s::public.vector) as score,
                     row_number() over (
                       partition by r.id
                       order by e.embedding <=> %(embedding)s::public.vector, e.chunk_index
                     ) as resource_rank
              from resource_embeddings e
              join embedding_indexes idx
                on idx.tenant_id = e.tenant_id
               and idx.id = e.embedding_index_id
               and idx.embedding_model = e.embedding_model
               and idx.chunker_version = e.chunker_version
               and idx.status = 'active'
              join resources r
                on r.tenant_id = e.tenant_id
               and r.id = e.resource_id
              join resource_versions rv
                on rv.tenant_id = e.tenant_id
               and rv.resource_id = e.resource_id
               and rv.version = e.resource_version
              where e.embedding_model = %(embedding_model)s
                and {readable_resource_where('r')}
                and rv.version = (
                  select max(latest.version)
                  from resource_versions latest
                  where latest.tenant_id = r.tenant_id
                    and latest.resource_id = r.id
                )
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

    def active_embedding_index(self, tenant_id: str):
        from data_foundation.embedding_repository import EmbeddingRepository

        return EmbeddingRepository(self.conn).active_index(tenant_id)

    def _enqueue_outbox(
        self,
        *,
        tenant_id: str,
        resource_id: Any,
        version: int,
        requests,
        event_id: Any = None,
    ) -> None:
        """把一组 OutboxRequest 写入 resource_outbox(投递到 meili/graph/embedding)。

        必须在调用方已开启的事务内调用(与主数据写在同一事务,保证原子)。
        event_id 可空:upsert 路径传新建 event 的 id;add_edge 等"无新 event"的路径
        传 None(schema resource_outbox.event_id 可空,FK on delete set null)。
        dedupe_key 与 payload 构造与 upsert 路径完全一致,保证幂等键稳定。
        """
        for request in requests:
            request_payload = {
                **request.payload,
                "resource_id": str(resource_id),
                "version": version,
            }
            dedupe_key = hashlib.sha256(
                json.dumps(
                    [
                        tenant_id,
                        str(resource_id),
                        version,
                        request.topic,
                        *request.dedupe_parts,
                    ],
                    sort_keys=True,
                    ensure_ascii=False,
                ).encode("utf-8")
            ).hexdigest()
            self.conn.execute(
                """
                insert into resource_outbox (
                  tenant_id, resource_id, resource_version, event_id, topic, dedupe_key, payload
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                on conflict (tenant_id, dedupe_key) do nothing
                """,
                (
                    tenant_id,
                    resource_id,
                    version,
                    event_id,
                    request.topic,
                    dedupe_key,
                    json.dumps(request_payload, sort_keys=True, ensure_ascii=False),
                ),
            )

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
                on conflict(tenant_id, source_resource_id, target_resource_id, edge_type)
                do update set weight = excluded.weight
                """,
                (tenant_id, source_resource_id, target_resource_id, edge_type, weight),
            )
            # 边能进 Falkor 的不变量:GraphProcessor 在 ingest 某资源时重建其全部出边
            # (processors/graph.py 查 source_resource_id=该资源)。所以一条边要进图,
            # 其 source 端点必须有一个 graph_ingest 事件。upsert 新资源自带 graph_ingest
            # (creation_memory 的边 source 即新资源,搭车正确);但 add_edge 的 source 若是
            # 既有资源(如 performance_feedback 的 measured_by:source=既有文档),没有任何
            # graph_ingest → 边永不进图。这里显式为 source 端补一个 graph_ingest,把"边能进图"
            # 的责任收进 add_edge 自身,不再依赖调用方碰巧让 source 被 upsert。
            # dedupe_parts=("graph",) 与 upsert 路径一致 → 同 source 同 version 时撞同一
            # dedupe_key,on conflict do nothing 自动去重(文档自身已有 graph_ingest 时不重复)。
            source_version = self._latest_version(source_resource_id)["version"]
            self._enqueue_outbox(
                tenant_id=tenant_id,
                resource_id=source_resource_id,
                version=source_version,
                requests=[OutboxRequest("graph_ingest", ("graph",), {})],
            )

    def writable_resource_metadata(self, *, tenant_id: str, actor_open_id: str, resource_id: str):
        row = self.conn.execute(
            """
            select id::text as id, visibility, owner_open_id
            from resources r
            where r.id = %(resource_id)s
              and r.tenant_id = %(tenant_id)s
              and (
                r.owner_open_id = %(actor_open_id)s
                or exists (
                  select 1 from resource_permissions rp
                  where rp.resource_id = r.id
                    and rp.tenant_id = r.tenant_id
                    and rp.subject_type = 'user'
                    and rp.subject_id = %(actor_open_id)s
                    and rp.permission in ('write', 'admin')
                )
              )
            """,
            {"tenant_id": tenant_id, "actor_open_id": actor_open_id, "resource_id": resource_id},
        ).fetchone()
        if row is None:
            raise PermissionError("Resource not found or not writable")
        return row

    def performance_rows(self, *, tenant_id: str, actor_open_id: str, resource_id: str):
        return self.conn.execute(
            f"""
            select metric.id::text as resource_id,
                   metric.title,
                   metric.content_json,
                   e.weight,
                   metric.updated_at
            from resources target
            join resource_edges e
              on e.tenant_id = target.tenant_id
             and e.source_resource_id = target.id
             and e.edge_type = 'measured_by'
            join resources metric
              on metric.tenant_id = target.tenant_id
             and metric.id = e.target_resource_id
             and metric.type = 'performance_metric'
            where target.id = %(resource_id)s
              and {readable_resource_where('target')}
              and {readable_resource_where('metric')}
            order by metric.updated_at desc, metric.id desc
            """,
            {"tenant_id": tenant_id, "actor_open_id": actor_open_id, "resource_id": resource_id},
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
        external_updated_at: Any | None = None,
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
                    "external_updated_at": external_updated_at,
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
                set sync_status = 'failed', error_code = 'sync_failed', error_summary = %s, updated_at = now()
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

    def data_foundation_status(self, tenant_id: str) -> dict[str, Any]:
        resource_rows = self.conn.execute(
            """
            select type, count
            from resource_type_counts
            where tenant_id = %s
              and count > 0
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
            where tenant_id = %s and source_type in ('feishu_base', 'feishu_wiki')
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
                if last_sync is None or last_sync["status"] not in ("succeeded", "partial")
                else last_sync["finished_at"],
                "last_error_summary": None if last_sync is None else last_sync["error_summary"],
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
                "retry": outbox.get("retry", 0),
                "processing": outbox.get("processing", 0),
                "blocked": outbox.get("blocked", 0),
                "succeeded": outbox.get("succeeded", 0),
                "superseded": outbox.get("superseded", 0),
                "dead": outbox.get("dead", 0),
            },
        }

    def runtime_fact_aggregates(self, tenant_id: str) -> dict[str, Any]:
        source_enabled = self.conn.execute(
            """
            select count(*) as count
            from sync_sources
            where tenant_id = %s
              and enabled
            """,
            (tenant_id,),
        ).fetchone()["count"]
        source_expired = self.conn.execute(
            """
            select count(*) as count
            from sync_sources
            where tenant_id = %s
              and enabled
              and next_run_at <= now()
              and (lease_expires_at is null or lease_expires_at <= now())
            """,
            (tenant_id,),
        ).fetchone()["count"]
        source_running = self.conn.execute(
            """
            select count(*) as count
            from sync_sources
            where tenant_id = %s
              and enabled
              and lease_expires_at is not null
              and lease_expires_at > now()
            """,
            (tenant_id,),
        ).fetchone()["count"]
        last_sync = self.conn.execute(
            """
            select status
            from sync_runs
            where tenant_id = %s
            order by started_at desc, id desc
            limit 1
            """,
            (tenant_id,),
        ).fetchone()
        outbox_rows = self.conn.execute(
            """
            select status, count(*) as count
            from resource_outbox
            where tenant_id = %s
            group by status
            """,
            (tenant_id,),
        ).fetchall()
        embedding_rows = self.conn.execute(
            """
            select distinct on (status)
              status,
              embedding_model,
              config_version,
              dimensions,
              expected_resources,
              completed_resources,
              failed_resources,
              activated_at,
              created_at,
              updated_at
            from embedding_indexes
            where tenant_id = %s and status in ('active', 'building')
            order by status, created_at desc, id desc
            """,
            (tenant_id,),
        ).fetchall()
        resource_rows = self.conn.execute(
            """
            select type, count
            from resource_type_counts
            where tenant_id = %s
              and count > 0
            order by type
            """,
            (tenant_id,),
        ).fetchall()
        indexed_row = self.conn.execute(
            """
            select max(created_at) as last_indexed_at
            from resource_embeddings
            where tenant_id = %s
            """,
            (tenant_id,),
        ).fetchone()
        error_rows = self.conn.execute(
            """
            select
              component,
              operation,
              error_code,
              error_count as count,
              window_started_at,
              window_ended_at
            from service_error_aggregates
            where tenant_id = %s
            order by window_started_at desc, window_ended_at desc, id desc
            limit 10
            """,
            (tenant_id,),
        ).fetchall()

        by_type = {resource_type: 0 for resource_type in RUNTIME_RESOURCE_TYPES}
        by_type["other"] = 0
        for row in resource_rows:
            resource_type = row["type"]
            if resource_type in by_type:
                by_type[resource_type] = row["count"]
            else:
                by_type["other"] += row["count"]
        outbox = {row["status"]: row["count"] for row in outbox_rows}
        embedding_by_status = {row["status"]: row for row in embedding_rows}

        return {
            "sources": {
                "enabled": source_enabled,
                "expired": source_expired,
                "running": source_running,
                "last_status": None if last_sync is None else last_sync["status"],
            },
            "outbox": {status: outbox.get(status, 0) for status in OUTBOX_STATUSES},
            "embedding": {
                status: self._runtime_embedding_fact(embedding_by_status.get(status))
                for status in EMBEDDING_RUNTIME_STATUSES
            },
            "resources": {
                "total": sum(by_type.values()),
                "by_type": by_type,
                "last_indexed_at": indexed_row["last_indexed_at"],
            },
            "errors": [
                {
                    "component": row["component"],
                    "operation": row["operation"],
                    "error_code": row["error_code"],
                    "count": row["count"],
                    "window_started_at": row["window_started_at"],
                    "window_ended_at": row["window_ended_at"],
                }
                for row in error_rows
            ],
        }

    def _runtime_embedding_fact(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "status": row["status"],
            "embedding_model": row["embedding_model"],
            "config_version": row["config_version"],
            "dimensions": row["dimensions"],
            "expected_resources": row["expected_resources"],
            "completed_resources": row["completed_resources"],
            "failed_resources": row["failed_resources"],
            "activated_at": row["activated_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

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
              external_updated_at, sync_cursor, sync_status, error_code, error_summary, updated_at
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, 'pending'), null, null, now())
            on conflict(tenant_id, system, external_type, external_id)
            do update set resource_id = excluded.resource_id,
                          external_url = excluded.external_url,
                          external_updated_at = excluded.external_updated_at,
                          sync_cursor = excluded.sync_cursor,
                          sync_status = excluded.sync_status,
                          error_code = null,
                          error_summary = null,
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

    def _adjust_resource_type_count(self, *, tenant_id: str, resource_type: str, delta: int) -> None:
        if delta == 0:
            return
        if delta > 0:
            self.conn.execute(
                """
                insert into resource_type_counts (tenant_id, type, count)
                values (%s, %s, %s)
                on conflict (tenant_id, type)
                do update set count = resource_type_counts.count + excluded.count,
                              updated_at = now()
                """,
                (tenant_id, resource_type, delta),
            )
            return
        self.conn.execute(
            """
            update resource_type_counts
            set count = count + %s,
                updated_at = now()
            where tenant_id = %s and type = %s
            """,
            (delta, tenant_id, resource_type),
        )
        self.conn.execute(
            """
            delete from resource_type_counts
            where tenant_id = %s and type = %s and count = 0
            """,
            (tenant_id, resource_type),
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
            source_updated_at=row.get("source_updated_at") if hasattr(row, "get") else None,
            version=None if version is None else int(version),
        )
