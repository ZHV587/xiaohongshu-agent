from __future__ import annotations

import pytest

from data_foundation.models import OutboxItem
from data_foundation.outbox_worker import process_outbox_batch, process_outbox_item
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult
from data_foundation.processors.registry import ProcessorRegistry


def _item(item_id: str = "1", topic: str = "meili_index") -> OutboxItem:
    return OutboxItem(
        id=item_id,
        tenant_id="default",
        resource_id="res1",
        resource_version=1,
        topic=topic,
        dedupe_key=f"key-{item_id}",
        payload={},
        status="processing",
        attempts=1,
        next_attempt_at=None,
        lease_owner="worker-a",
        lease_expires_at=None,
        error_code=None,
        error_summary=None,
        dead_at=None,
        created_at=None,
        updated_at=None,
    )


class RecordingRepo:
    def __init__(self, rows, *, renew_results: list[bool] | None = None):
        self.rows = rows
        self.renew_results = list(renew_results or [True])
        self.leases = []
        self.completed = []
        self.failed = []
        self.blocked = []
        self.renewed = []

    def lease_ready(self, *, tenant_id, topics, lease_owner, batch_size, lease_seconds):
        self.leases.append({
            "tenant_id": tenant_id,
            "topics": topics,
            "lease_owner": lease_owner,
            "batch_size": batch_size,
            "lease_seconds": lease_seconds,
        })
        return self.rows[:batch_size]

    def renew(self, **kwargs):
        self.renewed.append(kwargs)
        return self.renew_results.pop(0) if self.renew_results else True

    def complete(self, **kwargs):
        self.completed.append(kwargs)
        return True

    def fail(self, **kwargs):
        self.failed.append(kwargs)
        return True

    def block_item(self, **kwargs):
        self.blocked.append(kwargs)
        return True


class SucceedingProcessor:
    topic = "embedding_generate"

    def __init__(self):
        self.guards = []

    def state(self):
        return None

    async def process(self, item, lease: LeaseGuard):
        await lease.assert_owned()
        self.guards.append(lease)
        return ProcessResult(status="succeeded", processed_count=1)


class FailingProcessor:
    topic = "embedding_generate"

    def state(self):
        return None

    async def process(self, item, lease: LeaseGuard):
        await lease.assert_owned()
        raise ValueError("bad processor")


class PermanentlyFailingProcessor:
    topic = "embedding_generate"

    def state(self):
        return None

    async def process(self, item, lease: LeaseGuard):
        await lease.assert_owned()
        raise PermanentProcessingError("bad config")


@pytest.mark.asyncio
async def test_unregistered_topic_is_blocked():
    repo = RecordingRepo([_item(topic="meili_index")])
    registry = ProcessorRegistry()

    result = await process_outbox_item(
        _item(topic="meili_index"),
        repo=repo,
        registry=registry,
        tenant_id="default",
        lease_owner="worker-a",
        lease_seconds=60,
    )

    assert result.status == "blocked"
    assert result.error_code == "PROCESSOR_DISABLED"
    assert repo.blocked == [{
        "item_id": "1",
        "tenant_id": "default",
        "lease_owner": "worker-a",
        "reason_code": "PROCESSOR_DISABLED",
    }]


@pytest.mark.asyncio
async def test_processor_result_controls_terminal_state():
    repo = RecordingRepo([_item(topic="embedding_generate")])
    processor = SucceedingProcessor()
    registry = ProcessorRegistry({"embedding_generate": processor})

    result = await process_outbox_item(
        _item(topic="embedding_generate"),
        repo=repo,
        registry=registry,
        tenant_id="default",
        lease_owner="worker-a",
        lease_seconds=60,
    )

    assert result.status == "succeeded"
    assert repo.completed == [{
        "item_id": "1",
        "tenant_id": "default",
        "lease_owner": "worker-a",
        "status": "succeeded",
    }]
    assert repo.renewed == [{
        "item_id": "1",
        "tenant_id": "default",
        "lease_owner": "worker-a",
        "lease_seconds": 60,
    }]


@pytest.mark.asyncio
async def test_lost_lease_prevents_terminal_success():
    repo = RecordingRepo([_item(topic="embedding_generate")], renew_results=[False])
    registry = ProcessorRegistry({"embedding_generate": SucceedingProcessor()})

    result = await process_outbox_item(
        _item(topic="embedding_generate"),
        repo=repo,
        registry=registry,
        tenant_id="default",
        lease_owner="worker-a",
        lease_seconds=60,
    )

    assert result.status == "failed"
    assert result.error_code == "LEASE_LOST"
    assert repo.completed == []
    assert repo.failed == [{
        "item_id": "1",
        "tenant_id": "default",
        "lease_owner": "worker-a",
        "error_code": "LEASE_LOST",
        "error_summary": "RuntimeError: LEASE_LOST",
    }]


@pytest.mark.asyncio
async def test_permanent_processor_error_blocks_item():
    repo = RecordingRepo([_item(topic="embedding_generate")])
    registry = ProcessorRegistry({"embedding_generate": PermanentlyFailingProcessor()})

    result = await process_outbox_item(
        _item(topic="embedding_generate"),
        repo=repo,
        registry=registry,
        tenant_id="default",
        lease_owner="worker-a",
        lease_seconds=60,
    )

    assert result.status == "blocked"
    assert result.error_code == "PermanentProcessingError"
    assert repo.failed == []
    assert repo.blocked == [{
        "item_id": "1",
        "tenant_id": "default",
        "lease_owner": "worker-a",
        "reason_code": "PermanentProcessingError",
    }]


@pytest.mark.asyncio
async def test_process_outbox_batch_uses_registry_topics_and_continues_after_error():
    rows = [_item("1", "embedding_generate"), _item("2", "missing")]
    repo = RecordingRepo(rows)
    registry = ProcessorRegistry({"embedding_generate": FailingProcessor()})

    result = await process_outbox_batch(
        repo,
        tenant_id="default",
        registry=registry,
        lease_owner="worker-a",
        batch_size=10,
        lease_seconds=60,
    )

    assert repo.leases == [{
        "tenant_id": "default",
        "topics": ["embedding_generate", "graph_ingest", "meili_index"],
        "lease_owner": "worker-a",
        "batch_size": 10,
        "lease_seconds": 60,
    }]
    assert result["leased"] == 2
    assert result["processed"] == 2
    assert result["failed"] == 1
    assert result["blocked"] == 1
    assert repo.blocked == [{
        "item_id": "2",
        "tenant_id": "default",
        "lease_owner": "worker-a",
        "reason_code": "PROCESSOR_DISABLED",
    }]
