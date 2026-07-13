from __future__ import annotations

import json
from typing import Any

from psycopg import Connection
from psycopg.pq import TransactionStatus

from data_foundation.db import transaction
from data_foundation.models import OutboxItem


class OutboxRepository:
    def __init__(self, conn: Connection):
        # 连接在 db.connect() 已统一为 dict_row(单一事实源);不在此改写共享连接的
        # row_factory,避免污染其它共用该连接的组件(见 processors/meili.py 注释)。
        self.conn = conn

    def _rollback_aborted_transaction(self) -> None:
        """Return a processor-poisoned shared connection to a writable state."""
        if self.conn.info.transaction_status == TransactionStatus.INERROR:
            self.conn.rollback()

    def enqueue(
        self,
        *,
        tenant_id: str,
        topic: str,
        dedupe_key: str,
        payload: dict[str, Any],
        resource_id: str | None = None,
        resource_version: int | None = None,
        event_id: str | None = None,
    ) -> OutboxItem:
        # on conflict:enqueue 是「幂等 ensure-exists」。同 dedupe_key = 同一份工作
        # (embedding 的 dedupe_key 含 version/index,内容变 → key 变 → 走 insert 分支)。
        #   - succeeded / pending / retry / processing:保持原状。succeeded 必须幂等——
        #     reconcile 每周期对全部资源循环 enqueue,若在此把 succeeded 重置回 pending 会导致
        #     每周期重跑全量索引;succeeded 的重推走专用运维入口 requeue_succeeded()。
        #   - blocked:有专用 unblock_available() 复活路径,这里不动。
        #   - dead / superseded:是「无其它复活路径」的终态。调用方再次 enqueue 同一份工作,
        #     即明确的「重来」信号 → 复位回 pending 并清空 lease/attempts/错误态,否则新 enqueue
        #     被静默吞掉、任务永远推不动。
        # 用 CASE 而非 `do update ... where`:后者条件不满足时 RETURNING 不返回行,enqueue 会拿到
        # None;CASE 保证任何冲突都仍返回该行,同时只对 dead/superseded 生效。
        row = self.conn.execute(
            """
            insert into resource_outbox (
              tenant_id, resource_id, resource_version, event_id, topic, dedupe_key, payload
            )
            values (%s, %s, %s, %s, %s, %s, %s::jsonb)
            on conflict(tenant_id, dedupe_key) do update set
              status = case when resource_outbox.status in ('dead', 'superseded')
                            then 'pending' else resource_outbox.status end,
              attempts = case when resource_outbox.status in ('dead', 'superseded')
                              then 0 else resource_outbox.attempts end,
              next_attempt_at = case when resource_outbox.status in ('dead', 'superseded')
                                     then now() else resource_outbox.next_attempt_at end,
              lease_owner = case when resource_outbox.status in ('dead', 'superseded')
                                 then null else resource_outbox.lease_owner end,
              lease_expires_at = case when resource_outbox.status in ('dead', 'superseded')
                                      then null else resource_outbox.lease_expires_at end,
              error_code = case when resource_outbox.status in ('dead', 'superseded')
                                then null else resource_outbox.error_code end,
              error_summary = case when resource_outbox.status in ('dead', 'superseded')
                                   then null else resource_outbox.error_summary end,
              dead_at = case when resource_outbox.status in ('dead', 'superseded')
                             then null else resource_outbox.dead_at end,
              updated_at = now()
            returning *
            """,
            (
                tenant_id,
                resource_id,
                resource_version,
                event_id,
                topic,
                dedupe_key,
                json.dumps(payload, sort_keys=True, ensure_ascii=False),
            ),
        ).fetchone()
        self.conn.commit()
        return self._item_from_row(row)

    def requeue_succeeded(self, *, topics: list[str], tenant_id: str | None = None) -> int:
        """把指定 topic 已 succeeded 的 outbox 行重置回 pending,供引擎数据卷丢失后重推。

        为什么需要:Meili/Falkor 写是"PG 标 succeeded + 引擎入库"两段,引擎数据卷丢失重建后
        引擎里空了,但 outbox 早已 succeeded、upsert_resource 对未变内容也不再 enqueue →
        检索/图谱永久残缺无人重推。本方法是运维恢复入口:重置 succeeded→pending,worker 重新
        把现存资源推回引擎(processor 读的是当前资源行,幂等)。tenant_id 为 None 表示全租户。
        """
        if not topics:
            return 0
        params: list[Any] = [topics]
        tenant_clause = ""
        if tenant_id is not None:
            tenant_clause = "and tenant_id = %s"
            params.append(tenant_id)
        rows = self.conn.execute(
            f"""
            update resource_outbox
            set status = 'pending',
                next_attempt_at = now(),
                attempts = 0,
                lease_owner = null,
                lease_expires_at = null,
                error_code = null,
                error_summary = null
            where status = 'succeeded'
              and topic = any(%s)
              {tenant_clause}
            returning id
            """,
            tuple(params),
        ).fetchall()
        self.conn.commit()
        return len(rows)

    def pending_counts_by_topic(self, *, topics: list[str]) -> dict[str, dict[str, int]]:
        """按 (topic, tenant) 统计在途(尚未 succeeded)的 outbox 任务数,供索引对账防误报。

        在途 = pending/retry/processing(blocked/dead/succeeded/superseded 不算在途):
        正常 backlog 会让引擎暂时少于 PG 应有数,把在途算进来才不会把它误判成数据丢失。
        """
        if not topics:
            return {}
        rows = self.conn.execute(
            """
            select topic, tenant_id, count(distinct resource_id) as n
            from resource_outbox
            where status in ('pending', 'retry', 'processing')
              and topic = any(%s::text[])
            group by topic, tenant_id
            """,
            (topics,),
        ).fetchall()
        out: dict[str, dict[str, int]] = {}
        for row in rows:
            out.setdefault(row["topic"], {})[row["tenant_id"]] = int(row["n"])
        return out

    def discover_ready_tenants(self, *, limit: int) -> list[str]:
        rows = self.conn.execute(
            """
            select tenant_id
            from resource_outbox
            where status in ('pending', 'retry')
              and next_attempt_at <= now()
            group by tenant_id
            order by min(next_attempt_at), tenant_id
            limit %s
            """,
            (max(1, min(limit, 100)),),
        ).fetchall()
        return [row["tenant_id"] for row in rows]

    def discover_blocked_tenants(self, *, topics: list[str], limit: int) -> list[str]:
        """发现存在 blocked 任务的租户(限定 topic)。

        blocked 任务靠 unblock_available 转回 pending,但只有被发现的租户才会触发 unblock。
        当某 processor 从 disabled 转为 active(如 meili/graph 引擎启用)时,需要这个发现源
        把历史 blocked 任务所在租户重新纳入调度,否则会死锁(blocked 永不被 unblock)。
        """
        if not topics:
            return []
        rows = self.conn.execute(
            """
            select tenant_id
            from resource_outbox
            where status = 'blocked'
              and topic = any(%s::text[])
            group by tenant_id
            order by tenant_id
            limit %s
            """,
            (topics, max(1, min(limit, 100))),
        ).fetchall()
        return [row["tenant_id"] for row in rows]

    def lease_ready(
        self,
        *,
        tenant_id: str,
        topics: list[str],
        lease_owner: str,
        batch_size: int,
        lease_seconds: int,
    ) -> list[OutboxItem]:
        if not topics:
            return []
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select id
                from resource_outbox
                where tenant_id = %s
                  and topic = any(%s::text[])
                  and status in ('pending', 'retry')
                  and next_attempt_at <= now()
                order by next_attempt_at, created_at, id
                limit %s
                for update skip locked
                """,
                (tenant_id, topics, batch_size),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return []
            leased = self.conn.execute(
                """
                update resource_outbox
                set status = 'processing',
                    attempts = attempts + 1,
                    lease_owner = %s,
                    lease_expires_at = now() + (%s || ' seconds')::interval,
                    updated_at = now()
                where id = any(%s::uuid[])
                returning *
                """,
                (lease_owner, lease_seconds, ids),
            ).fetchall()
        return [self._item_from_row(row) for row in leased]

    def renew(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        lease_seconds: int,
    ) -> bool:
        cursor = self.conn.execute(
            """
            update resource_outbox
            set lease_expires_at = now() + (%s || ' seconds')::interval,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (lease_seconds, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def complete(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        status: str,
    ) -> bool:
        if status not in {"succeeded", "superseded"}:
            raise ValueError("Outbox completion status must be succeeded or superseded")
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = %s,
                lease_owner = null,
                lease_expires_at = null,
                error_code = null,
                error_summary = null,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (status, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def fail(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        error_code: str,
        error_summary: str,
        max_attempts: int = 8,
    ) -> bool:
        # A processor can fail because one of its SQL statements failed. Psycopg then
        # leaves the shared scheduler connection in INERROR until an explicit
        # rollback; trying to persist the retry state on that connection would fail
        # too and permanently degrade every later scheduler cycle. Preserve a valid
        # caller transaction, but reset a processor-poisoned one before recording the
        # durable retry/dead state.
        self._rollback_aborted_transaction()
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = case when attempts >= %s then 'dead' else 'retry' end,
                next_attempt_at = now() + (least(attempts * attempts, 300) || ' seconds')::interval,
                lease_owner = null,
                lease_expires_at = null,
                error_code = %s,
                error_summary = left(%s, 1000),
                dead_at = case when attempts >= %s then now() else dead_at end,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (max_attempts, error_code, error_summary, max_attempts, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def recover_expired(self, *, limit: int) -> int:
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select id
                from resource_outbox
                where status = 'processing'
                  and lease_expires_at < now()
                order by lease_expires_at, id
                limit %s
                for update skip locked
                """,
                (limit,),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return 0
            cursor = self.conn.execute(
                """
                update resource_outbox
                set status = 'retry',
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                where id = any(%s::uuid[])
                """,
                (ids,),
            )
        return cursor.rowcount

    def block_item(
        self,
        *,
        item_id: str,
        tenant_id: str,
        lease_owner: str,
        reason_code: str,
    ) -> bool:
        # Keep the permanent-failure path usable after a processor-side SQL error for
        # the same reason as fail(): terminal-state persistence needs a clean
        # transaction boundary.
        self._rollback_aborted_transaction()
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = 'blocked',
                error_code = %s,
                error_summary = %s,
                lease_owner = null,
                lease_expires_at = null,
                updated_at = now()
            where id = %s
              and tenant_id = %s
              and status = 'processing'
              and lease_owner = %s
              and lease_expires_at > now()
            """,
            (reason_code, reason_code, item_id, tenant_id, lease_owner),
        )
        self.conn.commit()
        return cursor.rowcount == 1

    def unblock_available(self, *, tenant_id: str, topic: str) -> int:
        cursor = self.conn.execute(
            """
            update resource_outbox
            set status = 'pending',
                error_code = null,
                error_summary = null,
                next_attempt_at = now(),
                updated_at = now()
            where topic = %s
              and tenant_id = %s
              and status = 'blocked'
            """,
            (topic, tenant_id),
        )
        self.conn.commit()
        return cursor.rowcount

    @staticmethod
    def _item_from_row(row: Any) -> OutboxItem:
        return OutboxItem(
            id=str(row["id"]),
            tenant_id=row["tenant_id"],
            resource_id=None if row["resource_id"] is None else str(row["resource_id"]),
            resource_version=row["resource_version"],
            topic=row["topic"],
            dedupe_key=row["dedupe_key"],
            payload=dict(row["payload"]),
            status=row["status"],
            attempts=row["attempts"],
            next_attempt_at=row["next_attempt_at"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            error_code=row["error_code"],
            error_summary=row["error_summary"],
            dead_at=row["dead_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
