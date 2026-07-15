"""按任务类型控制证据组成与图扩展预算。"""
from __future__ import annotations

import re
from typing import Literal, Sequence, TypeVar


RetrievalTask = Literal[
    "general", "copywriting", "imitation", "topic", "teardown", "diagnosis", "polish"
]

_TASK_RULES: tuple[tuple[RetrievalTask, re.Pattern[str]], ...] = (
    ("imitation", re.compile(r"仿写|照着|模仿|套路")),
    ("teardown", re.compile(r"拆解|拆爆款|分析爆款|为什么火")),
    ("topic", re.compile(r"选题|方向|灵感|话题")),
    ("polish", re.compile(r"润色|改写|优化|去.?ai|精简|缩短")),
    ("diagnosis", re.compile(r"诊断|复盘|问题|定位|效果")),
    ("copywriting", re.compile(r"写.*文案|写一篇|生成.*文案|起标题|开头")),
)

_QUOTAS: dict[RetrievalTask, tuple[tuple[str, float], ...]] = {
    "copywriting": (("copy", 0.4), ("pattern", 0.2), ("teardown", 0.2), ("source_material", 0.2)),
    "polish": (("copy", 0.5), ("pattern", 0.2), ("teardown", 0.2), ("source_material", 0.1)),
    "imitation": (("teardown", 0.4), ("copy", 0.3), ("pattern", 0.2), ("source_material", 0.1)),
    "topic": (("source_material", 0.5), ("copy", 0.2), ("pattern", 0.2), ("strategy_fact", 0.1)),
    "teardown": (("teardown", 0.4), ("copy", 0.3), ("source_material", 0.2), ("pattern", 0.1)),
    "diagnosis": (("strategy_fact", 0.3), ("pattern", 0.3), ("copy", 0.2), ("teardown", 0.2)),
}

_GRAPH_EDGES: dict[RetrievalTask, tuple[str, ...]] = {
    "copywriting": ("semantically_related", "derived_from", "imitated_from", "synthesized_from", "teardown_of"),
    "polish": ("semantically_related", "derived_from", "revised_from", "co_generated_variant"),
    "imitation": ("imitated_from", "teardown_of", "semantically_related", "synthesized_from"),
    "topic": ("semantically_related", "co_ingested", "derived_from", "synthesized_from"),
    "teardown": ("teardown_of", "measured_by", "semantically_related", "imitated_from"),
    "diagnosis": ("measured_by", "feedback_on", "learned_from", "synthesized_from", "revised_from"),
    "general": ("semantically_related", "derived_from", "teardown_of", "synthesized_from"),
}

T = TypeVar("T")


def infer_retrieval_task(query: str) -> RetrievalTask:
    for task, pattern in _TASK_RULES:
        if pattern.search(query):
            return task
    return "general"


def validate_retrieval_task(value: str | None, *, query: str) -> RetrievalTask:
    if value is None or not value.strip():
        return infer_retrieval_task(query)
    cleaned = value.strip().lower()
    allowed = {"general", "copywriting", "imitation", "topic", "teardown", "diagnosis", "polish"}
    if cleaned not in allowed:
        raise ValueError("unsupported retrieval task")
    return cleaned  # type: ignore[return-value]


def graph_edge_types(task: RetrievalTask) -> list[str]:
    return list(_GRAPH_EDGES[task])


def select_task_bundle(
    items: Sequence[T], *, task: RetrievalTask, limit: int
) -> list[T]:
    safe_limit = max(int(limit), 1)
    quotas = _QUOTAS.get(task)
    if not quotas:
        return list(items[:safe_limit])
    selected: list[T] = []
    selected_ids: set[int] = set()
    for asset_kind, ratio in quotas:
        if len(selected) >= safe_limit:
            break
        target = max(1, int(safe_limit * ratio))
        for index, item in enumerate(items):
            if len(selected) >= safe_limit:
                break
            if index in selected_ids or getattr(item, "asset_kind", None) != asset_kind:
                continue
            selected.append(item)
            selected_ids.add(index)
            if sum(getattr(chosen, "asset_kind", None) == asset_kind for chosen in selected) >= target:
                break
    for index, item in enumerate(items):
        if len(selected) >= safe_limit:
            break
        if index not in selected_ids:
            selected.append(item)
            selected_ids.add(index)
    # 组成配额只决定“谁入选”，最终展示仍沿用原精排相对顺序。
    positions = {id(item): index for index, item in enumerate(items)}
    selected.sort(key=lambda item: positions[id(item)])
    return selected[:safe_limit]


__all__ = [
    "RetrievalTask",
    "graph_edge_types",
    "infer_retrieval_task",
    "select_task_bundle",
    "validate_retrieval_task",
]
