from __future__ import annotations


def classification_lock_key(*, tenant_id: str, resource_id: str) -> str:
    """Return the transaction-lock identity for one mutable classification subject."""
    tenant = tenant_id.strip() if isinstance(tenant_id, str) else ""
    resource = resource_id.strip() if isinstance(resource_id, str) else ""
    if not tenant or not resource:
        raise ValueError("tenant_id and resource_id are required for knowledge classification lock")
    return f"knowledge-classification:{tenant}:{resource}"


def acquire_classification_lock(
    executor,
    *,
    tenant_id: str,
    resource_id: str,
) -> None:
    """Serialize facts and decisions that classify the same stable resource."""
    executor.execute(
        "select pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (classification_lock_key(tenant_id=tenant_id, resource_id=resource_id),),
    )


__all__ = ["acquire_classification_lock", "classification_lock_key"]
