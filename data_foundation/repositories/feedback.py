import hashlib
import hashlib
import json
import math
import re
import uuid
from typing import Optional

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.repositories.base import BaseRepository
from data_foundation.models import RuntimeIdentityConfig


class FeedbackRepository(BaseRepository):
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
        edge_type = edge_type.strip() if edge_type else ""
        if not edge_type:
            raise ValueError("Edge type is required")
        if not math.isfinite(weight):
            raise ValueError("Edge weight must be finite")
        for field, value in (
            ("source_resource_version", source_resource_version),
            ("target_resource_version", target_resource_version),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{field} must be a positive integer")
        if properties is not None and not isinstance(properties, dict):
            raise ValueError("Edge properties must be an object")
        edge_properties = dict(properties or {})
        edge_properties.update(
            {
                "source_resource_version": source_resource_version,
                "target_resource_version": target_resource_version,
            }
        )
        try:
            properties_json = json.dumps(
                edge_properties, sort_keys=True, ensure_ascii=False
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Edge properties must be JSON serializable") from exc

        endpoint_ids = sorted(list({str(source_resource_id), str(target_resource_id)}))

        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    # Lock/verify endpoints
                    res = cursor.execute(
                        "select count(*) as count from resources where tenant_id = %s and id = any(%s::uuid[])",
                        (tenant_id, endpoint_ids),
                    ).fetchone()
                    if res["count"] != len(endpoint_ids):
                        raise PermissionError("Both edge endpoints must belong to this tenant")

                    version_count = cursor.execute(
                        """
                        select count(*) as count
                        from resource_versions
                        where tenant_id = %s
                          and (
                            (resource_id = %s and version = %s)
                            or (resource_id = %s and version = %s)
                          )
                        """,
                        (
                            tenant_id,
                            source_resource_id,
                            source_resource_version,
                            target_resource_id,
                            target_resource_version,
                        ),
                    ).fetchone()
                    expected_versions = 1 if (
                        str(source_resource_id) == str(target_resource_id)
                        and source_resource_version == target_resource_version
                    ) else 2
                    if version_count["count"] != expected_versions:
                        raise ValueError("Both exact edge endpoint versions must exist")

                    cursor.execute(
                        """
                        insert into resource_edges (
                          tenant_id,
                          source_resource_id, source_resource_version,
                          target_resource_id, target_resource_version,
                          edge_type, weight, properties
                        )
                        values (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                        on conflict(
                          tenant_id,
                          source_resource_id, source_resource_version,
                          target_resource_id, target_resource_version,
                          edge_type
                        )
                        do update set weight = excluded.weight,
                                      properties = excluded.properties
                        """,
                        (
                            tenant_id,
                            source_resource_id,
                            source_resource_version,
                            target_resource_id,
                            target_resource_version,
                            edge_type,
                            weight,
                            properties_json,
                        ),
                    )

                    # Enqueue outbox task for graph_ingest
                    # dedupe_key 必须含边维度(target+edge_type):否则与 upsert_resource 对同
                    # (resource,version) 生成的 node-ingest key 相同 → 节点先入图标 succeeded 后,
                    # 加边再 enqueue 同 key → on conflict do nothing → 任务不创建 → 边永不入 FalkorDB
                    # (measured_by/derived_from/feedback_on 边在节点首次入图后添加的全部丢失)。
                    # 加上 (target, edge_type) 后,每条新边都是独立任务,触发重新 ingest 节点+其全部边
                    # (processor 读当前所有边,幂等)。
                    topic = "graph_ingest"
                    dedupe_parts = (
                        "graph",
                        "edge",
                        str(source_resource_version),
                        str(target_resource_id),
                        str(target_resource_version),
                        edge_type,
                        float(weight),
                        properties_json,
                    )
                    payload = {
                        "resource_id": str(source_resource_id),
                        "version": source_resource_version,
                    }
                    dedupe_key = hashlib.sha256(
                        json.dumps(
                            [
                                tenant_id,
                                str(source_resource_id),
                                source_resource_version,
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
                            source_resource_id,
                            source_resource_version,
                            None,
                            topic,
                            dedupe_key,
                            json.dumps(payload, sort_keys=True, ensure_ascii=False),
                        )
                    )

    def remove_edge(
        self,
        *,
        tenant_id: str,
        source_resource_id: str,
        source_resource_version: int,
        target_resource_id: str,
        target_resource_version: int,
        edge_type: str,
        conn: Optional[Connection] = None,
    ) -> bool:
        """Delete one exact PG edge and enqueue source-version graph reconciliation."""
        with self.connection_context(conn) as connection:
            with connection.transaction():
                with connection.cursor(row_factory=dict_row) as cursor:
                    deleted = cursor.execute(
                        """
                        delete from resource_edges
                        where tenant_id = %s
                          and source_resource_id = %s and source_resource_version = %s
                          and target_resource_id = %s and target_resource_version = %s
                          and edge_type = %s
                        returning weight, properties
                        """,
                        (
                            tenant_id,
                            source_resource_id,
                            source_resource_version,
                            target_resource_id,
                            target_resource_version,
                            edge_type,
                        ),
                    ).fetchone()
                    if deleted is None:
                        return False
                    identity = [
                        tenant_id,
                        source_resource_id,
                        source_resource_version,
                        target_resource_id,
                        target_resource_version,
                        edge_type,
                        "delete",
                        float(deleted["weight"]),
                        dict(deleted["properties"] or {}),
                    ]
                    dedupe_key = hashlib.sha256(
                        json.dumps(identity, sort_keys=True, ensure_ascii=False).encode("utf-8")
                    ).hexdigest()
                    cursor.execute(
                        """
                        insert into resource_outbox (
                          tenant_id, resource_id, resource_version, topic, dedupe_key, payload
                        ) values (
                          %s, %s, %s, 'graph_ingest', %s,
                          jsonb_build_object('resource_id', %s::text, 'version', %s::int)
                        )
                        on conflict (tenant_id, dedupe_key) do nothing
                        """,
                        (
                            tenant_id,
                            source_resource_id,
                            source_resource_version,
                            dedupe_key,
                            source_resource_id,
                            source_resource_version,
                        ),
                    )
                    return True

    def create_edge(
        self,
        source_id: str,
        source_version: int,
        target_id: str,
        target_version: int,
        edge_type: str,
        actor: RuntimeIdentityConfig,
        conn: Optional[Connection] = None,
    ) -> None:
        try:
            uuid.UUID(str(source_id))
            uuid.UUID(str(target_id))
        except (ValueError, TypeError, AttributeError):
            raise PermissionError("Invalid UUID format")

        edge_type = edge_type.strip() if edge_type else ""
        if not edge_type:
            raise ValueError("Edge type is required")

        with self.connection_context(conn) as connection:
            with connection.transaction():
                from data_foundation.repositories.resource import ResourceRepository
                res_repo = ResourceRepository()
                
                try:
                    res_repo.check_permission(source_id, actor, permission="write", conn=connection)
                except PermissionError:
                    raise PermissionError("Source resource does not exist or unauthorized")

                try:
                    res_repo.check_permission(target_id, actor, permission="read", conn=connection)
                except PermissionError:
                    raise PermissionError("Target resource does not exist or unauthorized")

                self.add_edge(
                    tenant_id=actor.tenant_id,
                    source_resource_id=source_id,
                    source_resource_version=source_version,
                    target_resource_id=target_id,
                    target_resource_version=target_version,
                    edge_type=edge_type,
                    conn=connection,
                )
