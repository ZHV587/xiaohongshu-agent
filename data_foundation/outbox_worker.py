from __future__ import annotations

from typing import Any
from uuid import uuid4

from data_foundation.models import OutboxItem
from data_foundation.processors.base import ItemProcessResult, LeaseGuard, PermanentProcessingError


async def process_outbox_item(
    item: OutboxItem,
    *,
    repo,
    registry,
    tenant_id: str,
    lease_owner: str,
    lease_seconds: int,
) -> ItemProcessResult:
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
        return ItemProcessResult(status="blocked", error_code=reason_code, error_summary=reason_code)

    lease = LeaseGuard(
        repo,
        item_id=item.id,
        tenant_id=tenant_id,
        lease_owner=lease_owner,
        lease_seconds=lease_seconds,
    )
    try:
        result = await processor.process(item, lease)
    except PermanentProcessingError as exc:
        error_code = type(exc).__name__
        repo.block_item(
            item_id=item.id,
            tenant_id=tenant_id,
            lease_owner=lease_owner,
            reason_code=error_code,
        )
        return ItemProcessResult(status="blocked", error_code=error_code, error_summary=str(exc))
    except Exception as exc:
        error_code = "LEASE_LOST" if str(exc) == "LEASE_LOST" else type(exc).__name__
        error_summary = f"{type(exc).__name__}: {exc}"
        repo.fail(
            item_id=item.id,
            tenant_id=tenant_id,
            lease_owner=lease_owner,
            error_code=error_code,
            error_summary=error_summary,
        )
        return ItemProcessResult(status="failed", error_code=error_code, error_summary=error_summary)

    repo.complete(
        item_id=item.id,
        tenant_id=tenant_id,
        lease_owner=lease_owner,
        status=result.status,
    )
    return ItemProcessResult(status=result.status)


async def process_outbox_batch(
    repo,
    tenant_id: str,
    *,
    registry,
    batch_size: int = 20,
    lease_owner: str | None = None,
    lease_seconds: int = 60,
) -> dict[str, Any]:
    lease_owner = lease_owner or f"outbox-worker:{uuid4()}"
    leased = repo.lease_ready(
        tenant_id=tenant_id,
        topics=list(registry.topics),
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
        result = await process_outbox_item(
            item,
            repo=repo,
            registry=registry,
            tenant_id=tenant_id,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
        )
        stats["processed"] += 1
        if result.status in {"succeeded", "superseded"}:
            stats["succeeded"] += 1
        elif result.status == "blocked":
            stats["blocked"] += 1
        else:
            stats["failed"] += 1
            stats["errors"].append({
                "id": item.id,
                "topic": item.topic,
                "error": result.error_summary,
            })

    return stats
