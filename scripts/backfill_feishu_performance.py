"""存量回填:把现有 feishu_base_record 白名单表的效果列接通 performance_metric + measured_by。

feishu-performance-metrics spec 的 b(先行)入口。与 sync_base_rows 共用同一抽取纯函数
(extract_performance_metrics)与同一幂等写入(save_performance_metric_resource),单一事实源。

用法:
    uv run python scripts/backfill_feishu_performance.py --dry-run   # 只统计命中,不写
    uv run python scripts/backfill_feishu_performance.py             # 实际幂等写入

幂等:重跑不产生重复 metric/边(按 target 复用既有 metric)。单条失败计入 errors 不中断。
"""
from __future__ import annotations

import argparse
import sys

from data_foundation.db import connect
from data_foundation.feishu_metrics import extract_performance_metrics
from data_foundation.performance_feedback import save_performance_metric_resource
from data_foundation.permissions import default_tenant_id
from data_foundation.repositories.resource import ResourceRepository


def _iter_feishu_base_records(conn, tenant_id: str, batch: int = 500):
    """分页读 feishu_base_record(id/owner_open_id/content_json),按 id 游标。"""
    last_id = None
    while True:
        if last_id is None:
            rows = conn.execute(
                """
                select id::text as id, owner_open_id, content_json
                from resources
                where tenant_id = %s and type = 'feishu_base_record'
                order by id limit %s
                """,
                (tenant_id, batch),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                select id::text as id, owner_open_id, content_json
                from resources
                where tenant_id = %s and type = 'feishu_base_record' and id > %s
                order by id limit %s
                """,
                (tenant_id, last_id, batch),
            ).fetchall()
        if not rows:
            return
        for row in rows:
            yield row
        last_id = rows[-1]["id"]


def backfill(*, dry_run: bool) -> dict[str, int]:
    tenant_id = default_tenant_id()
    stats = {"scanned": 0, "whitelisted": 0, "written": 0, "skipped_no_metric": 0, "errors": 0}
    conn = connect()
    # autocommit:读迭代器的 SELECT 不滞留顶层事务,否则每条写入的 transaction() 只是
    # savepoint、顶层事务永不提交 → conn.close() 时回滚(written 报告非零但库内为 0)。
    conn.autocommit = True
    try:
        repo = ResourceRepository(conn)
        for row in _iter_feishu_base_records(conn, tenant_id):
            stats["scanned"] += 1
            cj = dict(row["content_json"] or {})
            table_id = str(cj.get("table_id") or "")
            table_name = str(cj.get("table_name") or "")
            fields = dict(cj.get("fields") or {})
            metrics = extract_performance_metrics(table_id, table_name, fields)
            if not metrics:
                stats["skipped_no_metric"] += 1
                continue
            stats["whitelisted"] += 1
            if dry_run:
                continue
            try:
                save_performance_metric_resource(
                    repo,
                    tenant_id=tenant_id,
                    actor_open_id=row["owner_open_id"],
                    target_resource_id=row["id"],
                    metrics=metrics,
                    channel="xiaohongshu",
                )
                stats["written"] += 1
            except Exception as exc:  # noqa: BLE001 - 单条失败不中断
                stats["errors"] += 1
                print(f"[error] {row['id']}: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        conn.close()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="回填飞书效果指标")
    parser.add_argument("--dry-run", action="store_true", help="只统计命中,不写入")
    args = parser.parse_args()
    stats = backfill(dry_run=args.dry_run)
    mode = "DRY-RUN" if args.dry_run else "WRITE"
    print(
        f"[{mode}] scanned={stats['scanned']} whitelisted={stats['whitelisted']} "
        f"written={stats['written']} skipped_no_metric={stats['skipped_no_metric']} "
        f"errors={stats['errors']}"
    )
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
