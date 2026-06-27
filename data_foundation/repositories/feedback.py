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
        target_resource_id: str,
        edge_type: str,
        weight: float = 1.0,
        conn: Optional[Connection] = None,
    ) -> None:
        edge_type = edge_type.strip() if edge_type else ""
        if not edge_type:
            raise ValueError("Edge type is required")
        if not math.isfinite(weight):
            raise ValueError("Edge weight must be finite")

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

                    cursor.execute(
                        """
                        insert into resource_edges (tenant_id, source_resource_id, target_resource_id, edge_type, weight)
                        values (%s, %s, %s, %s, %s)
                        on conflict(tenant_id, source_resource_id, target_resource_id, edge_type)
                        do update set weight = excluded.weight
                        """,
                        (tenant_id, source_resource_id, target_resource_id, edge_type, weight),
                    )

                    # Get source version
                    version_row = cursor.execute(
                        """
                        select version
                        from resource_versions
                        where tenant_id = %s and resource_id = %s
                        order by version desc
                        limit 1
                        """,
                        (tenant_id, source_resource_id),
                    ).fetchone()
                    if not version_row:
                        raise RuntimeError(f"Resource {source_resource_id} has no versions recorded")

                    source_version = version_row["version"]

                    # Enqueue outbox task for graph_ingest
                    # dedupe_key 必须含边维度(target+edge_type):否则与 upsert_resource 对同
                    # (resource,version) 生成的 node-ingest key 相同 → 节点先入图标 succeeded 后,
                    # 加边再 enqueue 同 key → on conflict do nothing → 任务不创建 → 边永不入 FalkorDB
                    # (measured_by/derived_from/feedback_on 边在节点首次入图后添加的全部丢失)。
                    # 加上 (target, edge_type) 后,每条新边都是独立任务,触发重新 ingest 节点+其全部边
                    # (processor 读当前所有边,幂等)。
                    topic = "graph_ingest"
                    dedupe_parts = ("graph", "edge", str(target_resource_id), edge_type)
                    payload = {
                        "resource_id": str(source_resource_id),
                        "version": source_version,
                    }
                    dedupe_key = hashlib.sha256(
                        json.dumps(
                            [
                                tenant_id,
                                str(source_resource_id),
                                source_version,
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
                            source_version,
                            None,
                            topic,
                            dedupe_key,
                            json.dumps(payload, sort_keys=True, ensure_ascii=False),
                        )
                    )

    def create_edge(
        self,
        source_id: str,
        target_id: str,
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
                    target_resource_id=target_id,
                    edge_type=edge_type,
                    conn=connection,
                )

