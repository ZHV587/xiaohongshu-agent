from __future__ import annotations

from data_foundation.outbox_repository import OutboxRepository


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


def test_same_dedupe_key_can_exist_in_different_tenants(migrated_conn):
    repo = OutboxRepository(migrated_conn)

    first = repo.enqueue(tenant_id="tenant-a", topic="embedding_generate", dedupe_key="same", payload={})
    second = repo.enqueue(tenant_id="tenant-b", topic="embedding_generate", dedupe_key="same", payload={})

    assert first.tenant_id == "tenant-a"
    assert second.tenant_id == "tenant-b"
    assert first.id != second.id


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
