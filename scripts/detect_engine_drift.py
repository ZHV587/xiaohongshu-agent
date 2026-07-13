"""引擎索引对账检测(Meili/Falkor 相对 Postgres 的数据丢失自动发现)。

为什么需要:Meili/Falkor 两段提交(PG outbox 标 succeeded + 引擎入库),引擎数据卷丢失重建后
引擎空了但 outbox 早已 succeeded、upsert 不再 enqueue → 检索/图谱永久残缺无人重推。
requeue_engine_index.py 是钝器(整库 succeeded→pending 全量重推);本脚本先**对账**,只对
真正丢失的租户精准重推。

对账口径(防误报):对每个 (tenant, topic),比较 PG 当前资源数(expected)与 引擎实际行数
(actual)+ 在途 outbox 任务数(pending)。仅当 actual + pending < expected(即便把所有在途
任务都成功消费也补不齐)才判定为真实丢失;正常 backlog 不会被误报。引擎未启用(未配置)的
topic 直接跳过。

用法(在 langgraph 容器内,带库 + 引擎):
    # 只报告,不改动:
    docker compose exec -T langgraph python scripts/detect_engine_drift.py
    # 检测到丢失则对相关租户精准重推(succeeded→pending,worker 下个 cycle 补齐):
    docker compose exec -T langgraph python scripts/detect_engine_drift.py --repair
"""
from __future__ import annotations

import argparse
import os
import sys

# 确保项目根在 path 中(脚本可在任意 cwd 直接 python 执行,对齐 web_bridge_runner.py)。
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from data_foundation.db import connect
from data_foundation.engine_config import falkor_config_from_env, meili_config_from_env
from data_foundation.index_drift import TOPIC_GRAPH, TOPIC_MEILI, detect_index_drift
from data_foundation.outbox_repository import OutboxRepository


def _expected_by_topic(conn) -> dict[str, dict[str, int]]:
    rows = conn.execute(
        """
        select r.tenant_id,
               count(*) as graph_n,
               (select count(*)
                from current_knowledge_targets target
                where target.tenant_id = r.tenant_id) as meili_n
        from resources r
        group by r.tenant_id
        """
    ).fetchall()
    return {
        TOPIC_GRAPH: {row["tenant_id"]: int(row["graph_n"]) for row in rows},
        TOPIC_MEILI: {row["tenant_id"]: int(row["meili_n"]) for row in rows},
    }


def _meili_counts(tenants: list[str]) -> tuple[dict[str, int], dict[str, int]] | None:
    cfg = meili_config_from_env()
    if cfg.state != "enabled":
        return None  # 引擎未启用:跳过该 topic 的对账
    from data_foundation.meili_client import MeiliResourceIndex

    index = MeiliResourceIndex.from_config(cfg)
    # 先等待 filterable settings 生效，再按租户分别统计总文档和当前 hybrid
    # schema 文档；旧结构即便有 resource_version 也不能掩盖 v2 重建缺失。
    index.ensure_index()
    usable: dict[str, int] = {}
    malformed: dict[str, int] = {}
    for tenant_id in tenants:
        audit = index.audit_tenant(tenant_id=tenant_id)
        usable[tenant_id] = audit.current_schema_documents
        malformed[tenant_id] = audit.stale_schema_documents
    return usable, malformed


def _falkor_counts(tenants: list[str]) -> dict[str, int] | None:
    cfg = falkor_config_from_env()
    if cfg.state != "enabled":
        return None
    from data_foundation.falkor_client import FalkorResourceGraph

    graph = FalkorResourceGraph.from_config(cfg)
    return {t: graph.count(tenant_id=t) for t in tenants}


def main() -> int:
    parser = argparse.ArgumentParser(description="引擎索引对账检测(默认只报告)")
    parser.add_argument(
        "--repair", action="store_true",
        help="检测到真实丢失时,对相关租户精准重推(succeeded→pending);省略则只报告",
    )
    args = parser.parse_args()

    conn = connect()
    try:
        expected = _expected_by_topic(conn)
        tenants = sorted(
            set(expected.get(TOPIC_GRAPH, {})) | set(expected.get(TOPIC_MEILI, {}))
        )
        outbox = OutboxRepository(conn)
        pending = outbox.pending_counts_by_topic(topics=[TOPIC_MEILI, TOPIC_GRAPH])

        engine_actual: dict[str, dict[str, int]] = {}
        skipped: list[str] = []
        meili_audit = _meili_counts(tenants)
        meili_malformed: dict[str, int] = {}
        if meili_audit is None:
            skipped.append(TOPIC_MEILI)
        else:
            meili, meili_malformed = meili_audit
            engine_actual[TOPIC_MEILI] = meili
        falkor = _falkor_counts(tenants)
        if falkor is None:
            skipped.append(TOPIC_GRAPH)
        else:
            engine_actual[TOPIC_GRAPH] = falkor

        drift = detect_index_drift(
            expected_by_topic=expected,
            engine_actual=engine_actual,
            engine_pending=pending,
        )

        if skipped:
            print(f"跳过未启用引擎的 topic:{skipped}")
        for tenant_id, malformed in sorted(meili_malformed.items()):
            if malformed > 0:
                print(
                    f"Meili 旧索引结构残留: tenant={tenant_id} "
                    f"stale_schema_documents={malformed}"
                )
        if not drift:
            print("对账通过:未检测到引擎数据丢失(已计入在途任务)。")
            return 0

        print(f"检测到 {len(drift)} 处引擎数据丢失:")
        for d in drift:
            print(
                f"  tenant={d.tenant_id} topic={d.topic} "
                f"expected={d.expected} actual={d.actual} pending={d.pending} missing={d.missing}"
            )

        if not args.repair:
            print("\n仅报告模式。确认无误后加 --repair 对上述租户精准重推。")
            return 0

        # 精准重推:只对有丢失的 (tenant, topic) requeue,不动其余。
        affected: dict[tuple[str, str], int] = {}
        for d in drift:
            n = outbox.requeue_succeeded(topics=[d.topic], tenant_id=d.tenant_id)
            affected[(d.tenant_id, d.topic)] = n
        print("\n已精准重推(worker 下个 cycle 补齐):")
        for (tenant_id, topic), n in affected.items():
            print(f"  tenant={tenant_id} topic={topic} requeued={n}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
