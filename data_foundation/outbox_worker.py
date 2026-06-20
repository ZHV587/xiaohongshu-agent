from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4


def process_outbox_batch(
    repo,
    tenant_id: str,
    *,
    registry,
    batch_size: int = 20,
    lease_owner: str | None = None,
    lease_seconds: int = 60,
) -> dict[str, Any]:
    lease_owner = lease_owner or f"outbox-worker:{uuid4()}"
    topics = list(registry.topics)
    leased = repo.lease_ready(
        tenant_id=tenant_id,
        topics=topics,
        lease_owner=lease_owner,
        batch_size=batch_size,
        lease_seconds=lease_seconds,
    )
    stats: dict[str, Any] = {
        "leased": len(leased),
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "blocked": 0,
        "errors": [],
    }

    for item in leased:
        state = registry.state_for(item.topic)
        processor = registry.processor_for(item.topic)
        if state.status != "active" or state.reason_code or processor is None:
            reason_code = state.reason_code or "PROCESSOR_DISABLED"
            repo.block_item(
                item_id=item.id,
                tenant_id=tenant_id,
                lease_owner=lease_owner,
                reason_code=reason_code,
            )
            stats["processed"] += 1
            stats["blocked"] += 1
            continue

        try:
            result = processor.process(item)
            if hasattr(result, "__await__"):
                result = asyncio.run(result)
            repo.complete(
                item_id=item.id,
                tenant_id=tenant_id,
                lease_owner=lease_owner,
                status=result.status,
            )
            stats["processed"] += 1
            stats["succeeded"] += 1
        except Exception as exc:
            error_summary = f"{type(exc).__name__}: {exc}"
            repo.fail(
                item_id=item.id,
                tenant_id=tenant_id,
                lease_owner=lease_owner,
                error_code=type(exc).__name__,
                error_summary=error_summary,
            )
            stats["processed"] += 1
            stats["failed"] += 1
            stats["errors"].append({"id": item.id, "topic": item.topic, "error": error_summary})

    return stats
