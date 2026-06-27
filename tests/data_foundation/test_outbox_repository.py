from __future__ import annotations

from data_foundation.outbox_repository import OutboxRepository


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _RecordingConnection:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.row_factory = None

    def execute(self, query, params):
        self.calls.append((query, params))
        return _Rows(self.rows)


def test_ready_tenant_discovery_is_bounded_and_ordered_by_due_time():
    conn = _RecordingConnection([{"tenant_id": "alpha"}])

    assert OutboxRepository(conn).discover_ready_tenants(limit=101) == ["alpha"]
    query, params = conn.calls[0]
    assert "status in ('pending', 'retry')" in query
    assert "next_attempt_at <= now()" in query
    assert "order by min(next_attempt_at), tenant_id" in query
    assert params == (100,)


def test_enqueue_is_idempotent(migrated_conn):
    repo = OutboxRepository(migrated_conn)

    first = repo.enqueue(
        tenant_id="tenant-a",
        topic="embedding_generate",
        dedupe_key="same-work",
        payload={"resource_id": "r1"},
    )
    second = repo.enqueue(
        tenant_id="tenant-a",
        topic="embedding_generate",
        dedupe_key="same-work",
        payload={"resource_id": "r1"},
    )

    assert second.id == first.id
    assert migrated_conn.execute("select count(*) from resource_outbox").fetchone()["count"] == 1


def test_requeue_succeeded_resets_only_given_topics(migrated_conn):
    """C-1 恢复入口:引擎数据卷丢失后,把 meili/graph 已 succeeded 的行重置回 pending 重推,
    且不碰其他 topic(embedding 走自己的 reconcile)与非 succeeded 行。"""
    repo = OutboxRepository(migrated_conn)
    meili = repo.enqueue(tenant_id="t1", topic="meili_index", dedupe_key="m1", payload={})
    graph = repo.enqueue(tenant_id="t1", topic="graph_ingest", dedupe_key="g1", payload={})
    emb = repo.enqueue(tenant_id="t1", topic="embedding_generate", dedupe_key="e1", payload={})
    pending_meili = repo.enqueue(tenant_id="t1", topic="meili_index", dedupe_key="m2", payload={})
    # 把前三个标 succeeded,第四个保持 pending
    for item in (meili, graph, emb):
        migrated_conn.execute(
            "update resource_outbox set status='succeeded' where id=%s", (item.id,)
        )

    n = repo.requeue_succeeded(topics=["meili_index", "graph_ingest"])

    assert n == 2  # 只重置 meili+graph 的 succeeded,不含 embedding
    def status(i):
        return migrated_conn.execute(
            "select status from resource_outbox where id=%s", (i,)
        ).fetchone()["status"]
    assert status(meili.id) == "pending"
    assert status(graph.id) == "pending"
    assert status(emb.id) == "succeeded"      # 其他 topic 不动
    assert status(pending_meili.id) == "pending"  # 本就 pending,不受影响


def test_same_dedupe_key_can_exist_in_different_tenants(migrated_conn):
    repo = OutboxRepository(migrated_conn)

    first = repo.enqueue(tenant_id="tenant-a", topic="embedding_generate", dedupe_key="same", payload={})
    second = repo.enqueue(tenant_id="tenant-b", topic="embedding_generate", dedupe_key="same", payload={})

    assert first.tenant_id == "tenant-a"
    assert second.tenant_id == "tenant-b"
    assert first.id != second.id


