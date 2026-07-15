"""候选 reranker 的只读影子实验契约。

影子排序只能重排已经通过 PostgreSQL 精确版本/ACL 门的候选，不能增加、删除或替换
身份，也绝不能改变线上返回顺序。观察结果不含查询正文和候选正文，持久化层只保存顺序
摘要与聚合差异，供真实标注集离线配对评估。
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence
import uuid


ExactIdentity = tuple[str, int]


@dataclass(frozen=True)
class RerankerShadowObservation:
    baseline_order: tuple[ExactIdentity, ...]
    shadow_order: tuple[ExactIdentity, ...]
    top1_changed: bool
    top_k_overlap: float
    mean_rank_displacement: float

    @property
    def candidate_count(self) -> int:
        return len(self.baseline_order)

    @property
    def baseline_order_hash(self) -> str:
        return order_hash(self.baseline_order)

    @property
    def shadow_order_hash(self) -> str:
        return order_hash(self.shadow_order)


def execute_shadow_rerank(
    *,
    query: str,
    ranked_candidates: Sequence[Any],
    reranker: Any,
) -> RerankerShadowObservation:
    """执行一次旁路重排并验证它是同一候选集合的严格排列。"""

    baseline = tuple(_candidate_identity(item) for item in ranked_candidates)
    if not baseline:
        raise ValueError("shadow reranker requires candidates")
    if len(set(baseline)) != len(baseline):
        raise ValueError("baseline candidates must have unique exact identities")
    raw = reranker(query=query, candidates=tuple(ranked_candidates))
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise ValueError("shadow reranker must return an identity sequence")
    shadow = tuple(_candidate_identity(item) for item in raw)
    if len(shadow) != len(baseline) or len(set(shadow)) != len(shadow):
        raise ValueError("shadow order must contain every candidate exactly once")
    if set(shadow) != set(baseline):
        raise ValueError("shadow reranker cannot change the authorized candidate set")

    baseline_rank = {identity: index for index, identity in enumerate(baseline)}
    displacement = sum(
        abs(index - baseline_rank[identity]) for index, identity in enumerate(shadow)
    ) / len(baseline)
    overlap_k = min(3, len(baseline))
    overlap = len(set(baseline[:overlap_k]) & set(shadow[:overlap_k])) / overlap_k
    return RerankerShadowObservation(
        baseline_order=baseline,
        shadow_order=shadow,
        top1_changed=baseline[0] != shadow[0],
        top_k_overlap=round(overlap, 6),
        mean_rank_displacement=round(displacement, 6),
    )


def order_hash(order: Sequence[ExactIdentity]) -> str:
    encoded = json.dumps(list(order), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _candidate_identity(value: Any) -> ExactIdentity:
    if isinstance(value, Mapping):
        resource_id = value.get("resource_id")
        resource_version = value.get("resource_version")
    elif isinstance(value, tuple) and len(value) == 2:
        resource_id, resource_version = value
    else:
        resource_id = getattr(value, "resource_id", None)
        resource_version = getattr(value, "resource_version", None)
    try:
        normalized_id = str(uuid.UUID(str(resource_id)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("shadow identity resource_id must be a UUID") from exc
    if (
        not isinstance(resource_version, int)
        or isinstance(resource_version, bool)
        or resource_version <= 0
    ):
        raise ValueError("shadow identity resource_version must be positive")
    return normalized_id, resource_version


__all__ = [
    "ExactIdentity",
    "RerankerShadowObservation",
    "execute_shadow_rerank",
    "order_hash",
]
