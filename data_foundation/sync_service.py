from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import os
from typing import Any

from data_foundation.models import SourceSecrets
from data_foundation.sources.base import SourceContext
from data_foundation.sources.feishu import FeishuBaseSourceProcessor, FeishuWikiSourceProcessor
from data_foundation.knowledge.source_qualification import (
    default_base_source_config,
    default_wiki_source_config,
)


def _run_coro(coro):
    """在同步上下文运行协程,且对"已处于运行中的事件循环线程"健壮。

    sync_feishu_sources 是同步函数,经同步 @tool 触发。LangChain 在 async 执行路径下会把
    同步工具卸到线程池(线程内无 running loop),此时直接 asyncio.run —— 这是生产主路径,
    行为与改前完全一致。但为不依赖"总会被卸到线程"这一外部假设(本地/未来某些同步执行
    路径可能在事件循环线程直接调用),检测到当前线程已有 running loop 时改到独立线程跑独立
    事件循环,避免 asyncio.run "cannot be called from a running event loop" 直接崩工具。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # 无 running loop:生产主路径,行为不变
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(coro)).result()


class _ManualLease:
    async def assert_owned(self) -> None:
        return None


def _feishu_sync_interval_seconds() -> int:
    raw = os.environ.get("XHS_FEISHU_SYNC_INTERVAL_SECONDS", "86400").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 86400
    # 防误配成高频全量拉取；生产默认每天一次，测试/人工可最低 5 分钟。
    return min(max(value, 300), 31 * 86400)


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
    schedule_seconds = _feishu_sync_interval_seconds()
    base_source = source_repo.register_source(
        tenant_id=tenant_id,
        source_type="feishu_base",
        name="feishu-base-daily",
        external_id=app_token or "configured-base",
        credentials={},
        config=default_base_source_config(app_token=app_token, table_id=table_id),
        schedule_seconds=schedule_seconds,
        enabled=True,
    )
    wiki_source = source_repo.register_source(
        tenant_id=tenant_id,
        source_type="feishu_wiki",
        name="feishu-wiki-daily",
        external_id=wiki_space_id or "configured-space",
        credentials={},
        config=default_wiki_source_config(wiki_space_id=wiki_space_id),
        schedule_seconds=schedule_seconds,
        enabled=True,
    )
    run_id = source_repo.start_run(
        base_source.id,
        tenant_id=tenant_id,
        instance_id=None,
        execution_id=None,
    )

    created = 0
    updated = 0
    skipped = 0
    read = 0
    cursor: dict[str, Any] = {}
    errors: list[str] = list(source_errors or [])
    try:
        base_result = _run_coro(
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

        wiki_result = _run_coro(
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
            schedule_seconds=schedule_seconds,
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
            schedule_seconds=schedule_seconds,
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
    schedule_seconds: int,
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
        next_run_after_seconds=schedule_seconds,
    )
    source_repo.finish_source(
        wiki_source_id,
        tenant_id=tenant_id,
        lease_owner=None,
        cursor=cursor.get("feishu_wiki", {}),
        next_run_after_seconds=schedule_seconds,
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
