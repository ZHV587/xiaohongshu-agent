from __future__ import annotations

from contextlib import nullcontext
import math
from typing import Any

from data_foundation.metric_parse import weighted_engagement
from data_foundation.outbox_requests import default_write_requests

MEASURED_BY_EDGE = "measured_by"
ALLOWED_METRICS = {"likes", "collects", "comments", "shares", "views", "conversions"}


def save_performance_metric_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    target_resource_id: str,
    metrics: dict[str, Any],
    published_at: str | None = None,
    channel: str = "xiaohongshu",
    note_url: str | None = None,
    extra_content: dict[str, Any] | None = None,
    target_resource_version: int | None = None,
) -> dict[str, Any]:
    target_resource_id = target_resource_id.strip()
    if not target_resource_id:
        raise ValueError("target_resource_id is required")
    cleaned_metrics = _clean_metrics(metrics)
    score = _score(cleaned_metrics)
    channel = channel.strip() if isinstance(channel, str) and channel.strip() else "xiaohongshu"
    published_at = published_at.strip() if isinstance(published_at, str) and published_at.strip() else None
    note_url = note_url.strip() if isinstance(note_url, str) and note_url.strip() else None
    title_date = published_at[:10] if published_at else "未注明日期"
    title = f"{_channel_label(channel)}效果 {title_date}"
    content_json = {
        "target_resource_id": target_resource_id,
        "metrics": cleaned_metrics,
        "score": score,
        "published_at": published_at,
        "channel": channel,
        "note_url": note_url,
    }
    # 调用方可在同一事务内合并额外字段(如 stage / account / scheduled_*),避免落库后
    # 再开第二个事务回写——后者中途失败会留下半成品(score 已落、stage 缺失)。
    if extra_content:
        content_json.update({k: v for k, v in extra_content.items() if v is not None})
    with _unit_of_work(repo):
        target = repo.writable_resource_metadata(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=target_resource_id,
        )
        resolved_target_version = target_resource_version
        lifecycle = None
        if target.get("type") == "generated_copy":
            from data_foundation.repositories.generated_copy import GeneratedCopyRepository

            lifecycle = GeneratedCopyRepository(repo)
            resolved_target_version = lifecycle.attributable_version(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=target_resource_id,
                requested_version=target_resource_version,
            )
        elif resolved_target_version is None:
            resolved_target_version = target.get("version")
        if resolved_target_version is None:
            raise ValueError("target resource version is required")
        version_exists = getattr(repo, "resource_version_exists", None)
        if callable(version_exists) and not version_exists(
            tenant_id=tenant_id,
            resource_id=target_resource_id,
            resource_version=int(resolved_target_version),
        ):
            raise ValueError("target resource version does not exist")
        content_json["target_resource_version"] = int(resolved_target_version)
        # 幂等:同一 target 已有 performance_metric 则复用其 id 原地更新,不新建第二条。
        existing_id = repo.find_performance_metric_id(
            tenant_id=tenant_id,
            target_resource_id=target_resource_id,
        )
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=existing_id,
            resource_type="performance_metric",
            title=title,
            summary=_summary(score, cleaned_metrics),
            content_text=_content_text(title, score, cleaned_metrics, note_url),
            content_json=content_json,
            visibility=target["visibility"],
            owner_open_id=target["owner_open_id"],
            outbox_requests=default_write_requests(),
        )
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=target_resource_id,
            source_resource_version=int(resolved_target_version),
            target_resource_id=resource.id,
            target_resource_version=int(resource.version),
            edge_type=MEASURED_BY_EDGE,
            weight=score,
        )
        # Every immutable performance_metric version is one exact, retry-idempotent
        # preference fact.  Keep this inside the metric unit of work: if profile
        # observation/rebuild fails, metric + measured_by + lifecycle all roll back.
        from data_foundation.preference_learning import PreferenceLearningService

        PreferenceLearningService(repo).record_exact_event(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            event_type="metrics_backfilled",
            source_resource_id=target_resource_id,
            source_resource_version=int(resolved_target_version),
            source_event_id=f"performance_metric:{resource.id}:v{int(resource.version)}",
            event_payload={
                "metrics": cleaned_metrics,
                "score": score,
                "metric_resource_id": str(resource.id),
                "metric_resource_version": int(resource.version),
                "published_at": published_at,
                "channel": channel,
            },
        )
        if lifecycle is not None:
            lifecycle.mark_measured(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_id=target_resource_id,
            )
    return {
        "ok": True,
        "resource": {
            "resource_id": resource.id,
            "type": resource.type,
            "title": resource.title,
            "version": resource.version,
        },
        "score": score,
        "target_resource_version": int(resolved_target_version),
    }


def get_resource_performance_payload(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_id: str,
) -> dict[str, Any]:
    resource_id = resource_id.strip()
    if not resource_id:
        raise ValueError("resource_id is required")
    metrics = []
    for row in repo.performance_rows(
        tenant_id=tenant_id,
        actor_open_id=actor_open_id,
        resource_id=resource_id,
    ):
        content_json = dict(row["content_json"])
        updated_at = row.get("updated_at") if hasattr(row, "get") else None
        metrics.append({
            "resource_id": str(row["resource_id"]),
            "title": row["title"],
            "score": float(content_json.get("score", row.get("weight", 0.0))),
            "metrics": dict(content_json.get("metrics") or {}),
            "channel": content_json.get("channel"),
            "target_resource_version": content_json.get("target_resource_version"),
            "updated_at": updated_at.isoformat() if updated_at is not None else None,
        })
    return {"ok": True, "target_resource_id": resource_id, "metrics": metrics}


def _clean_metrics(metrics: dict[str, Any]) -> dict[str, float | int]:
    if not isinstance(metrics, dict):
        raise ValueError("metrics must be a mapping")
    cleaned: dict[str, float | int] = {}
    for key, value in metrics.items():
        if key not in ALLOWED_METRICS:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("metrics must be finite non-negative numbers") from exc
        if not math.isfinite(number):
            raise ValueError("metrics must be finite non-negative numbers")
        if number < 0:
            raise ValueError("metrics must be non-negative")
        cleaned[key] = int(number) if number.is_integer() else number
    if not cleaned:
        raise ValueError("metrics must contain at least one supported metric")
    return cleaned


def _score(metrics: dict[str, float | int]) -> float:
    # 加权互动系数走单一事实源 weighted_engagement;此处的「归一化」是÷播放量(转化率口径),
    # 与 search_ranker 的对数归一化(绝对声量)各自保留,仅系数统一。
    raw = weighted_engagement(metrics)
    views = metrics.get("views")
    if views is not None:
        raw = raw / max(float(views), 1.0)
    return round(raw, 6)


def _summary(score: float, metrics: dict[str, float | int]) -> str:
    parts = [f"score={score:g}"]
    parts.extend(f"{key}={metrics[key]:g}" for key in ["likes", "collects", "comments", "shares", "views", "conversions"] if key in metrics)
    return " ".join(parts)


def _content_text(
    title: str,
    score: float,
    metrics: dict[str, float | int],
    note_url: str | None,
) -> str:
    lines = [title, f"score: {score:g}"]
    lines.extend(f"{key}: {value:g}" for key, value in metrics.items())
    if note_url:
        lines.append(f"url: {note_url}")
    return "\n".join(lines)


def _channel_label(channel: str) -> str:
    return "小红书" if channel == "xiaohongshu" else f"{channel} "


def _unit_of_work(repo: Any):
    unit_of_work = getattr(repo, "unit_of_work", None)
    return unit_of_work() if callable(unit_of_work) else nullcontext()
