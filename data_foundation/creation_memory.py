from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from data_foundation.outbox_requests import default_write_requests

DERIVED_EDGE = "derived_from"
FEEDBACK_EDGE = "feedback_on"


def save_generated_topic_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    direction: str,
    topics: list[str],
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    direction = direction.strip()
    if not direction:
        raise ValueError("direction is required")
    topics = _clean_strings(topics, field="topics")
    cleaned_evidence = _clean_evidence(evidence)
    with _unit_of_work(repo):
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type="generated_topic",
            title=f"{direction} 选题",
            summary="; ".join(topics[:3]),
            content_text="\n".join(f"- {topic}" for topic in topics),
            content_json={"direction": direction, "topics": topics, "evidence": cleaned_evidence},
            visibility="team",
            owner_open_id=actor_open_id,
            outbox_requests=default_write_requests(),
        )
        _link_evidence(repo, tenant_id=tenant_id, generated_id=resource.id, evidence=cleaned_evidence)
    return _payload(resource, cleaned_evidence)


def save_generated_copy_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    title: str,
    body: str,
    tags: list[str],
    source_topic: str | None = None,
    evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    title = title.strip()
    if not title:
        raise ValueError("title is required")
    body = body.strip()
    if not body:
        raise ValueError("body is required")
    cleaned_tags = [tag.strip() for tag in tags if isinstance(tag, str) and tag.strip()]
    cleaned_evidence = _clean_evidence(evidence)
    source_topic = source_topic.strip() if isinstance(source_topic, str) and source_topic.strip() else None
    parts = [title, "", body]
    if cleaned_tags:
        parts.extend(["", " ".join(cleaned_tags)])
    with _unit_of_work(repo):
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type="generated_copy",
            title=title,
            summary=source_topic,
            content_text="\n".join(parts),
            content_json={
                "title": title,
                "body": body,
                "tags": cleaned_tags,
                "source_topic": source_topic,
                "evidence": cleaned_evidence,
            },
            visibility="team",
            owner_open_id=actor_open_id,
            outbox_requests=default_write_requests(),
        )
        _link_evidence(repo, tenant_id=tenant_id, generated_id=resource.id, evidence=cleaned_evidence)
    return _payload(resource, cleaned_evidence)


def save_user_feedback_resource(
    repo: Any,
    *,
    tenant_id: str,
    actor_open_id: str,
    feedback: str,
    target_resource_id: str | None = None,
    feedback_type: str = "user_feedback",
) -> dict[str, Any]:
    feedback = feedback.strip()
    if not feedback:
        raise ValueError("feedback is required")
    if feedback_type not in {"user_feedback", "revision_request"}:
        raise ValueError("feedback_type must be user_feedback or revision_request")
    target_resource_id = (
        target_resource_id.strip()
        if isinstance(target_resource_id, str) and target_resource_id.strip()
        else None
    )
    if feedback_type == "revision_request" and not target_resource_id:
        raise ValueError("target_resource_id is required for revision_request")
    with _unit_of_work(repo):
        resource = repo.upsert_resource(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            resource_type=feedback_type,
            title="用户反馈" if feedback_type == "user_feedback" else "修改意见",
            summary=feedback[:120],
            content_text=feedback,
            content_json={"feedback": feedback, "target_resource_id": target_resource_id},
            visibility="team",
            owner_open_id=actor_open_id,
            outbox_requests=default_write_requests(),
        )
        if target_resource_id:
            repo.add_edge(
                tenant_id=tenant_id,
                source_resource_id=resource.id,
                target_resource_id=target_resource_id,
                edge_type=FEEDBACK_EDGE,
                weight=1.0,
            )
    return _payload(resource, [])


def _clean_strings(values: list[str], *, field: str) -> list[str]:
    cleaned = [value.strip() for value in values if isinstance(value, str) and value.strip()]
    if not cleaned:
        raise ValueError(f"{field} must contain at least one non-empty string")
    return cleaned


def _clean_evidence(evidence: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        resource_id = item.get("resource_id")
        if not isinstance(resource_id, str) or not resource_id.strip():
            continue
        resource_id = resource_id.strip()
        if resource_id in seen:
            continue
        seen.add(resource_id)
        cleaned_item = {
            "resource_id": resource_id,
            "title": _clean_optional_string(item.get("title")),
            "summary": _clean_optional_string(item.get("summary")),
            "source_updated_at": _clean_optional_string(item.get("source_updated_at")),
            "indexed_at": _clean_optional_string(item.get("indexed_at")),
        }
        cleaned.append(cleaned_item)
    return cleaned


def _link_evidence(
    repo: Any,
    *,
    tenant_id: str,
    generated_id: str,
    evidence: list[dict[str, str]],
) -> None:
    for item in evidence:
        repo.add_edge(
            tenant_id=tenant_id,
            source_resource_id=generated_id,
            target_resource_id=item["resource_id"],
            edge_type=DERIVED_EDGE,
            weight=1.0,
        )


def _payload(resource: Any, evidence: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "ok": True,
        "resource": {
            "resource_id": resource.id,
            "type": resource.type,
            "title": resource.title,
            "version": resource.version,
        },
        "evidence_count": len(evidence),
    }


def _clean_optional_string(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _unit_of_work(repo: Any):
    unit_of_work = getattr(repo, "unit_of_work", None)
    return unit_of_work() if callable(unit_of_work) else nullcontext()
