from __future__ import annotations

from typing import Any

from data_foundation.feishu_sync import sync_base_rows, sync_wiki_documents


def sync_feishu_sources(
    repo,
    *,
    tenant_id: str,
    actor_open_id: str,
    triggered_by: str,
    base_rows: list[dict[str, Any]] | None = None,
    wiki_documents: list[dict[str, Any]] | None = None,
    source_errors: list[str] | None = None,
    app_token: str = "",
    table_id: str = "",
    wiki_space_id: str = "",
) -> dict[str, Any]:
    base_rows = base_rows or []
    wiki_documents = wiki_documents or []
    run_id = repo.start_sync_run(
        tenant_id=tenant_id,
        source="feishu",
        triggered_by=triggered_by,
        actor_open_id=actor_open_id,
        metadata={
            "base_rows": len(base_rows),
            "wiki_documents": len(wiki_documents),
        },
    )

    created = 0
    errors: list[str] = list(source_errors or [])
    try:
        base_result = sync_base_rows(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            app_token=app_token or "configured-base",
            table_id=table_id or "configured-table",
            rows=base_rows,
        )
        created += base_result.imported
        errors.extend(base_result.errors)

        wiki_result = sync_wiki_documents(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            space_id=wiki_space_id or "configured-space",
            documents=wiki_documents,
        )
        created += wiki_result.imported
        errors.extend(wiki_result.errors)

        status = _status_for_result(created=created, errors=errors)
        return _finish(
            repo,
            tenant_id=tenant_id,
            run_id=run_id,
            status=status,
            created=created,
            errors=errors,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return _finish(
            repo,
            tenant_id=tenant_id,
            run_id=run_id,
            status="failed",
            created=created,
            errors=[*errors, message],
        )


def _status_for_result(*, created: int, errors: list[str]) -> str:
    if not errors:
        return "success"
    if created > 0:
        return "partial_success"
    return "failed"


def _finish(
    repo,
    *,
    tenant_id: str,
    run_id: str,
    status: str,
    created: int,
    errors: list[str],
) -> dict[str, Any]:
    failed = len(errors)
    repo.finish_sync_run(
        tenant_id=tenant_id,
        run_id=run_id,
        status=status,
        created_count=created,
        updated_count=0,
        skipped_count=0,
        failed_count=failed,
        error="\n".join(errors) if errors else None,
    )
    return {
        "ok": status == "success",
        "run_id": run_id,
        "status": status,
        "created": created,
        "updated": 0,
        "skipped": 0,
        "failed": failed,
        "errors": errors,
    }
