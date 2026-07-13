"""引擎索引对账(检测 Meili/Falkor 相对 Postgres 的数据丢失)。

为什么需要:Meili/Falkor 的写是"PG outbox 标 succeeded + 引擎入库"两段式。引擎数据卷丢失
重建后引擎空了,但 outbox 早已 succeeded、upsert_resource 对未变内容不再 enqueue → 全文检索 /
图谱永久残缺,无人重推(embedding 有自己的 reconcile 兜底,Meili/Falkor 没有)。

本模块提供**纯对账逻辑**:给定每租户 PG 应有资源数、引擎实际行数、以及在途(尚未 succeeded)的
outbox 任务数,判定哪些 (tenant, topic) 出现了"即便把在途任务全算上仍不足额"的真实丢失。
把在途算进来是关键防误报:正常 backlog(刚 upsert、worker 还没消费)不该被当成数据丢失。

判定为丢失的 (tenant, topic) 由调用方(scripts/detect_engine_drift.py)决定是否按租户精准重推
(requeue_succeeded),避免对整库做钝重的全量重推。
"""
from __future__ import annotations

from dataclasses import dataclass


TOPIC_MEILI = "meili_index"
TOPIC_GRAPH = "graph_ingest"
ENGINE_TOPICS = (TOPIC_MEILI, TOPIC_GRAPH)


@dataclass(frozen=True)
class DriftEntry:
    tenant_id: str
    topic: str
    expected: int   # PG 应有(当前存在的资源数)
    actual: int     # 引擎实际行数
    pending: int    # 在途(pending/retry/processing)outbox 任务数
    missing: int    # 即便算上在途仍缺的量 = expected - actual - pending(>0)


def detect_index_drift(
    *,
    expected_by_topic: dict[str, dict[str, int]],
    engine_actual: dict[str, dict[str, int]],
    engine_pending: dict[str, dict[str, int]],
) -> list[DriftEntry]:
    """纯函数:对账 PG 应有数 vs 引擎实际 + 在途,返回真实丢失项。

    参数:
    - expected_by_topic:{topic: {tenant: PG 对该引擎应有的资源数}}
    - engine_actual:{topic: {tenant: 引擎实际行数}}
    - engine_pending:{topic: {tenant: 在途 outbox 任务数}}

    判定:对每个 (tenant, topic),若 actual + pending < expected,说明即便把所有在途任务
    都成功消费也补不齐 → 引擎确有丢失(而非正常 backlog)。expected<=0 的租户跳过。
    """
    entries: list[DriftEntry] = []
    for topic in ENGINE_TOPICS:
        # Absence of a topic means that engine is disabled/unconfigured.  An enabled
        # but empty engine is represented explicitly as ``topic: {}`` and is audited.
        if topic not in engine_actual:
            continue
        for tenant_id in sorted(expected_by_topic.get(topic, {})):
            expected = int(expected_by_topic.get(topic, {}).get(tenant_id, 0))
            if expected <= 0:
                continue
            actual = int(engine_actual.get(topic, {}).get(tenant_id, 0))
            pending = int(engine_pending.get(topic, {}).get(tenant_id, 0))
            missing = expected - actual - pending
            if missing > 0:
                entries.append(
                    DriftEntry(
                        tenant_id=tenant_id,
                        topic=topic,
                        expected=expected,
                        actual=actual,
                        pending=pending,
                        missing=missing,
                    )
                )
    return entries
