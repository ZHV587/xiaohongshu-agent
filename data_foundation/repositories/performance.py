from typing import Optional, Any
from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.repositories.base import BaseRepository
from data_foundation.models import RuntimeIdentityConfig


class PerformanceRepository(BaseRepository):
    def save_performance(
        self,
        resource_id: str,
        resource_version: int,
        likes: int,
        comments: int,
        shares: int,
        actor: RuntimeIdentityConfig,
        conn: Optional[Connection] = None,
    ) -> float:
        score = float(likes * 1 + comments * 2 + shares * 3)

        from data_foundation.repositories.resource import ResourceRepository
        from data_foundation.repositories.feedback import FeedbackRepository

        res_repo = ResourceRepository()
        fb_repo = FeedbackRepository()

        with self.connection_context(conn) as connection:
            with connection.transaction():
                # 1. Lock/verify write permission on target resource
                res_repo.check_permission(resource_id, actor, permission="write", conn=connection)

                # 2. Lock target resource row and verify it exists
                with connection.cursor(row_factory=dict_row) as cursor:
                    if (
                        not isinstance(resource_version, int)
                        or isinstance(resource_version, bool)
                        or resource_version <= 0
                    ):
                        raise ValueError("resource_version must be a positive integer")
                    target = cursor.execute(
                        """
                        select r.id, r.visibility, r.owner_open_id
                        from resources r
                        join resource_versions rv
                          on rv.tenant_id = r.tenant_id and rv.resource_id = r.id
                        where r.id = %s and rv.version = %s
                        for update of r
                        """,
                        (resource_id, resource_version),
                    ).fetchone()
                    if not target:
                        raise ValueError("Resource not found")

                    target_visibility = target["visibility"]
                    target_owner_open_id = target["owner_open_id"]

                    # Query if a performance_metric resource already exists for this target_resource_id
                    existing_metric = cursor.execute(
                        """
                        SELECT id FROM resources
                        WHERE tenant_id = %s
                          AND type = 'performance_metric'
                          AND content_json->>'target_resource_id' = %s
                        """,
                        (actor.tenant_id, resource_id),
                    ).fetchone()
                    metric_id = str(existing_metric["id"]) if existing_metric else None

                # 3. Upsert the performance metric resource(单一 kwargs 契约;outbox 默认走 default_write_requests)
                upserted_metric = res_repo.upsert_resource(
                    tenant_id=actor.tenant_id,
                    actor_open_id=actor.open_id,
                    resource_id=metric_id,
                    resource_type="performance_metric",
                    title="效果数据",
                    content_json={
                        "target_resource_id": resource_id,
                        "target_resource_version": resource_version,
                        "metrics": {
                            "likes": likes,
                            "comments": comments,
                            "shares": shares,
                        },
                        "score": score,
                    },
                    visibility=target_visibility,
                    owner_open_id=target_owner_open_id,
                    conn=connection,
                )

                # 4. Add measured_by edge from target to metric
                fb_repo.add_edge(
                    tenant_id=actor.tenant_id,
                    source_resource_id=resource_id,
                    source_resource_version=resource_version,
                    target_resource_id=upserted_metric.id,
                    target_resource_version=int(upserted_metric.version),
                    edge_type="measured_by",
                    weight=score,
                    conn=connection,
                )

                return score

    def performance_rows(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_id: str,
        conn: Optional[Connection] = None,
    ) -> list[dict]:
        target_where = self.readable_resource_where("target")
        metric_where = self.readable_resource_where("metric")

        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    f"""
                    SELECT 
                        metric.id::text as resource_id,
                        metric.title,
                        metric.content_json,
                        e.weight,
                        metric.updated_at
                    FROM resources target
                    JOIN resource_edges e
                      ON e.tenant_id = target.tenant_id
                     AND e.source_resource_id = target.id
                     AND e.edge_type = 'measured_by'
                    JOIN resources metric
                      ON metric.tenant_id = target.tenant_id
                     AND metric.id = e.target_resource_id
                     AND metric.type = 'performance_metric'
                    WHERE target.id = %(resource_id)s
                      AND {target_where}
                      AND {metric_where}
                    ORDER BY metric.updated_at DESC, metric.id DESC
                    """,
                    {
                        "resource_id": resource_id,
                        "tenant_id": tenant_id,
                        "actor_open_id": actor_open_id,
                    },
                ).fetchall()
                return [dict(row) for row in rows]

    def bulk_performance_metrics(
        self,
        tenant_id: str,
        resource_ids: list[str],
        actor: Optional[RuntimeIdentityConfig] = None,
        conn: Optional[Connection] = None,
    ) -> dict[str, list[dict[str, Any]]]:
        if not resource_ids:
            return {}

        if actor is not None:
            target_where = self.readable_resource_where("target")
            metric_where = self.readable_resource_where("metric")
            params = {
                "resource_ids": resource_ids,
                "tenant_id": actor.tenant_id,
                "actor_open_id": actor.open_id,
            }
        else:
            target_where = "target.tenant_id = %(tenant_id)s"
            metric_where = "1=1"
            params = {"resource_ids": resource_ids, "tenant_id": tenant_id}

        with self.connection_context(conn) as connection:
            with connection.cursor(row_factory=dict_row) as cursor:
                rows = cursor.execute(
                    f"""
                    SELECT target.id::text as target_resource_id,
                        metric.id,
                        metric.title,
                        metric.content_json,
                        e.weight,
                        metric.updated_at
                    FROM resources target
                    JOIN resource_edges e
                      ON e.tenant_id = target.tenant_id
                     AND e.source_resource_id = target.id
                     AND e.edge_type = 'measured_by'
                    JOIN resources metric
                      ON metric.tenant_id = target.tenant_id
                     AND metric.id = e.target_resource_id
                     AND metric.type = 'performance_metric'
                    WHERE target.id = ANY(%(resource_ids)s::uuid[])
                      AND {target_where}
                      AND {metric_where}
                    ORDER BY metric.updated_at DESC, metric.id DESC
                    """,
                    params,
                ).fetchall()

                result: dict[str, list[dict[str, Any]]] = {str(rid): [] for rid in resource_ids}
                for row in rows:
                    content_json = dict(row["content_json"]) if row["content_json"] is not None else {}
                    result[str(row["target_resource_id"])].append({
                        "resource_id": str(row["id"]),
                        "title": row["title"],
                        "score": float(content_json.get("score", row.get("weight", 0.0))),
                        "metrics": dict(content_json.get("metrics") or {}),
                        "channel": content_json.get("channel"),
                        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                    })
                return result