def test_ready_tenants_returns_due_pending_and_retry_once(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    repo.enqueue(tenant_id="alpha", topic="embedding_generate", dedupe_key="pending", payload={})
    retry = repo.enqueue(
        tenant_id="alpha", topic="embedding_generate", dedupe_key="retry", payload={}
    )
    future = repo.enqueue(
        tenant_id="future", topic="embedding_generate", dedupe_key="future", payload={}
    )
    processing = repo.enqueue(
        tenant_id="processing", topic="embedding_generate", dedupe_key="processing", payload={}
    )
    migrated_conn.execute(
        "update resource_outbox set status = 'retry', next_attempt_at = now() - interval '2 minutes' where id = %s",
        (retry.id,),
    )
    migrated_conn.execute(
        "update resource_outbox set next_attempt_at = now() + interval '1 hour' where id = %s",
        (future.id,),
    )
    migrated_conn.execute(
        "update resource_outbox set status = 'processing' where id = %s",
        (processing.id,),
    )
    migrated_conn.commit()

    assert repo.discover_ready_tenants(limit=10) == ["alpha"]


def test_lease_ready_claims_only_requested_tenant_and_topics(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    wanted = repo.enqueue(
        tenant_id="tenant-a",
        topic="embedding_generate",
        dedupe_key="wanted",
        payload={},
    )
    repo.enqueue(tenant_id="tenant-b", topic="embedding_generate", dedupe_key="other-tenant", payload={})
    repo.enqueue(tenant_id="tenant-a", topic="graph_ingest", dedupe_key="other-topic", payload={})

    leased = repo.lease_ready(
        tenant_id="tenant-a",
        topics=["embedding_generate"],
        lease_owner="worker-a",
        batch_size=10,
        lease_seconds=30,
    )

    assert [item.id for item in leased] == [wanted.id]
    assert leased[0].status == "processing"
    assert leased[0].lease_owner == "worker-a"
    assert leased[0].attempts == 1


def test_lost_or_expired_lease_cannot_complete(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    repo.enqueue(tenant_id="tenant-a", topic="embedding_generate", dedupe_key="lease", payload={})
    item = repo.lease_ready(
        tenant_id="tenant-a",
        topics=["embedding_generate"],
        lease_owner="worker-a",
        batch_size=1,
        lease_seconds=30,
    )[0]

    assert repo.complete(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-b",
        status="succeeded",
    ) is False
    migrated_conn.execute(
        "update resource_outbox set lease_expires_at = now() - interval '1 second' where id = %s",
        (item.id,),
    )
    assert repo.complete(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        status="succeeded",
    ) is False
    migrated_conn.execute(
        "update resource_outbox set lease_expires_at = now() + interval '30 seconds' where id = %s",
        (item.id,),
    )
    assert repo.complete(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        status="succeeded",
    ) is True


def test_fail_retries_then_dead_letters(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    repo.enqueue(tenant_id="tenant-a", topic="embedding_generate", dedupe_key="retry", payload={})
    item = repo.lease_ready(
        tenant_id="tenant-a",
        topics=["embedding_generate"],
        lease_owner="worker-a",
        batch_size=1,
        lease_seconds=30,
    )[0]

    assert repo.fail(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        error_code="EMBEDDING_TIMEOUT",
        error_summary="timed out",
        max_attempts=2,
    ) is True

    retry = migrated_conn.execute(
        "select status, error_code, error_summary from resource_outbox where id = %s",
        (item.id,),
    ).fetchone()
    assert retry == {"status": "retry", "error_code": "EMBEDDING_TIMEOUT", "error_summary": "timed out"}

    migrated_conn.execute(
        """
        update resource_outbox
        set status = 'processing',
            attempts = 2,
            lease_owner = 'worker-a',
            lease_expires_at = now() + interval '30 seconds'
        where id = %s
        """,
        (item.id,),
    )
    assert repo.fail(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        error_code="EMBEDDING_TIMEOUT",
        error_summary="timed out again",
        max_attempts=2,
    ) is True

    dead = migrated_conn.execute(
        "select status, dead_at is not null as has_dead_at from resource_outbox where id = %s",
        (item.id,),
    ).fetchone()
    assert dead == {"status": "dead", "has_dead_at": True}


def test_renew_extends_only_owned_lease(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    repo.enqueue(tenant_id="tenant-a", topic="embedding_generate", dedupe_key="renew", payload={})
    item = repo.lease_ready(
        tenant_id="tenant-a",
        topics=["embedding_generate"],
        lease_owner="worker-a",
        batch_size=1,
        lease_seconds=30,
    )[0]

    assert repo.renew(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-b",
        lease_seconds=30,
    ) is False
    assert repo.renew(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        lease_seconds=30,
    ) is True


def test_recover_expired_returns_processing_rows_to_retry(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    repo.enqueue(tenant_id="tenant-a", topic="embedding_generate", dedupe_key="expired", payload={})
    item = repo.lease_ready(
        tenant_id="tenant-a",
        topics=["embedding_generate"],
        lease_owner="worker-a",
        batch_size=1,
        lease_seconds=1,
    )[0]
    migrated_conn.execute(
        "update resource_outbox set lease_expires_at = now() - interval '1 second' where id = %s",
        (item.id,),
    )

    assert repo.recover_expired(limit=10) == 1
    row = migrated_conn.execute(
        "select status, lease_owner from resource_outbox where id = %s",
        (item.id,),
    ).fetchone()
    assert row == {"status": "retry", "lease_owner": None}


def test_block_leased_item_requires_owner_and_unblock_is_tenant_scoped(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    repo.enqueue(tenant_id="tenant-a", topic="embedding_generate", dedupe_key="block-a", payload={})
    repo.enqueue(tenant_id="tenant-b", topic="embedding_generate", dedupe_key="block-b", payload={})
    item = repo.lease_ready(
        tenant_id="tenant-a",
        topics=["embedding_generate"],
        lease_owner="worker-a",
        batch_size=1,
        lease_seconds=30,
    )[0]

    assert repo.block_item(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-b",
        reason_code="PROCESSOR_DISABLED",
    ) is False
    assert repo.block_item(
        item_id=item.id,
        tenant_id="tenant-a",
        lease_owner="worker-a",
        reason_code="PROCESSOR_DISABLED",
    ) is True
    blocked = migrated_conn.execute(
        "select status, error_code from resource_outbox where id = %s",
        (item.id,),
    ).fetchone()
    assert blocked == {"status": "blocked", "error_code": "PROCESSOR_DISABLED"}

    assert repo.unblock_available(tenant_id="tenant-a", topic="embedding_generate") == 1
    unblocked = migrated_conn.execute(
        "select status, error_code from resource_outbox where id = %s",
        (item.id,),
    ).fetchone()
    assert unblocked == {"status": "pending", "error_code": None}
    other_tenant = migrated_conn.execute(
        "select status from resource_outbox where tenant_id = 'tenant-b'"
    ).fetchone()
    assert other_tenant == {"status": "pending"}


def test_discover_blocked_tenants_filters_by_topic_and_status():
    conn = _RecordingConnection([{"tenant_id": "default"}])
    result = OutboxRepository(conn).discover_blocked_tenants(topics=["meili_index", "graph_ingest"], limit=10)
    assert result == ["default"]
    query, params = conn.calls[0]
    assert "status = 'blocked'" in query
    assert "topic = any(%s::text[])" in query
    assert params == (["meili_index", "graph_ingest"], 10)


def test_discover_blocked_tenants_empty_topics_returns_empty():
    conn = _RecordingConnection([{"tenant_id": "default"}])
    assert OutboxRepository(conn).discover_blocked_tenants(topics=[], limit=10) == []
    assert conn.calls == []
