from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from langchain_core.runnables import RunnableConfig

from tools.feishu_bitable import read_xhs_data
from tools.feishu_wiki import read_feishu_wiki


def load_feishu_sources(config: RunnableConfig | None = None) -> dict[str, Any]:
    base_payload = _read_source("base", read_xhs_data, config)
    wiki_payload = _read_source("wiki", read_feishu_wiki, config)

    errors = list(base_payload.get("source_errors", []))
    base_rows = []
    for row in base_payload.get("sync_rows", []):
        if isinstance(row, dict) and row.get("record_id") and isinstance(row.get("fields"), dict):
            base_rows.append(_normalize_external_time(row, errors, f"base row {row['record_id']}"))
        else:
            errors.append("base row missing record_id or fields")

    errors.extend(wiki_payload.get("source_errors", []))
    wiki_documents = []
    for document in wiki_payload.get("documents", []):
        if isinstance(document, dict) and document.get("obj_token") and document.get("node_token"):
            wiki_documents.append(
                _normalize_external_time(document, errors, f"wiki document {document['obj_token']}")
            )
        else:
            errors.append("wiki document missing obj_token or node_token")

    return {
        "base_rows": base_rows,
        "wiki_documents": wiki_documents,
        "source_errors": errors,
        "app_token": str(base_payload.get("app_token") or ""),
        "table_id": str(base_payload.get("table_id") or ""),
        "wiki_space_id": str(wiki_payload.get("wiki_space_id") or ""),
    }


def _read_source(name: str, source_tool: Any, config: RunnableConfig | None) -> dict[str, Any]:
    try:
        payload = source_tool.func(config=config)
    except Exception as exc:
        return {"source_errors": [f"{name}: {type(exc).__name__}: {exc}"]}
    if not isinstance(payload, dict):
        return {"source_errors": [f"{name}: invalid response"]}
    if payload.get("error"):
        payload = {**payload, "source_errors": [f"{name}: {payload['error']}", *payload.get("source_errors", [])]}
    return payload


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
