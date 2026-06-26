import hashlib
import json
import uuid
from typing import Optional, Any, Union
from psycopg import Connection, Cursor
from psycopg.rows import dict_row

from data_foundation.repositories.base import BaseRepository
from data_foundation.models import Resource, RuntimeIdentityConfig

class ResourceRepository(BaseRepository):
    def upsert_resource(
        self,
        resource: Optional[Resource] = None,
        actor: Optional[RuntimeIdentityConfig] = None,
        conn: Optional[Connection] = None,
        *,
        tenant_id: Optional[str] = None,
        actor_open_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        title: Optional[str] = None,
        content_text: Optional[str] = None,
        content_json: Optional[dict[str, Any]] = None,
        visibility: str = "private",
        owner_open_id: Optional[str] = None,
        summary: Optional[str] = None,
        mapping: Optional[dict[str, Any]] = None,
        outbox_requests: Optional[list] = None,
        **kwargs,
    ) -> Resource:
        """Upsert a resource, record version, events, type counts, and write to outbox.
        Supports both the new model-based signature and the legacy keyword-argument signature.
        """
        is_legacy = (resource is None)
        if resource is None:
            t_id = tenant_id or kwargs.get("tenant_id")
            a_open_id = actor_open_id or kwargs.get("actor_open_id")
            if not t_id or not a_open_id or not resource_type or not title:
                raise ValueError("Missing required arguments for upsert_resource")
            
            actor = RuntimeIdentityConfig(tenant_id=t_id, open_id=a_open_id)
            res_id = kwargs.get("id") or kwargs.get("resource_id")
            
            resource = Resource(
                id=res_id,
                tenant_id=t_id,
                type=resource_type,
                title=title,
                summary=summary,
                content_text=content_text,
                content_json=content_json or {},
                status="active",
                visibility=visibility,
                owner_open_id=owner_open_id or a_open_id,
                created_at=None,
                updated_at=None,
            )

        tenant_id = actor.tenant_id
        actor_open_id = actor.open_id
        
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    # 1. Advisory lock and mapping resolution if mapping is provided
                    if mapping is not None:
                        self._lock_mapping(tenant_id, mapping, cursor)
                        mapped_id = self._resource_id_for_mapping(tenant_id, mapping, cursor)
                        if mapped_id is not None:
                            resource = Resource(
                                id=str(mapped_id),
                                tenant_id=resource.tenant_id,
                                type=resource.type,
                                title=resource.title,
                                summary=resource.summary,
                                content_text=resource.content_text,
                                content_json=resource.content_json,
                                status=resource.status,
                                visibility=resource.visibility,
                                owner_open_id=resource.owner_open_id,
                                created_at=resource.created_at,
                                updated_at=resource.updated_at,
                            )
                    
                    # Enforce tenant boundary security checks
                    existing = None
                    if resource.id is not None:
                        existing = cursor.execute(
                            "select tenant_id, type from resources where id = %s",
                            (resource.id,)
                        ).fetchone()
                        
                    if existing:
                        if existing["tenant_id"] != tenant_id:
                            raise PermissionError("Tenant access bypass: resource belongs to another tenant")
                    
                    # Extract and default fields
                    resource_id = resource.id if resource.id is not None else str(uuid.uuid4())
                    resource_type = resource.type
                    title = resource.title
                    summary = resource.summary
                    content_text = resource.content_text
                    content_json = resource.content_json or {}
                    status = resource.status or "active"
                    visibility = resource.visibility or "private"
                    owner_open_id = resource.owner_open_id or actor_open_id
                    
                    payload_json = json.dumps(content_json, sort_keys=True, ensure_ascii=False)
                    content_hash = hashlib.sha256(f"{content_text or ''}\n{payload_json}".encode("utf-8")).hexdigest()
                    
                    if existing:
                        # Check early return if unchanged (important for idempotence)
                        latest_version_row = cursor.execute(
                            """
                            select version, content_hash
                            from resource_versions
                            where resource_id = %s
                            order by version desc
                            limit 1
                            """,
                            (resource_id,),
                        ).fetchone()
                        
                        current_row = cursor.execute(
                            "select * from resources where id = %s and tenant_id = %s",
                            (resource_id, tenant_id)
                        ).fetchone()
                        
                        if current_row and latest_version_row:
                            if self._resource_is_unchanged(
                                current_row,
                                latest_version_row,
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
                                    self._upsert_mapping(tenant_id=tenant_id, resource_id=resource_id, mapping=mapping, cursor=cursor)
                                return self._resource_from_row(current_row, latest_version_row["version"])

                        row = cursor.execute(
                            """
                            update resources
                            set type = %s,
                                title = %s,
                                summary = %s,
                                content_text = %s,
                                content_json = %s::jsonb,
                                status = %s,
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
                                status,
                                visibility,
                                owner_open_id,
                                resource_id,
                                tenant_id
                            )
                        ).fetchone()
                        
                        if existing["type"] != resource_type:
                            self._adjust_resource_type_count(cursor, tenant_id, existing["type"], -1)
                            self._adjust_resource_type_count(cursor, tenant_id, resource_type, 1)
                    else:
                        # Insert new resource
                        row = cursor.execute(
                            """
                            insert into resources (
                                id, tenant_id, type, title, summary, content_text, content_json, status, visibility, owner_open_id
                            )
                            values (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                            returning *
                            """,
                            (
                                resource_id,
                                tenant_id,
                                resource_type,
                                title,
                                summary,
                                content_text,
                                payload_json,
                                status,
                                visibility,
                                owner_open_id
                            )
                        ).fetchone()
                        
                        self._adjust_resource_type_count(cursor, tenant_id, resource_type, 1)
                    
                    # Determine version
                    v_row = cursor.execute(
                        "select coalesce(max(version), 0) + 1 as next_version from resource_versions where resource_id = %s",
                        (resource_id,)
                    ).fetchone()
                    version = int(v_row["next_version"])
                    
                    # Create resource version record
                    cursor.execute(
                        """
                        insert into resource_versions (
                            tenant_id, resource_id, version, content_hash, content_text, content_json, changed_by
                        )
                        values (%s, %s, %s, %s, %s, %s::jsonb, %s)
                        """,
                        (tenant_id, resource_id, version, content_hash, content_text, payload_json, actor_open_id)
                    )
                    
                    # Create event record
                    event = cursor.execute(
                        """
                        insert into resource_events (tenant_id, resource_id, event_type, actor_open_id, payload)
                        values (%s, %s, %s, %s, %s::jsonb)
                        returning id
                        """,
                        (
                            tenant_id,
                            resource_id,
                            "updated" if version > 1 else "imported",
                            actor_open_id,
                            json.dumps({"version": version}, sort_keys=True)
                        )
                    ).fetchone()
                    event_id = event["id"]
                    
                    # Upsert mapping if provided
                    if mapping is not None:
                        self._upsert_mapping(tenant_id=tenant_id, resource_id=resource_id, mapping=mapping, cursor=cursor)

                    # Enqueue transactional outbox tasks
                    if outbox_requests is not None:
                        self._enqueue_outbox(
                            tenant_id=tenant_id,
                            resource_id=resource_id,
                            version=version,
                            requests=outbox_requests,
                            event_id=event_id,
                            cursor=cursor,
                        )
                    elif is_legacy:
                        # Legacy signature: do not enqueue default outbox requests
                        pass
                    else:
                        for topic, dedupe_parts in [("meili_index", ("search",)), ("graph_ingest", ("graph",))]:
                            request_payload = {
                                "resource_id": str(resource_id),
                                "version": version,
                            }
                            dedupe_key = hashlib.sha256(
                                json.dumps(
                                    [
                                        tenant_id,
                                        str(resource_id),
                                        version,
                                        topic,
                                        *dedupe_parts,
                                    ],
                                    sort_keys=True,
                                    ensure_ascii=False,
                                ).encode("utf-8")
                            ).hexdigest()
                            
                            cursor.execute(
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
                                    topic,
                                    dedupe_key,
                                    json.dumps(request_payload, sort_keys=True, ensure_ascii=False),
                                )
                            )
                    
                    return self._resource_from_row(row, version)

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

    def _enqueue_outbox(
        self,
        *,
        tenant_id: str,
        resource_id: Any,
        version: int,
        requests: list,
        event_id: Any = None,
        cursor: Cursor = None,
    ) -> None:
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
            cursor.execute(
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

    def _adjust_resource_type_count(
        self,
        connection: Union[Connection, Cursor],
        tenant_id: str,
        resource_type: str,
        delta: int
    ) -> None:
        connection.execute(
            """
            insert into resource_type_counts (tenant_id, type, count)
            values (%s, %s, greatest(0::bigint, %s::bigint))
            on conflict (tenant_id, type) do update
            set count = greatest(0::bigint, resource_type_counts.count + %s::bigint),
                updated_at = now()
            """,
            (tenant_id, resource_type, delta, delta),
        )
        connection.execute(
            "delete from resource_type_counts where tenant_id = %s and type = %s and count = 0",
            (tenant_id, resource_type),
        )


    def _resource_from_row(self, row: dict, version: Optional[int] = None) -> Resource:
        return Resource(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            type=row["type"],
            title=row["title"],
            summary=row["summary"],
            content_text=row["content_text"],
            content_json=dict(row["content_json"]) if row["content_json"] is not None else {},
            status=row["status"],
            visibility=row["visibility"],
            owner_open_id=row["owner_open_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            source_updated_at=row.get("source_updated_at"),
            version=None if version is None else int(version),
        )

    def check_permission(
        self,
        resource_id: str,
        actor: RuntimeIdentityConfig,
        permission: str = "write",
        conn: Optional[Connection] = None,
    ) -> None:
        """Verify if the actor has the specified permission ('read' or 'write') on the resource.
        Raises PermissionError if the actor does not have the permission.
        """
        try:
            uuid.UUID(str(resource_id))
        except (ValueError, TypeError, AttributeError):
            raise PermissionError("Invalid UUID format")

        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                if permission == "write":
                    row = cursor.execute(
                        """
                        select 1 from resources r
                        where r.id = %s
                          and r.tenant_id = %s
                          and (
                            r.owner_open_id = %s
                            or exists (
                              select 1 from resource_permissions rp
                              where rp.resource_id = r.id
                                and rp.tenant_id = r.tenant_id
                                and rp.subject_type = 'user'
                                and rp.subject_id = %s
                                and rp.permission in ('write', 'admin')
                            )
                          )
                        """,
                        (resource_id, actor.tenant_id, actor.open_id, actor.open_id)
                    ).fetchone()
                    if not row:
                        raise PermissionError(f"Resource {resource_id} is not writable by actor")
                elif permission == "read":
                    row = cursor.execute(
                        """
                        select 1 from resources r
                        where r.id = %s
                          and r.tenant_id = %s
                          and (
                            r.owner_open_id = %s
                            or r.visibility = 'team'
                            or exists (
                              select 1 from resource_permissions rp
                              where rp.resource_id = r.id
                                and rp.tenant_id = r.tenant_id
                                and rp.subject_type = 'user'
                                and rp.subject_id = %s
                                and rp.permission in ('read', 'write', 'admin')
                            )
                          )
                        """,
                        (resource_id, actor.tenant_id, actor.open_id, actor.open_id)
                    ).fetchone()
                    if not row:
                        raise PermissionError(f"Resource {resource_id} is not readable by actor")
                else:
                    raise ValueError(f"Unknown permission type: {permission}")

    def get_resource(self, tenant_id: str, actor_open_id: str, resource_id: str, conn: Optional[Connection] = None) -> Resource | None:
        actor = RuntimeIdentityConfig(tenant_id=tenant_id, open_id=actor_open_id)
        where_clause = self.readable_resource_where(actor, "r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
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
                    where r.id = %s
                      and {where_clause}
                    """,
                    (resource_id,),
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
        conn: Optional[Connection] = None,
    ) -> None:
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        insert into resource_permissions (tenant_id, resource_id, subject_type, subject_id, permission)
                        values (%s, %s, %s, %s, %s)
                        on conflict(tenant_id, resource_id, subject_type, subject_id, permission) do nothing
                        """,
                        (tenant_id, resource_id, subject_type, subject_id, permission),
                    )

    def readable_rows_by_ids(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_ids: list[str],
        conn: Optional[Connection] = None,
    ) -> list[dict]:
        if not resource_ids:
            return []
        ordering = {rid: i for i, rid in enumerate(resource_ids)}
        actor = RuntimeIdentityConfig(tenant_id=tenant_id, open_id=actor_open_id)
        where_clause = self.readable_resource_where(actor, "r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    f"""
                    select r.*,
                           (
                             select max(rm.external_updated_at)
                             from resource_mappings rm
                             where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                           ) as source_updated_at,
                           1.0::real as score
                    from resources r
                    where r.id = any(%s::uuid[])
                      and {where_clause}
                    """,
                    (resource_ids,),
                ).fetchall()
                return sorted([dict(row) for row in rows], key=lambda row: ordering.get(str(row["id"]), len(ordering)))

    def _vector_literal(self, embedding: list[float]) -> str:
        return "[" + ",".join(str(float(x)) for x in embedding) + "]"

    def semantic_rows(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        embedding: list[float],
        embedding_model: str,
        top_k: int,
        conn: Optional[Connection] = None,
    ) -> list[dict]:
        embedding_model = embedding_model.strip()
        if not embedding_model:
            raise ValueError("Embedding model is required")
        vector_literal = self._vector_literal(embedding)
        actor = RuntimeIdentityConfig(tenant_id=tenant_id, open_id=actor_open_id)
        where_clause = self.readable_resource_where(actor, "r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    f"""
                    with candidates as (
                      select r.*, e.chunk_index, e.chunk_text,
                             (
                               select max(rm.external_updated_at)
                               from resource_mappings rm
                               where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                             ) as source_updated_at,
                             1 - (e.embedding <=> %s::public.vector) as score,
                             row_number() over (
                               partition by r.id
                               order by e.embedding <=> %s::public.vector, e.chunk_index
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
                      where e.embedding_model = %s
                        and {where_clause}
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
                    limit %s
                    """,
                    (vector_literal, vector_literal, embedding_model, top_k),
                ).fetchall()
                return [dict(row) for row in rows]

    def active_embedding_index(self, tenant_id: str, conn: Optional[Connection] = None) -> Any:
        from data_foundation.embedding_repository import EmbeddingRepository
        with self.connection_context(conn) as connection:
            return EmbeddingRepository(connection).active_index(tenant_id)

    def writable_resource_metadata(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        conn: Optional[Connection] = None,
    ) -> dict:
        actor = RuntimeIdentityConfig(tenant_id=tenant_id, open_id=actor_open_id)
        self.check_permission(resource_id, actor, permission="write", conn=conn)
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    "select id::text as id, visibility, owner_open_id from resources where id = %s",
                    (resource_id,),
                ).fetchone()
                if row is None:
                    raise PermissionError("Resource not found or not writable")
                return dict(row)

    def find_performance_metric_id(
        self,
        *,
        tenant_id: str,
        target_resource_id: str,
        conn: Optional[Connection] = None,
    ) -> str | None:
        """按目标资源查既有 performance_metric id(幂等写入用)。无则 None。

        与 PerformanceRepository.save_performance 的查重口径一致:
        content_json->>'target_resource_id' 唯一定位某目标的效果指标。
        """
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    """
                    select id::text as id
                    from resources
                    where tenant_id = %s
                      and type = 'performance_metric'
                      and content_json->>'target_resource_id' = %s
                    limit 1
                    """,
                    (tenant_id, target_resource_id),
                ).fetchone()
                return None if row is None else row["id"]

    def existing_mapping_external_ids(
        self,
        *,
        tenant_id: str,
        system: str,
        external_type: str,
        external_ids: list[str],
        conn: Optional[Connection] = None,
    ) -> set[str]:
        """返回 external_ids 中已存在 mapping 的子集(用于跨源去重 / 采纳幂等判断)。"""
        ids = [str(x) for x in external_ids if x]
        if not ids:
            return set()
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    select external_id
                    from resource_mappings
                    where tenant_id = %s and system = %s and external_type = %s
                      and external_id = any(%s)
                    """,
                    (tenant_id, system, external_type, ids),
                ).fetchall()
                return {str(row["external_id"]) for row in rows}

    def _lock_mapping(self, tenant_id: str, mapping: dict[str, Any] | None, cursor: Cursor) -> None:
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
        cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))

    def _resource_id_for_mapping(self, tenant_id: str, mapping: dict[str, Any] | None, cursor: Cursor) -> Any | None:
        if mapping is None:
            return None
        row = cursor.execute(
            """
            select resource_id
            from resource_mappings
            where tenant_id = %s and system = %s and external_type = %s and external_id = %s
            """,
            (tenant_id, mapping["system"], mapping["external_type"], mapping["external_id"]),
        ).fetchone()
        return None if row is None else row["resource_id"]

    def _upsert_mapping(self, *, tenant_id: str, resource_id: Any, mapping: dict[str, Any], cursor: Cursor) -> None:
        resource = cursor.execute(
            "select id from resources where id = %s and tenant_id = %s",
            (resource_id, tenant_id),
        ).fetchone()
        if resource is None:
            raise PermissionError("Cannot map a resource from another tenant")
        cursor.execute(
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
        conn: Optional[Connection] = None,
    ) -> None:
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
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
                        cursor=cursor,
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
        conn: Optional[Connection] = None,
    ) -> None:
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    cursor.execute(
                        """
                        update resource_mappings
                        set sync_status = 'failed', error_code = 'sync_failed', error_summary = %s, updated_at = now()
                        where tenant_id = %s and system = %s and external_type = %s and external_id = %s
                        """,
                        (error, tenant_id, system, external_type, external_id),
                    )
                    if cursor.rowcount == 0:
                        cursor.execute(
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

    def data_foundation_status(self, tenant_id: str, conn: Optional[Connection] = None) -> dict[str, Any]:
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                resource_rows = cursor.execute(
                    """
                    select type, count
                    from resource_type_counts
                    where tenant_id = %s
                      and count > 0
                    order by type
                    """,
                    (tenant_id,),
                ).fetchall()
                outbox_rows = cursor.execute(
                    """
                    select status, count(*) as count
                    from resource_outbox
                    where tenant_id = %s
                    group by status
                    """,
                    (tenant_id,),
                ).fetchall()
                last_sync = cursor.execute(
                    """
                    select *
                    from sync_runs
                    where tenant_id = %s and source_type in ('feishu_base', 'feishu_wiki')
                    order by started_at desc, id desc
                    limit 1
                    """,
                    (tenant_id,),
                ).fetchone()
                running = cursor.execute(
                    """
                    select count(*) as count
                    from sync_runs
                    where tenant_id = %s and status = 'running'
                    """,
                    (tenant_id,),
                ).fetchone()["count"]
                
                by_type = {row["type"]: row["count"] for row in resource_rows}
                outbox = {row["status"]: row["count"] for row in outbox_rows}
                
                # OUTBOX_STATUSES constant
                outbox_statuses = ("pending", "retry", "processing", "blocked", "dead", "succeeded", "superseded")
                
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
                    "outbox": {status: outbox.get(status, 0) for status in outbox_statuses},
                }

    def _runtime_embedding_fact(self, row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
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

    def runtime_fact_aggregates(self, tenant_id: str, conn: Optional[Connection] = None) -> dict[str, Any]:
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                source_enabled = cursor.execute(
                    """
                    select count(*) as count
                    from sync_sources
                    where tenant_id = %s
                      and enabled
                    """,
                    (tenant_id,),
                ).fetchone()["count"]
                source_expired = cursor.execute(
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
                source_running = cursor.execute(
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
                last_sync = cursor.execute(
                    """
                    select status
                    from sync_runs
                    where tenant_id = %s
                    order by started_at desc, id desc
                    limit 1
                    """,
                    (tenant_id,),
                ).fetchone()
                outbox_rows = cursor.execute(
                    """
                    select status, count(*) as count
                    from resource_outbox
                    where tenant_id = %s
                    group by status
                    """,
                    (tenant_id,),
                ).fetchall()
                embedding_rows = cursor.execute(
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
                resource_rows = cursor.execute(
                    """
                    select type, count
                    from resource_type_counts
                    where tenant_id = %s
                      and count > 0
                    order by type
                    """,
                    (tenant_id,),
                ).fetchall()
                indexed_row = cursor.execute(
                    """
                    select max(created_at) as last_indexed_at
                    from resource_embeddings
                    where tenant_id = %s
                    """,
                    (tenant_id,),
                ).fetchone()
                error_rows = cursor.execute(
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

                runtime_resource_types = (
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
                outbox_statuses = ("pending", "retry", "processing", "blocked", "dead", "succeeded", "superseded")
                embedding_runtime_statuses = ("active", "building")

                by_type = {resource_type: 0 for resource_type in runtime_resource_types}
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
                    "outbox": {status: outbox.get(status, 0) for status in outbox_statuses},
                    "embedding": {
                        status: self._runtime_embedding_fact(embedding_by_status.get(status))
                        for status in embedding_runtime_statuses
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

    def add_edge(
        self,
        *,
        tenant_id: str,
        source_resource_id: str,
        target_resource_id: str,
        edge_type: str,
        weight: float = 1.0,
        conn: Optional[Connection] = None,
    ) -> None:
        from data_foundation.repositories.feedback import FeedbackRepository
        FeedbackRepository(conn or self.conn).add_edge(
            tenant_id=tenant_id,
            source_resource_id=source_resource_id,
            target_resource_id=target_resource_id,
            edge_type=edge_type,
            weight=weight,
            conn=conn or self.conn,
        )

    def performance_rows(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        conn: Optional[Connection] = None,
    ) -> list[dict]:
        from data_foundation.repositories.performance import PerformanceRepository
        return PerformanceRepository(conn or self.conn).performance_rows(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=resource_id,
            conn=conn or self.conn,
        )

    def bulk_performance_metrics(
        self,
        tenant_id: str,
        resource_ids: list[str],
        actor: Optional[RuntimeIdentityConfig] = None,
        conn: Optional[Connection] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        from data_foundation.repositories.performance import PerformanceRepository
        return PerformanceRepository(conn or self.conn).bulk_performance_metrics(
            tenant_id=tenant_id,
            resource_ids=resource_ids,
            actor=actor,
            conn=conn or self.conn,
        )

    def debug_counts(self, conn: Optional[Connection] = None) -> dict[str, int]:
        names = ["resources", "resource_versions", "resource_events", "resource_mappings", "resource_outbox"]
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return {name: cursor.execute(f"select count(*) as c from {name}").fetchone()["c"] for name in names}




