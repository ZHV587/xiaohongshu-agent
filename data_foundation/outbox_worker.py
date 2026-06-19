from __future__ import annotations

from typing import Any


SUPPORTED_TOPICS = {"embedding_generate", "graph_ingest", "meili_index"}


def process_outbox_batch(repo, tenant_id: str, batch_size: int = 20) -> dict[str, Any]:
    leased = repo.lease_outbox(tenant_id=tenant_id, batch_size=batch_size)
    stats: dict[str, Any] = {
        "leased": len(leased),
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "errors": [],
    }

    for item in leased:
        try:
            _process_item(item)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            repo.complete_outbox(item["id"], status="failed", error=error)
            stats["processed"] += 1
            stats["failed"] += 1
            stats["errors"].append(
                {
                    "id": item["id"],
                    "topic": item.get("topic"),
                    "error": error,
                }
            )
            continue

        repo.complete_outbox(item["id"], status="succeeded")
        stats["processed"] += 1
        stats["succeeded"] += 1

    return stats


def _process_item(item: dict[str, Any]) -> None:
    topic = item["topic"]
    if topic not in SUPPORTED_TOPICS:
        raise ValueError(f"Unsupported outbox topic: {topic}")
