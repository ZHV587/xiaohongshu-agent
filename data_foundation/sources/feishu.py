from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from data_foundation.errors import classify_error
from data_foundation.feishu_sync import sync_base_rows, sync_wiki_documents
from data_foundation.sources.base import SourceContext, SourceLease, SourceSyncResult

Loader = Callable[[SourceContext], dict[str, Any]]


class FeishuBaseSourceProcessor:
    source_type = "feishu_base"

    def __init__(self, *, loader: Loader | None = None, resource_repo):
        self.loader = loader or _default_base_loader
        self.resource_repo = resource_repo

    async def sync(self, context: SourceContext, lease: SourceLease) -> SourceSyncResult:
        try:
            # loader 是同步阻塞调用(lark-cli 子进程 / 飞书 HTTP)。卸到线程,使外层
            # scheduler 的 asyncio.wait_for 超时能真正打断挂起的同步 IO(否则 await 不到它)。
            payload = await asyncio.to_thread(self.loader, context)
        except Exception as exc:
            return _failed_result(exc)

        errors = list(payload.get("source_errors", []))
        rows = _valid_base_rows(payload, errors)
        await lease.assert_owned()
        result = sync_base_rows(
            self.resource_repo,
            tenant_id=context.source.tenant_id,
            actor_open_id=context.actor_open_id,
            app_token=str(payload.get("app_token") or context.source.config.get("app_token") or ""),
            rows=rows,
        )
        errors.extend(result.errors)
        return _source_result(read_count=len(rows), created_count=result.imported, errors=errors)


class FeishuWikiSourceProcessor:
    source_type = "feishu_wiki"

    def __init__(self, *, loader: Loader | None = None, resource_repo):
        self.loader = loader or _default_wiki_loader
        self.resource_repo = resource_repo

    async def sync(self, context: SourceContext, lease: SourceLease) -> SourceSyncResult:
        try:
            payload = await asyncio.to_thread(self.loader, context)
        except Exception as exc:
            return _failed_result(exc)

        errors = list(payload.get("source_errors", []))
        documents = _valid_wiki_documents(payload, errors)
        await lease.assert_owned()
        result = sync_wiki_documents(
            self.resource_repo,
            tenant_id=context.source.tenant_id,
            actor_open_id=context.actor_open_id,
            space_id=str(payload.get("wiki_space_id") or context.source.config.get("wiki_space_id") or ""),
            documents=documents,
        )
        errors.extend(result.errors)
        return _source_result(read_count=len(documents), created_count=result.imported, errors=errors)


def _valid_base_rows(payload: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in payload.get("sync_rows", []):
        if isinstance(row, dict) and row.get("record_id") and isinstance(row.get("fields"), dict):
            rows.append(_normalize_external_time(row, errors, f"base row {row['record_id']}"))
        else:
            errors.append("base row missing record_id or fields")
    return rows


def _valid_wiki_documents(payload: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for document in payload.get("documents", []):
        if isinstance(document, dict) and document.get("obj_token") and document.get("node_token"):
            documents.append(
                _normalize_external_time(document, errors, f"wiki document {document['obj_token']}")
            )
        else:
            errors.append("wiki document missing obj_token or node_token")
    return documents


def _source_result(*, read_count: int, created_count: int, errors: list[str]) -> SourceSyncResult:
    if not errors:
        status = "succeeded"
    elif created_count > 0:
        status = "partial"
    else:
        status = "failed"
    return SourceSyncResult(
        status=status,
        read_count=read_count,
        created_count=created_count,
        updated_count=0,
        skipped_count=0,
        failed_count=len(errors),
        errors=errors,
        cursor={},
    )


def _failed_result(exc: Exception) -> SourceSyncResult:
    classification = classify_error(exc, component="feishu_source", operation="sync")
    return SourceSyncResult(
        status="failed",
        read_count=0,
        created_count=0,
        updated_count=0,
        skipped_count=0,
        failed_count=1,
        errors=[classification.error_summary],
        cursor={},
    )


def _default_base_loader(context: SourceContext) -> dict[str, Any]:
    from tools.feishu_bitable import read_xhs_data
    from tools.runtime_identity import identity_config

    # 用当前 actor 的身份(UAT)读多维表,而不是 config=None 退回无 token 的 bot。
    actor = getattr(context, "actor_open_id", "") or ""
    config = identity_config(actor) if actor else None
    return read_xhs_data.func(config=config)


def _default_wiki_loader(context: SourceContext) -> dict[str, Any]:
    from tools.feishu_wiki import read_feishu_wiki
    from tools.runtime_identity import identity_config

    actor = getattr(context, "actor_open_id", "") or ""
    config = identity_config(actor) if actor else None
    return read_feishu_wiki.func(config=config)


def _normalize_external_time(
    item: dict[str, Any],
    errors: list[str],
    label: str,
) -> dict[str, Any]:
    raw_value = item.get("external_updated_at")
    if raw_value is None or raw_value == "":
        return item

    normalized = _parse_external_time(raw_value)
    if normalized is None:
        cleaned = dict(item)
        cleaned.pop("external_updated_at", None)
        errors.append(f"{label} has invalid external_updated_at")
        return cleaned

    return {**item, "external_updated_at": normalized.isoformat()}


def _parse_external_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _datetime_from_epoch(float(value))

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return _datetime_from_epoch(float(stripped))
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    return None


def _datetime_from_epoch(value: float) -> datetime | None:
    seconds = value / 1000 if value > 10_000_000_000 else value
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
