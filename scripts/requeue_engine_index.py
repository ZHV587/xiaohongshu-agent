"""引擎数据卷丢失后的检索/图谱恢复入口(运维一次性脚本)。

为什么需要:Meili/Falkor 的写是"PG outbox 标 succeeded + 引擎入库"两段式。引擎数据卷丢失
重建后,引擎里空了,但 outbox 早已 succeeded,且 upsert_resource 对未变内容不再 enqueue →
全文检索 / 图谱永久残缺,无人重推(embedding 有自己的 reconcile 兜底,Meili/Falkor 没有)。

本脚本把指定 topic 已 succeeded 的 outbox 行重置回 pending,worker 下个 cycle 会把现存资源
重新推回引擎(processor 读当前资源行,幂等)。

用法(在 langgraph 容器内执行,默认重推 meili + falkor):
    docker compose exec -T langgraph python scripts/requeue_engine_index.py
    # 只重推某一引擎 / 某租户:
    docker compose exec -T langgraph python scripts/requeue_engine_index.py --topics meili_index --tenant default
"""
from __future__ import annotations

import argparse
import sys

from data_foundation.db import connect
from data_foundation.outbox_repository import OutboxRepository

_DEFAULT_TOPICS = ["meili_index", "graph_ingest"]


def main() -> int:
    parser = argparse.ArgumentParser(description="引擎数据丢失后重推检索/图谱索引")
    parser.add_argument(
        "--topics", nargs="+", default=_DEFAULT_TOPICS,
        help=f"要重推的 outbox topic(默认 {_DEFAULT_TOPICS});embedding_generate 走自己的 reconcile,勿放这里",
    )
    parser.add_argument("--tenant", default=None, help="只重推某租户;省略则全租户")
    args = parser.parse_args()

    conn = connect()
    try:
        repo = OutboxRepository(conn)
        n = repo.requeue_succeeded(topics=args.topics, tenant_id=args.tenant)
    finally:
        conn.close()

    scope = f"tenant={args.tenant}" if args.tenant else "all tenants"
    print(f"Requeued {n} succeeded outbox rows (topics={args.topics}, {scope}). "
          f"Worker 将于下个 cycle 重推。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
