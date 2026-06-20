from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from data_foundation.models import SourceSecrets, SyncSource
from data_foundation.sources.base import SourceContext
from data_foundation.sources.feishu import FeishuBaseSourceProcessor, FeishuWikiSourceProcessor


class _ManualLease:
    async def assert_owned(self) -> None:
        return None


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
    preloaded_base_rows = base_rows
    preloaded_wiki_documents = wiki_documents
    base_rows = base_rows or []
    wiki_documents = wiki_documents or []
    run_id = repo.start_sync_run(
        tenant_id=tenant_id,
        source_type="feishu_base",
        actor_open_id=actor_open_id,
        read_count=len(base_rows) + len(wiki_documents),
    )

    created = 0
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
                _manual_context(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    source_type="feishu_base",
                    name=f"{triggered_by}-feishu-base",
                    config={"app_token": app_token or "configured-base", "table_id": table_id or "configured-table"},
                ),
                _ManualLease(),
            )
        )
        created += base_result.created_count
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
                _manual_context(
                    tenant_id=tenant_id,
                    actor_open_id=actor_open_id,
                    source_type="feishu_wiki",
                    name=f"{triggered_by}-feishu-wiki",
                    config={"wiki_space_id": wiki_space_id or "configured-space"},
                ),
                _ManualLease(),
            )
        )
        created += wiki_result.created_count
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
        return "succeeded"
    if created > 0:
        return "partial"
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
        error_summary="\n".join(errors) if errors else None,
    )
    return {
        "ok": status == "succeeded",
        "run_id": run_id,
        "status": status,
        "created": created,
        "updated": 0,
        "skipped": 0,
        "failed": failed,
        "errors": errors,
    }


def _manual_context(
    *,
    tenant_id: str,
    actor_open_id: str,
    source_type: str,
    name: str,
    config: dict[str, Any],
) -> SourceContext:
    now = datetime.now(timezone.utc)
    return SourceContext(
        source=SyncSource(
            id=f"manual:{source_type}",
            tenant_id=tenant_id,
            source_type=source_type,
            name=name,
            external_id=None,
            config=config,
            enabled=True,
            schedule_seconds=0,
            next_run_at=now,
            last_dispatched_at=now,
            lease_owner=None,
            lease_expires_at=None,
            cursor={},
            created_at=now,
            updated_at=now,
        ),
        secrets=SourceSecrets(credentials={}),
        actor_open_id=actor_open_id,
    )
