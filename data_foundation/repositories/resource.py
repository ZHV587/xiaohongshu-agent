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
        resource: Resource,
        actor: RuntimeIdentityConfig,
        conn: Optional[Connection] = None
    ) -> Resource:
        """Upsert a resource, record version, events, type counts, and write to outbox."""
        
        tenant_id = actor.tenant_id
        actor_open_id = actor.open_id
        
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
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
                        # Update existing resource
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
                    
                    # Enqueue transactional outbox tasks
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

    def _resource_from_row(self, row: dict, version: int) -> Resource:
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
            version=version,
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

