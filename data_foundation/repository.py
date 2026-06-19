from __future__ import annotations

import hashlib
import json
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
                self.conn.execute(
                    """
                    insert into resource_mappings (
                      tenant_id, resource_id, system, external_type, external_id, external_url,
                      external_updated_at, sync_cursor, sync_status, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, 'pending'), now())
                    on conflict(tenant_id, system, external_type, external_id)
                    do update set resource_id = excluded.resource_id,
                                  external_url = excluded.external_url,
                                  external_updated_at = excluded.external_updated_at,
                                  sync_cursor = excluded.sync_cursor,
                                  sync_status = excluded.sync_status,
                                  updated_at = now()
                    """,
                    (
                        tenant_id,
                        row["id"],
                        mapping["system"],
                        mapping["external_type"],
                        mapping["external_id"],
                        mapping.get("external_url"),
                        mapping.get("external_updated_at"),
                        mapping.get("sync_cursor"),
                        mapping.get("sync_status"),
                    ),
                )

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
