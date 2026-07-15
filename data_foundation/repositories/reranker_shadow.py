from __future__ import annotations

import hashlib
from typing import Any

from data_foundation.repositories.base import BaseRepository
from data_foundation.reranker_shadow import RerankerShadowObservation


class RerankerShadowRepository(BaseRepository):
    """只保存旁路排序摘要；不保存查询、标题、正文或模型响应。"""

    def record(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        experiment_id: str,
        task_type: str,
        observation: RerankerShadowObservation,
    ) -> dict[str, Any]:
        experiment = experiment_id.strip() if isinstance(experiment_id, str) else ""
        if not experiment:
            raise ValueError("experiment_id is required")
        actor_key = hashlib.sha256(
            f"{tenant_id}\0{actor_open_id}".encode("utf-8")
        ).hexdigest()
        with self.connection_context() as connection:
            row = connection.execute(
                """
                insert into knowledge_reranker_shadow_runs (
                  tenant_id, actor_key, experiment_id, task_type, candidate_count,
                  top1_changed, top_k_overlap, mean_rank_displacement,
                  baseline_order_hash, shadow_order_hash
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                returning id::text, created_at
                """,
                (
                    tenant_id,
                    actor_key,
                    experiment,
                    task_type,
                    observation.candidate_count,
                    observation.top1_changed,
                    observation.top_k_overlap,
                    observation.mean_rank_displacement,
                    observation.baseline_order_hash,
                    observation.shadow_order_hash,
                ),
            ).fetchone()
        return {"id": str(row["id"]), "created_at": row["created_at"]}


__all__ = ["RerankerShadowRepository"]
