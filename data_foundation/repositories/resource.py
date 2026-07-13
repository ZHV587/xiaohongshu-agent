import hashlib
import json
import uuid
from typing import Optional, Any, Union
from psycopg import Connection, Cursor
from psycopg.rows import dict_row

from data_foundation.knowledge.locking import acquire_classification_lock
from data_foundation.repositories.base import BaseRepository
from data_foundation.models import Resource, RuntimeIdentityConfig
from data_foundation.outbox_requests import default_write_requests


def hnsw_ef_search_width(top_k: int) -> int:
    """语义检索的 HNSW 召回宽度:按 top_k 放宽(4×),下限 64(pgvector 默认 40 偏窄)、
    上限 400(兜住极端 top_k 的查询开销)。独立成纯函数,便于对边界值做单测。"""
    return min(400, max(64, int(top_k) * 4))


class ResourceRepository(BaseRepository):
    def upsert_resource(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_type: str,
        title: str,
        summary: Optional[str] = None,
        content_text: Optional[str] = None,
        content_json: Optional[dict[str, Any]] = None,
        status: str = "active",
        visibility: str = "private",
        owner_open_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        mapping: Optional[dict[str, Any]] = None,
        outbox_requests: Optional[list] = None,
        conn: Optional[Connection] = None,
    ) -> Resource:
        """Upsert a resource and, in the same transaction, record its version, event,
        type-count delta, optional external mapping, and outbox tasks.

        单一调用契约(全 kwargs)。outbox_requests 语义(单一源,消除随签名静默分歧):
        - None(默认):投递 knowledge_enrich；资格处理成功后再投既有检索/图谱/向量管道。
        - []:显式不投递任何 outbox(仅本地、无需索引的中间态)。
        - 非空列表:按给定 OutboxRequest 投递。
        """
        if not tenant_id or not actor_open_id or not resource_type or not title:
            raise ValueError("tenant_id, actor_open_id, resource_type, title are required")
        if outbox_requests is None:
            outbox_requests = default_write_requests()

        resource = Resource(
            id=resource_id,
            tenant_id=tenant_id,
            type=resource_type,
            title=title,
            summary=summary,
            content_text=content_text,
            content_json=content_json or {},
            status=status,
            visibility=visibility,
            owner_open_id=owner_open_id or actor_open_id,
            created_at=None,
            updated_at=None,
        )

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

                    # Mapping resolution above is the only step allowed to change the
                    # stable resource id.  From this point through live-row/version and
                    # outbox writes, serialize with KnowledgeService classification.
                    # Mapping lock is always acquired first, preventing lock-order
                    # inversion for two imports of the same external identity.
                    resource_id = resource.id if resource.id is not None else str(uuid.uuid4())
                    acquire_classification_lock(
                        cursor,
                        tenant_id=tenant_id,
                        resource_id=resource_id,
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
                                status=status,
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

                    # Enqueue transactional outbox tasks(单一源:default_write_requests;[] 表示显式不投)。
                    if outbox_requests:
                        self._enqueue_outbox(
                            tenant_id=tenant_id,
                            resource_id=resource_id,
                            version=version,
                            requests=outbox_requests,
                            event_id=event_id,
                            cursor=cursor,
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
        status: str,
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
            and row["status"] == status
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
        dedupe_event: bool = False,
        cursor: Cursor = None,
    ) -> None:
        for request in requests:
            request_payload = {
                **request.payload,
                "resource_id": str(resource_id),
                "version": version,
            }
            dedupe_identity = [
                tenant_id,
                str(resource_id),
                version,
                request.topic,
                *request.dedupe_parts,
            ]
            # Normal resource upserts remain version-idempotent.  Lifecycle target
            # transitions are different: v1 -> v2 -> v1 must enqueue the second v1
            # transition, otherwise the old succeeded v1 row swallows the repair.
            if dedupe_event:
                if event_id is None:
                    raise ValueError("event_id is required for event-scoped outbox dedupe")
                dedupe_identity.append(str(event_id))
            dedupe_key = hashlib.sha256(
                json.dumps(
                    dedupe_identity,
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
        where_clause = self.readable_resource_where("r")
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
                    where r.id = %(resource_id)s
                      and {where_clause}
                    """,
                    {
                        "resource_id": resource_id,
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                    },
                ).fetchone()
                if row is None:
                    return None
                return self._resource_from_row(row, version=row["version"])

    def get_resource_version(
        self,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        conn: Optional[Connection] = None,
    ) -> Resource | None:
        """按 ACL hydrate 指定不可变版本，绝不回读 resources 的 latest 正文。

        resources 只提供身份、权限和不随版本变化的元数据；标题优先取版本 content_json.title，
        正文与结构化内容完全来自 resource_versions。
        """
        if not isinstance(resource_version, int) or isinstance(resource_version, bool) or resource_version <= 0:
            raise ValueError("resource_version must be a positive integer")
        where_clause = self.readable_resource_where("r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    f"""
                    select r.id, r.tenant_id, r.type,
                           coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                           r.summary, rv.content_text, rv.content_json,
                           r.status, r.visibility, r.owner_open_id,
                           r.created_at, r.updated_at,
                           null::timestamptz as source_updated_at,
                           rv.version
                    from resources r
                    join resource_versions rv
                      on rv.tenant_id = r.tenant_id and rv.resource_id = r.id
                    where r.id = %(resource_id)s
                      and rv.version = %(resource_version)s
                      and {where_clause}
                    """,
                    {
                        "resource_id": resource_id,
                        "resource_version": resource_version,
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                    },
                ).fetchone()
                return None if row is None else self._resource_from_row(row, version=row["version"])

    def get_resource_for_knowledge(
        self,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        conn: Optional[Connection] = None,
    ) -> Resource | None:
        """Hydrate the exact snapshot that an Agent is allowed to use as knowledge.

        ``current_knowledge_targets`` is the single qualification + exact-version gate.
        The ACL and knowledge pointer are checked in the same query so a concurrent
        lifecycle or qualification change cannot leak a stale/unqualified snapshot.
        """
        if (
            not isinstance(resource_version, int)
            or isinstance(resource_version, bool)
            or resource_version <= 0
        ):
            raise ValueError("resource_version must be a positive integer")
        where_clause = self.readable_resource_where("r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                row = cursor.execute(
                    f"""
                    select r.id, r.tenant_id, r.type,
                           coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                           r.summary, rv.content_text, rv.content_json,
                           r.status, r.visibility, r.owner_open_id,
                           r.created_at, r.updated_at,
                           (
                             select max(rm.external_updated_at)
                             from resource_mappings rm
                             where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                           ) as source_updated_at,
                           rv.version
                    from current_knowledge_targets target
                    join resources r
                      on r.tenant_id = target.tenant_id and r.id = target.resource_id
                    join resource_versions rv
                      on rv.tenant_id = target.tenant_id
                     and rv.resource_id = target.resource_id
                     and rv.version = target.resource_version
                    where target.resource_id = %(resource_id)s
                      and target.resource_version = %(resource_version)s
                      and {where_clause}
                    """,
                    {
                        "resource_id": resource_id,
                        "resource_version": resource_version,
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                    },
                ).fetchone()
                return None if row is None else self._resource_from_row(row, version=row["version"])

    def list_owned_session_snapshots(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        project_name: str | None = None,
        limit: int = 10,
        conn: Optional[Connection] = None,
    ) -> list[dict[str, Any]]:
        """Read the actor's latest exact session checkpoints outside the knowledge gate.

        Session checkpoints remain restorable even before the user confirms them as
        reusable strategy knowledge.  This path is deliberately owner-only; team ACL
        and generic resource search must not turn unconfirmed model output into shared
        knowledge.
        """
        if not actor_open_id:
            raise ValueError("actor_open_id is required")
        safe_limit = min(max(int(limit), 1), 50)
        project = project_name.strip() if isinstance(project_name, str) else ""
        title_prefix = f"[{project}] " if project else ""
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    """
                    select r.id::text as resource_id, rv.version as resource_version,
                           r.title, r.summary, rv.content_text, rv.content_json,
                           r.created_at, r.updated_at
                    from resources r
                    join lateral (
                      select version, content_text, content_json
                      from resource_versions exact
                      where exact.tenant_id = r.tenant_id
                        and exact.resource_id = r.id
                      order by exact.version desc
                      limit 1
                    ) rv on true
                    where r.tenant_id = %(tenant_id)s
                      and r.type = 'session_snapshot'
                      and r.owner_open_id = %(actor_open_id)s
                      and r.status = 'active'
                      and (
                        %(project_name)s = ''
                        or rv.content_json->>'project_name' = %(project_name)s
                        or left(r.title, char_length(%(title_prefix)s)) = %(title_prefix)s
                      )
                    order by r.updated_at desc, r.id
                    limit %(limit)s
                    """,
                    {
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                        "project_name": project,
                        "title_prefix": title_prefix,
                        "limit": safe_limit,
                    },
                ).fetchall()
        return [dict(row) for row in rows]

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
                    row = cursor.execute(
                        """
                        insert into resource_permissions (tenant_id, resource_id, subject_type, subject_id, permission)
                        values (%s, %s, %s, %s, %s)
                        on conflict(tenant_id, resource_id, subject_type, subject_id, permission) do nothing
                        returning id::text
                        """,
                        (tenant_id, resource_id, subject_type, subject_id, permission),
                    ).fetchone()
                    if row is not None and subject_type == "user":
                        from data_foundation.preference_outbox import enqueue_preference_synthesis

                        enqueue_preference_synthesis(
                            cursor,
                            tenant_id=tenant_id,
                            actor_open_id=subject_id,
                            trigger_key=f"permission:grant:{row['id']}",
                            trigger_payload={
                                "kind": "permission_grant",
                                "resource_id": resource_id,
                                "permission": permission,
                            },
                        )

    def revoke_permission(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        subject_type: str,
        subject_id: str,
        permission: str,
        conn: Optional[Connection] = None,
    ) -> bool:
        """Revoke one exact ACL row and recompute any affected actor patterns."""
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    row = cursor.execute(
                        """
                        delete from resource_permissions
                        where tenant_id = %s and resource_id = %s
                          and subject_type = %s and subject_id = %s and permission = %s
                        returning id::text
                        """,
                        (tenant_id, resource_id, subject_type, subject_id, permission),
                    ).fetchone()
                    if row is None:
                        return False
                    if subject_type == "user":
                        from data_foundation.preference_outbox import enqueue_preference_synthesis

                        enqueue_preference_synthesis(
                            cursor,
                            tenant_id=tenant_id,
                            actor_open_id=subject_id,
                            trigger_key=f"permission:revoke:{row['id']}",
                            trigger_payload={
                                "kind": "permission_revoke",
                                "resource_id": resource_id,
                                "permission": permission,
                            },
                        )
                    return True

    def readable_rows_by_ids(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_ids: list[str],
        resource_versions: list[int] | None = None,
        knowledge_only: bool = False,
        conn: Optional[Connection] = None,
    ) -> list[dict]:
        if not resource_ids:
            return []
        if resource_versions is not None:
            if knowledge_only:
                raise ValueError("resource_versions and knowledge_only are mutually exclusive")
            if len(resource_versions) != len(resource_ids):
                raise ValueError("resource_versions must align with resource_ids")
            if any(
                not isinstance(version, int)
                or isinstance(version, bool)
                or version <= 0
                for version in resource_versions
            ):
                raise ValueError("resource_versions must contain positive integers")
        ordering = {rid: i for i, rid in enumerate(resource_ids)}
        where_clause = self.readable_resource_where("r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                if resource_versions is not None:
                    rows = cursor.execute(
                        f"""
                        with requested(resource_id, resource_version, ordinal) as (
                          select *
                          from unnest(
                            %(resource_ids)s::uuid[],
                            %(resource_versions)s::int[]
                          ) with ordinality
                        )
                        select r.id, r.tenant_id, r.type,
                               coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                               r.summary, rv.content_text, rv.content_json,
                               r.status, r.visibility, r.owner_open_id,
                               r.created_at, r.updated_at,
                               (
                                 select max(rm.external_updated_at)
                                 from resource_mappings rm
                                 where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                               ) as source_updated_at,
                               1.0::real as score,
                               rv.version as resource_version
                        from requested req
                        join resources r on r.id = req.resource_id
                        join current_knowledge_targets target
                          on target.tenant_id = r.tenant_id
                         and target.resource_id = r.id
                         and target.resource_version = req.resource_version
                        join resource_versions rv
                          on rv.tenant_id = r.tenant_id
                         and rv.resource_id = r.id
                         and rv.version = req.resource_version
                        where {where_clause}
                        order by req.ordinal
                        """,
                        {
                            "resource_ids": resource_ids,
                            "resource_versions": resource_versions,
                            "tenant_id": tenant_id,
                            "actor_open_id": actor_open_id,
                        },
                    ).fetchall()
                    return [dict(row) for row in rows]
                if knowledge_only:
                    rows = cursor.execute(
                        f"""
                        with requested(resource_id, ordinal) as (
                          select *
                          from unnest(%(resource_ids)s::uuid[]) with ordinality
                        )
                        select r.id, r.tenant_id, r.type,
                               coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                               r.summary, rv.content_text, rv.content_json,
                               r.status, r.visibility, r.owner_open_id,
                               r.created_at, r.updated_at,
                               (
                                 select max(rm.external_updated_at)
                                 from resource_mappings rm
                                 where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                               ) as source_updated_at,
                               1.0::real as score,
                               rv.version as resource_version
                        from requested req
                        join resources r on r.id = req.resource_id
                        join current_knowledge_targets target
                          on target.tenant_id = r.tenant_id
                         and target.resource_id = r.id
                        join resource_versions rv
                          on rv.tenant_id = target.tenant_id
                         and rv.resource_id = target.resource_id
                         and rv.version = target.resource_version
                        where {where_clause}
                        order by req.ordinal
                        """,
                        {
                            "resource_ids": resource_ids,
                            "tenant_id": tenant_id,
                            "actor_open_id": actor_open_id,
                        },
                    ).fetchall()
                    return [dict(row) for row in rows]
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
                    where r.id = any(%(resource_ids)s::uuid[])
                      and {where_clause}
                    """,
                    {
                        "resource_ids": resource_ids,
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                    },
                ).fetchall()
                return sorted([dict(row) for row in rows], key=lambda row: ordering.get(str(row["id"]), len(ordering)))

    def current_knowledge_rows(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_ids: list[str],
        resource_versions: list[int],
        asset_kinds: list[str] | None = None,
        source_kinds: list[str] | None = None,
        niches: list[str] | None = None,
        min_quality: float | None = None,
        updated_after: Any | None = None,
        conn: Optional[Connection] = None,
    ) -> list[dict[str, Any]]:
        """按 exact identity 回表执行当前知识资格、ACL 与用户过滤条件。

        Meilisearch 与 FalkorDB 均不承担行级权限。任何召回结果（包括图扩展节点）都必须
        经过本方法才能成为证据。返回正文与元数据全部来自同一不可变
        ``resource_versions`` / ``current_knowledge_targets`` 行，不猜 latest。
        """
        if len(resource_ids) != len(resource_versions):
            raise ValueError("resource_ids and resource_versions must be aligned")
        if not resource_ids:
            return []
        normalized_ids: list[str] = []
        for resource_id in resource_ids:
            try:
                normalized_ids.append(str(uuid.UUID(str(resource_id))))
            except (ValueError, TypeError, AttributeError) as exc:
                raise ValueError("resource_ids must contain UUID values") from exc
        if any(
            not isinstance(version, int)
            or isinstance(version, bool)
            or version <= 0
            for version in resource_versions
        ):
            raise ValueError("resource_versions must contain positive integers")

        asset_kinds = [value.strip() for value in (asset_kinds or []) if value.strip()]
        source_kinds = [value.strip() for value in (source_kinds or []) if value.strip()]
        niches = [value.strip() for value in (niches or []) if value.strip()]
        if min_quality is not None and not 0.0 <= float(min_quality) <= 1.0:
            raise ValueError("min_quality must be between 0 and 1")

        readable = self.readable_resource_where("r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    f"""
                    with requested(resource_id, resource_version, ordinal) as (
                      select *
                      from unnest(
                        %(resource_ids)s::uuid[],
                        %(resource_versions)s::int[]
                      ) with ordinality
                    )
                    select target.resource_id::text as resource_id,
                           target.resource_version,
                           target.resource_type,
                           target.title,
                           target.summary,
                           target.content_text,
                           target.content_json,
                           target.asset_kind,
                           target.source_kind,
                           target.source_authority,
                           target.quality_score,
                           target.duplicate_family_id::text as duplicate_family_id,
                           target.qualified_at,
                           target.indexed_at,
                           target.metadata || coalesce(enrichment.payload, '{{}}'::jsonb)
                             as metadata,
                           coalesce(
                             nullif(enrichment.payload->>'niche', ''),
                             nullif(target.content_json->>'niche', ''),
                             nullif(target.content_json->>'vertical', '')
                           ) as niche,
                           (
                             select max(mapping.external_updated_at)
                             from resource_mappings mapping
                             where mapping.tenant_id = target.tenant_id
                               and mapping.resource_id = target.resource_id
                           ) as source_updated_at
                    from requested req
                    join current_knowledge_targets target
                      on target.resource_id = req.resource_id
                     and target.resource_version = req.resource_version
                    join resources r
                      on r.tenant_id = target.tenant_id
                     and r.id = target.resource_id
                    left join lateral (
                      select knowledge_enrichments.payload
                      from knowledge_enrichments
                      where knowledge_enrichments.tenant_id = target.tenant_id
                        and knowledge_enrichments.resource_id = target.resource_id
                        and knowledge_enrichments.resource_version = target.resource_version
                        and knowledge_enrichments.enrichment_type = 'deterministic_metadata'
                      order by knowledge_enrichments.created_at desc,
                               knowledge_enrichments.id desc
                      limit 1
                    ) enrichment on true
                    where {readable}
                      and (
                        not %(has_asset_kinds)s
                        or target.asset_kind = any(%(asset_kinds)s::text[])
                      )
                      and (
                        not %(has_source_kinds)s
                        or target.source_kind = any(%(source_kinds)s::text[])
                      )
                      and (
                        not %(has_niches)s
                        or coalesce(
                          nullif(enrichment.payload->>'niche', ''),
                          nullif(target.content_json->>'niche', ''),
                          nullif(target.content_json->>'vertical', '')
                        ) = any(%(niches)s::text[])
                      )
                      and (
                        %(min_quality)s::double precision is null
                        or target.quality_score >= %(min_quality)s
                      )
                      and (
                        %(updated_after)s::timestamptz is null
                        or target.qualified_at >= %(updated_after)s
                      )
                    order by req.ordinal
                    """,
                    {
                        "resource_ids": normalized_ids,
                        "resource_versions": resource_versions,
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                        "has_asset_kinds": bool(asset_kinds),
                        "asset_kinds": asset_kinds,
                        "has_source_kinds": bool(source_kinds),
                        "source_kinds": source_kinds,
                        "has_niches": bool(niches),
                        "niches": niches,
                        "min_quality": min_quality,
                        "updated_after": updated_after,
                    },
                ).fetchall()
        return [dict(row) for row in rows]

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
        where_clause = self.readable_resource_where("r")
        # HNSW 召回宽度 ef_search:pgvector 默认 40,当 top_k 上探到 100(工具层 5× over-fetch
        # 的候选头寸)时,默认 40 会让候选池在近邻图上过早收敛、召回不足。按 top_k 放宽 ef_search
        # (且 ef_search 需 ≥ limit),让候选真正取满再交给统一 RRF 精排 —— 直接提召回。
        # 上限 400 兜住极端 top_k 的查询开销。连接非 autocommit,SET LOCAL 作用于本次隐式事务。
        # 注意:该参数只对 HNSW 索引生效 —— schema.sql 的条件升级块负责 ivfflat→HNSW,
        # 且 http_app 启动时显式跑迁移保证生产已升级(否则这里是 no-op 死代码)。
        ef_search = hnsw_ef_search_width(top_k)
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                # 作为事务内首条语句设置,仅本事务生效,不污染连接池上后续查询。
                cursor.execute(f"SET LOCAL hnsw.ef_search = {ef_search}")
                rows = cursor.execute(
                    f"""
                    with candidates as (
                      select r.id, r.tenant_id, r.type,
                             coalesce(nullif(rv.content_json->>'title', ''), r.title) as title,
                             r.summary, rv.content_text, rv.content_json,
                             r.status, r.visibility, r.owner_open_id, r.created_at, r.updated_at,
                             e.chunk_index, e.chunk_text,
                             (
                               select max(rm.external_updated_at)
                               from resource_mappings rm
                               where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                             ) as source_updated_at,
                             1 - (e.embedding <=> %(vector)s::public.vector) as score,
                             row_number() over (
                               partition by r.id
                               order by e.embedding <=> %(vector)s::public.vector, e.chunk_index
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
                      join current_knowledge_targets target
                        on target.tenant_id = e.tenant_id
                       and target.resource_id = e.resource_id
                       and target.resource_version = e.resource_version
                      where e.embedding_model = %(embedding_model)s
                        and {where_clause}
                    )
                    select * from candidates
                    where resource_rank = 1
                    order by score desc, updated_at desc
                    limit %(top_k)s
                    """,
                    {
                        "vector": vector_literal,
                        "embedding_model": embedding_model,
                        "top_k": top_k,
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                    },
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
                    """
                    select r.id::text as id, r.type, r.visibility, r.owner_open_id,
                           (select max(rv.version) from resource_versions rv
                            where rv.tenant_id = r.tenant_id and rv.resource_id = r.id) as version
                    from resources r where r.id = %s and r.tenant_id = %s
                    """,
                    (resource_id, tenant_id),
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

    def resource_version_exists(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
        conn: Optional[Connection] = None,
    ) -> bool:
        with self.connection_context(conn) as connection:
            row = connection.execute(
                """
                select 1 from resource_versions
                where tenant_id = %s and resource_id = %s and version = %s
                """,
                (tenant_id, resource_id, resource_version),
            ).fetchone()
            return row is not None

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
        source_resource_version: int,
        target_resource_id: str,
        target_resource_version: int,
        edge_type: str,
        weight: float = 1.0,
        properties: dict | None = None,
        conn: Optional[Connection] = None,
    ) -> None:
        from data_foundation.repositories.feedback import FeedbackRepository
        FeedbackRepository(conn or self.conn).add_edge(
            tenant_id=tenant_id,
            source_resource_id=source_resource_id,
            source_resource_version=source_resource_version,
            target_resource_id=target_resource_id,
            target_resource_version=target_resource_version,
            edge_type=edge_type,
            weight=weight,
            properties=properties,
            conn=conn or self.conn,
        )

    def ensure_resource_association(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        resource_version: int,
        source_topic: str | None = None,
        conn: Optional[Connection] = None,
    ) -> bool:
        """保证新素材至少有一条图关联；无强证据时挂同主题/同作者弱关联。

        强关联由上层先写 derived_from / imitated_from。本方法只在仍无出边时，从 actor
        可读的既有选题或文案中选最近一条；全库第一条素材没有可连对象时返回 False。
        """
        if (
            not isinstance(resource_version, int)
            or isinstance(resource_version, bool)
            or resource_version <= 0
        ):
            raise ValueError("resource_version must be a positive integer")
        where_clause = self.readable_resource_where("r")
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                exists = cursor.execute(
                    """
                    select 1 from resource_edges
                    where tenant_id = %s
                      and source_resource_id = %s
                      and source_resource_version = %s
                    limit 1
                    """,
                    (tenant_id, resource_id, resource_version),
                ).fetchone()
                if exists is not None:
                    return True
                target = cursor.execute(
                    f"""
                    select r.id::text as id,
                           latest.version as resource_version
                    from resources r
                    join lateral (
                      select rv.version
                      from resource_versions rv
                      where rv.tenant_id = r.tenant_id and rv.resource_id = r.id
                      order by rv.version desc
                      limit 1
                    ) latest on true
                    where r.id <> %(resource_id)s
                      and r.type in ('generated_topic', 'generated_copy', 'xhs_note', 'xhs_online_note')
                      and {where_clause}
                    order by
                      case when %(source_topic)s <> '' and
                                     (r.summary = %(source_topic)s or r.content_text ilike '%%' || %(source_topic)s || '%%')
                           then 0 else 1 end,
                      r.updated_at desc,
                      r.id desc
                    limit 1
                    """,
                    {
                        "resource_id": resource_id,
                        "source_topic": source_topic or "",
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                    },
                ).fetchone()
                if target is None:
                    return False
                self.add_edge(
                    tenant_id=tenant_id,
                    source_resource_id=resource_id,
                    source_resource_version=resource_version,
                    target_resource_id=target["id"],
                    target_resource_version=int(target["resource_version"]),
                    edge_type="same_topic",
                    weight=0.1,
                    conn=connection,
                )
                return True

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

    def bulk_exact_performance_metrics(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_ids: list[str],
        resource_versions: list[int],
        conn: Optional[Connection] = None,
    ) -> dict[tuple[str, int], list[dict[str, Any]]]:
        from data_foundation.repositories.performance import PerformanceRepository

        return PerformanceRepository(conn or self.conn).bulk_exact_performance_metrics(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_ids=resource_ids,
            resource_versions=resource_versions,
            conn=conn or self.conn,
        )

    def debug_counts(self, conn: Optional[Connection] = None) -> dict[str, int]:
        names = ["resources", "resource_versions", "resource_events", "resource_mappings", "resource_outbox"]
        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                return {name: cursor.execute(f"select count(*) as c from {name}").fetchone()["c"] for name in names}
