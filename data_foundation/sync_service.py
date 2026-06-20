from __future__ import annotations

import asyncio
from typing import Any

from data_foundation.models import SourceSecrets
from data_foundation.sources.base import SourceContext
from data_foundation.sources.feishu import FeishuBaseSourceProcessor, FeishuWikiSourceProcessor


class _ManualLease:
    async def assert_owned(self) -> None:
        return None


def sync_feishu_sources(
    repo,
    *,
    source_repo,
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
    preloaded_base_rows = base_rows
    preloaded_wiki_documents = wiki_documents
    base_rows = base_rows or []
    wiki_documents = wiki_documents or []
    base_source = source_repo.register_source(
        tenant_id=tenant_id,
        source_type="feishu_base",
        name=f"{triggered_by}-feishu-base",
        external_id=app_token or "configured-base",
        credentials={},
        config={"app_token": app_token or "configured-base", "table_id": table_id or "configured-table"},
        schedule_seconds=60,
        enabled=False,
    )
    wiki_source = source_repo.register_source(
        tenant_id=tenant_id,
        source_type="feishu_wiki",
        name=f"{triggered_by}-feishu-wiki",
        external_id=wiki_space_id or "configured-space",
        credentials={},
        config={"wiki_space_id": wiki_space_id or "configured-space"},
        schedule_seconds=60,
        enabled=False,
    )
    run_id = source_repo.start_run(
        base_source.id,
        tenant_id=tenant_id,
        instance_id=f"manual:{actor_open_id}",
        execution_id=None,
    )

    created = 0
    updated = 0
    skipped = 0
    read = 0
    cursor: dict[str, Any] = {}
    errors: list[str] = list(source_errors or [])
    try:
        base_result = asyncio.run(
            FeishuBaseSourceProcessor(
                loader=None
                if preloaded_base_rows is None
                else lambda _context: {
                    "app_token": app_token or "configured-base",
                    "table_id": table_id or "configured-table",
                    "sync_rows": base_rows,
                },
                resource_repo=repo,
            ).sync(
                SourceContext(
                    source=base_source,
                    secrets=SourceSecrets(credentials={}),
                    actor_open_id=actor_open_id,
                ),
                _ManualLease(),
            )
        )
        read += base_result.read_count
        created += base_result.created_count
        updated += base_result.updated_count
        skipped += base_result.skipped_count
        cursor["feishu_base"] = base_result.cursor
        errors.extend(base_result.errors)

        wiki_result = asyncio.run(
            FeishuWikiSourceProcessor(
                loader=None
                if preloaded_wiki_documents is None
                else lambda _context: {
                    "wiki_space_id": wiki_space_id or "configured-space",
                    "documents": wiki_documents,
                },
                resource_repo=repo,
            ).sync(
                SourceContext(
                    source=wiki_source,
                    secrets=SourceSecrets(credentials={}),
                    actor_open_id=actor_open_id,
                ),
                _ManualLease(),
            )
        )
        read += wiki_result.read_count
        created += wiki_result.created_count
        updated += wiki_result.updated_count
        skipped += wiki_result.skipped_count
        cursor["feishu_wiki"] = wiki_result.cursor
        errors.extend(wiki_result.errors)

        status = _status_for_result(created=created, errors=errors)
        return _finish(
            source_repo,
            tenant_id=tenant_id,
            run_id=run_id,
            base_source_id=base_source.id,
            wiki_source_id=wiki_source.id,
            status=status,
            cursor=cursor,
            read=read,
            created=created,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        return _finish(
            source_repo,
            tenant_id=tenant_id,
            run_id=run_id,
            base_source_id=base_source.id,
            wiki_source_id=wiki_source.id,
            status="failed",
            cursor=cursor,
            read=read,
            created=created,
            updated=updated,
            skipped=skipped,
            errors=[*errors, message],
        )


def _status_for_result(*, created: int, errors: list[str]) -> str:
    if not errors:
        return "succeeded"
    if created > 0:
        return "partial"
    return "failed"


def _finish(
    source_repo,
    *,
    tenant_id: str,
    run_id: str,
    base_source_id: str,
    wiki_source_id: str,
    status: str,
    cursor: dict[str, Any],
    read: int,
    created: int,
    updated: int,
    skipped: int,
    errors: list[str],
) -> dict[str, Any]:
    failed = len(errors)
    source_repo.finish_run(
        run_id,
        tenant_id=tenant_id,
        status=status,
        cursor_after=cursor,
        read_count=read,
        created_count=created,
        updated_count=updated,
        skipped_count=skipped,
        failed_count=failed,
        error_code=None,
        error_summary="\n".join(errors) if errors else None,
    )
    source_repo.finish_source(
        base_source_id,
        tenant_id=tenant_id,
        lease_owner=None,
        cursor=cursor.get("feishu_base", {}),
        next_run_after_seconds=60,
    )
    source_repo.finish_source(
        wiki_source_id,
        tenant_id=tenant_id,
        lease_owner=None,
        cursor=cursor.get("feishu_wiki", {}),
        next_run_after_seconds=60,
    )
    return {
        "ok": status == "succeeded",
        "run_id": run_id,
        "status": status,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
    }
