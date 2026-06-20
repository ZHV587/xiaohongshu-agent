from __future__ import annotations

from dataclasses import replace

from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.outbox_worker import process_outbox_batch


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
    def __init__(self, rows):
        self.rows = rows
        self.leases = []
        self.completed = []
        self.failed = []
        self.blocked = []

    def lease_ready(self, *, tenant_id, topics, lease_owner, batch_size, lease_seconds):
        self.leases.append({
            "tenant_id": tenant_id,
            "topics": topics,
            "lease_owner": lease_owner,
            "batch_size": batch_size,
            "lease_seconds": lease_seconds,
        })
        return self.rows[:batch_size]

    def complete(self, **kwargs):
        self.completed.append(kwargs)
        return True

    def fail(self, **kwargs):
        self.failed.append(kwargs)
        return True

    def block_item(self, **kwargs):
        self.blocked.append(kwargs)
        return True


class DisabledRegistry:
    topics = ["meili_index"]

    def state_for(self, topic):
        return ProcessorState(topic=topic, status="disabled", config_version=None, reason_code="PROCESSOR_DISABLED")

    def processor_for(self, topic):
        return None


class SucceedingProcessor:
    async def process(self, item):
        return replace(item, status="succeeded")


class EnabledRegistry:
    topics = ["meili_index"]

    def state_for(self, topic):
        return ProcessorState(topic=topic, status="active", config_version="v1", reason_code=None)

    def processor_for(self, topic):
        return SucceedingProcessor()


def test_process_outbox_batch_returns_empty_stats_when_nothing_leased():
    repo = RecordingRepo([])

    result = process_outbox_batch(
        repo,
        tenant_id="default",
        registry=EnabledRegistry(),
        lease_owner="outbox-worker",
    )

    assert result == {"leased": 0, "processed": 0, "succeeded": 0, "failed": 0, "blocked": 0, "errors": []}
    assert repo.leases == [{
        "tenant_id": "default",
        "topics": ["meili_index"],
        "lease_owner": "outbox-worker",
        "batch_size": 20,
        "lease_seconds": 60,
    }]


def test_process_outbox_batch_blocks_disabled_processor_topic():
    repo = RecordingRepo([_item()])

    result = process_outbox_batch(
        repo,
        tenant_id="default",
        registry=DisabledRegistry(),
        lease_owner="outbox-worker",
    )

    assert result["blocked"] == 1
    assert repo.blocked == [{
        "item_id": "1",
        "tenant_id": "default",
        "lease_owner": "outbox-worker",
        "reason_code": "PROCESSOR_DISABLED",
    }]
    assert repo.completed == []


def test_process_outbox_batch_completes_processor_success():
    repo = RecordingRepo([_item()])

    result = process_outbox_batch(
        repo,
        tenant_id="default",
        registry=EnabledRegistry(),
        lease_owner="outbox-worker",
    )

    assert result["succeeded"] == 1
    assert repo.completed == [{
        "item_id": "1",
        "tenant_id": "default",
        "lease_owner": "outbox-worker",
        "status": "succeeded",
    }]
