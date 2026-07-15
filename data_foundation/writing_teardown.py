from __future__ import annotations

from contextlib import nullcontext
import math
from typing import Any
import uuid

from data_foundation.outbox_requests import default_write_requests


TEARDOWN_EDGE = "teardown_of"
TEARDOWN_NAMESPACE = uuid.UUID("522b8cd5-2ce8-4fe9-874f-a74b7772a593")
TEARDOWN_ANALYSIS_SCHEMA_VERSION = 1
TEARDOWN_DETERMINISTIC_QUALITY = 0.8


def save_writing_teardown_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    source_resource_id: str,
    source_resource_version: int,
    niche: str,
    hook: str,
    cta: str,
    structure: list[str],
    success_factors: list[str],
    style_tags: list[str],
    quality: float,
) -> dict[str, Any]:
    """Persist one exact, ACL-checked writing teardown and its versioned graph edge."""
    source_resource_id = _required_text(source_resource_id, field="source_resource_id")
    source_resource_version = _required_version(
        source_resource_version, field="source_resource_version"
    )
    niche = _required_text(niche, field="niche")
    hook = _required_text(hook, field="hook")
    cta = _required_text(cta, field="cta")
    structure = _required_strings(structure, field="structure")
    success_factors = _required_strings(success_factors, field="success_factors")
    style_tags = _required_strings(style_tags, field="style_tags")
    if (
        not isinstance(quality, (int, float))
        or isinstance(quality, bool)
        or not math.isfinite(float(quality))
        or not 0 <= float(quality) <= 100
    ):
        raise ValueError("quality must be a finite number between 0 and 100")
    # quality 是模型对“拆解完整度”的自评，只作为审计信息保存，绝不能反过来决定
    # 自己是否有资格进入知识库。资格与质量由 policy 根据 schema 完整性和精确来源边确定。
    model_assessed_quality = float(quality)

    with _unit_of_work(repo):
        source = repo.get_resource_for_knowledge(
            tenant_id,
            actor_open_id,
            source_resource_id,
            source_resource_version,
        )
        if source is None:
            raise PermissionError(
                "source resource version is not current qualified knowledge or not readable"
            )
        visibility = "team" if source.visibility == "team" else "private"
        content_json = {
            "analysis_schema_version": TEARDOWN_ANALYSIS_SCHEMA_VERSION,
            "analysis_kind": "writing_teardown",
            "metadata_provenance": "model_analysis_exact_source",
            "source_resource_id": source_resource_id,
            "source_resource_version": source_resource_version,
            "niche": niche,
            "hook": hook,
            "cta": cta,
            "structure": structure,
            "success_factors": success_factors,
            "style_tags": style_tags,
            "model_assessed_quality": model_assessed_quality,
        }
        content_text = "\n".join(
            [
                f"垂类：{niche}",
                f"钩子：{hook}",
                f"行动引导：{cta}",
                "结构：" + " → ".join(structure),
                "成功要素：" + "；".join(success_factors),
                "风格标签：" + "、".join(style_tags),
                f"模型完整度自评：{model_assessed_quality:g}",
            ]
        )
        stable_identity = (
            f"{tenant_id}:{actor_open_id}:{source_resource_id}:"
            f"{source_resource_version}:{TEARDOWN_EDGE}"
        )
        teardown_resource_id = str(uuid.uuid5(TEARDOWN_NAMESPACE, stable_identity))
        existing = None
        get_resource = getattr(repo, "get_resource", None)
        if callable(get_resource):
            existing = get_resource(tenant_id, actor_open_id, teardown_resource_id)
        idempotent_replay = bool(
            existing is not None
            and dict(getattr(existing, "content_json", {}) or {}) == content_json
            and str(getattr(existing, "content_text", "") or "") == content_text
        )
        teardown = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_id=teardown_resource_id,
            resource_type="writing_teardown",
            title=f"{source.title} · 写作拆解",
            summary=f"{niche} · {hook[:80]}",
            content_text=content_text,
            content_json=content_json,
            visibility=visibility,
            owner_open_id=actor_open_id,
            mapping={
                "system": "internal",
                "external_type": "writing_teardown",
                "external_id": stable_identity,
                "sync_status": "synced",
            },
            outbox_requests=default_write_requests(),
        )
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=teardown.id,
            source_resource_version=int(teardown.version),
            target_resource_id=source_resource_id,
            target_resource_version=source_resource_version,
            edge_type=TEARDOWN_EDGE,
            weight=1.0,
            properties={
                "analysis_kind": "writing_teardown",
                "analysis_schema_version": TEARDOWN_ANALYSIS_SCHEMA_VERSION,
                "provenance": "exact_source",
            },
        )

    return {
        "ok": True,
        "resource_id": str(teardown.id),
        "resource_version": int(teardown.version),
        "source_resource_id": source_resource_id,
        "source_resource_version": source_resource_version,
        "edge_type": TEARDOWN_EDGE,
        "idempotent_replay": idempotent_replay,
    }


def _required_text(value: Any, *, field: str) -> str:
    cleaned = value.strip() if isinstance(value, str) else ""
    if not cleaned:
        raise ValueError(f"{field} is required")
    return cleaned


def _required_version(value: Any, *, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _required_strings(values: Any, *, field: str) -> list[str]:
    if not isinstance(values, list):
        raise ValueError(f"{field} must be an array")
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not cleaned:
        raise ValueError(f"{field} must contain at least one non-empty string")
    return cleaned


def _unit_of_work(repo: Any):
    unit_of_work = getattr(repo, "unit_of_work", None)
    return unit_of_work() if callable(unit_of_work) else nullcontext()


__all__ = [
    "TEARDOWN_ANALYSIS_SCHEMA_VERSION",
    "TEARDOWN_DETERMINISTIC_QUALITY",
    "TEARDOWN_EDGE",
    "TEARDOWN_NAMESPACE",
    "save_writing_teardown_resource",
]
