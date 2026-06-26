"""线上笔记采纳核心(纯数据底座逻辑,不依赖 tools/ 层)。

采纳 = 写 Postgres 权威库(xhs_online_note,按 redfox note_id 幂等)+ 接效果指标
(performance_metric + measured_by 边)。飞书镜像同步由 tools 层在采纳成功后另行编排。
"""
from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from data_foundation.outbox_requests import default_write_requests
from data_foundation.performance_feedback import save_performance_metric_resource

REDFOX_SYSTEM = "redfox"
XHS_NOTE_EXTERNAL_TYPE = "xhs_note"
ONLINE_NOTE_TYPE = "xhs_online_note"

_METRIC_KEYS = ("likes", "collects", "comments", "shares")


def find_adopted_note_ids(repo: Any, *, tenant_id: str, note_ids: list[str]) -> set[str]:
    """返回 note_ids 中已被采纳入库(存在 redfox mapping)的子集。"""
    return repo.existing_mapping_external_ids(
        tenant_id=tenant_id,
        system=REDFOX_SYSTEM,
        external_type=XHS_NOTE_EXTERNAL_TYPE,
        external_ids=note_ids,
    )


def _clean_int(value: Any) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _metrics_from_note(note: dict[str, Any]) -> dict[str, int]:
    metrics = {key: _clean_int(note.get(key)) for key in _METRIC_KEYS}
    return {key: value for key, value in metrics.items() if value > 0}


def adopt_online_note_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    note: dict[str, Any],
) -> dict[str, Any]:
    """采纳单条线上笔记:upsert xhs_online_note(幂等)+ 接效果指标。

    Returns: {"ok", "resource_id", "note_id", "note_url"} 或 {"ok": False, "error", "note_id"}。
    """
    note_id = str(note.get("note_id") or "").strip()
    if not note_id:
        return {"ok": False, "error": "note_id is required", "note_id": ""}
    note_url = str(note.get("note_url") or "").strip()
    title = str(note.get("title") or "").strip() or note_id
    summary = str(note.get("summary") or "").strip()

    content_json = {**note, "note_id": note_id, "note_url": note_url}
    content_text = "\n".join(
        part for part in [title, summary, note_url] if part
    )

    with _unit_of_work(repo):
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type=ONLINE_NOTE_TYPE,
            title=title,
            summary=summary or title,
            content_text=content_text,
            content_json=content_json,
            visibility="team",
            owner_open_id=actor_open_id,
            mapping={
                "system": REDFOX_SYSTEM,
                "external_type": XHS_NOTE_EXTERNAL_TYPE,
                "external_id": note_id,
                "external_url": note_url or None,
            },
            outbox_requests=default_write_requests(),
        )
        metrics = _metrics_from_note(note)
        if metrics:
            save_performance_metric_resource(
                repo,
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                target_resource_id=str(resource.id),
                metrics=metrics,
                published_at=str(note.get("created_at") or "") or None,
                channel="xiaohongshu",
                note_url=note_url or None,
            )

    return {
        "ok": True,
        "resource_id": str(resource.id),
        "note_id": note_id,
        "note_url": note_url,
    }


def _unit_of_work(repo: Any):
    unit_of_work = getattr(repo, "unit_of_work", None)
    return unit_of_work() if callable(unit_of_work) else nullcontext()
