from __future__ import annotations

import re
from typing import Any

from psycopg import Connection

from data_foundation.knowledge.models import KnowledgeEnrichResult
from data_foundation.knowledge.normalizer import normalize_knowledge_text
from data_foundation.knowledge.policy import classify_knowledge_asset
from data_foundation.knowledge.repository import PIPELINE_VERSION, KnowledgeRepository


_LIST_FIELDS = {
    "tags": ("tags", "topic_tags"),
    "hook_types": ("hook_types", "hook_type", "hook", "hook_mechanism"),
    "cta_types": ("cta_types", "cta_type", "cta"),
    "structure_tags": ("structure_tags", "structure"),
    "style_tags": ("style_tags", "style"),
    "success_factors": ("success_factors",),
}


def _stable_strings(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else [value]
    result: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, (str, int, float)) or isinstance(item, bool):
            continue
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _explicit_values(content_json: dict[str, Any], source_keys: tuple[str, ...]) -> list[str]:
    candidates = [content_json]
    nested = content_json.get("metadata")
    if isinstance(nested, dict):
        candidates.append(nested)
    values: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        for source_key in source_keys:
            for value in _stable_strings(candidate.get(source_key)):
                if value not in seen:
                    seen.add(value)
                    values.append(value)
    return values


def _infer_hook_types(title: str) -> list[str]:
    rules = (
        ("数字清单", bool(re.search(r"\d", title))),
        ("避坑警示", any(token in title for token in ("别", "不要", "千万", "避坑", "踩坑"))),
        ("问题悬念", any(token in title for token in ("为什么", "怎么", "如何", "?", "？"))),
        ("反常识", any(token in title for token in ("没想到", "居然", "原来", "反而"))),
    )
    return [label for label, matched in rules if matched]


def _infer_cta_types(body: str) -> list[str]:
    # CTA only counts in the tail; an instructional mention in the middle is not an
    # actual closing call-to-action.
    tail = body[-220:]
    rules = (
        ("评论互动", any(token in tail for token in ("评论区", "留言", "你会怎么", "告诉我", "聊聊"))),
        ("收藏", any(token in tail for token in ("收藏", "存下来", "先码住"))),
        ("关注追更", any(token in tail for token in ("关注", "下篇", "持续更新"))),
    )
    return [label for label, matched in rules if matched]


_LIST_LINE = re.compile(
    r"^\s*(?:[-*•·]|\d{1,2}[.、)）]|[一二三四五六七八九十]{1,3}[、.）)])\s*"
)
_EMOJI = re.compile(r"[\u2600-\u27bf\U0001f300-\U0001faff]")
_FIRST_PERSON_MARKERS = (
    "我用", "我把", "我在", "我是", "我曾", "我踩", "我觉得", "我发现",
    "我建议", "我的", "我们", "亲测", "实测",
)


def _observable_layout(body: str) -> tuple[list[str], bool]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\n", body) if part.strip()]
    list_line_count = sum(1 for paragraph in paragraphs if _LIST_LINE.match(paragraph))
    return paragraphs, list_line_count >= 2


def _infer_structure_tags(body: str) -> tuple[list[str], int, bool]:
    paragraphs, has_list = _observable_layout(body)
    if not paragraphs:
        return [], 0, False
    tags = ["清单体"] if has_list else []
    if len(paragraphs) <= 3:
        tags.append("短段落")
    elif len(paragraphs) <= 7:
        tags.append("中段落")
    else:
        tags.append("多段落")
    return tags, len(paragraphs), has_list


def _infer_style_tags(*, title: str, body: str, has_list: bool) -> list[str]:
    tags: list[str] = []
    if _EMOJI.search(f"{title}\n{body}"):
        tags.append("emoji点缀")
    if has_list:
        tags.append("清单表达")
    if any(marker in body for marker in _FIRST_PERSON_MARKERS):
        tags.append("第一人称")
    return tags


def extract_deterministic_metadata(
    content_json: dict[str, Any],
    normalized_text: str,
    *,
    title: str | None = None,
) -> dict[str, Any]:
    """Extract explicit metadata plus falsifiable surface-form writing features.

    The inference rules above are fixed string/regex checks.  They do not infer niche,
    success, intent, or quality when the source does not state those facts.
    """
    niche_values = _explicit_values(content_json, ("niche", "vertical"))
    observed_title = str(content_json.get("title") or title or "").strip()
    observed_body = str(content_json.get("body") or normalized_text or "").strip()
    inferred_structure, paragraph_count, has_list = _infer_structure_tags(observed_body)
    metadata: dict[str, Any] = {
        "pipeline_version": PIPELINE_VERSION,
        "niche": niche_values[0] if niche_values else None,
        "tags": [],
        "hook_types": [],
        "cta_types": [],
        "structure_tags": [],
        "style_tags": [],
        "success_factors": [],
        "normalized_length": len(normalized_text),
        "paragraph_count": paragraph_count,
    }
    for output_key, source_keys in _LIST_FIELDS.items():
        metadata[output_key] = _explicit_values(content_json, source_keys)

    # Explicit structured fields win.  Only absent dimensions are inferred, so the
    # pipeline never contradicts a teardown/user-provided label.
    if not metadata["hook_types"]:
        metadata["hook_types"] = _infer_hook_types(observed_title)
    if not metadata["cta_types"]:
        metadata["cta_types"] = _infer_cta_types(observed_body)
    if not metadata["structure_tags"]:
        metadata["structure_tags"] = inferred_structure
    if not metadata["style_tags"]:
        metadata["style_tags"] = _infer_style_tags(
            title=observed_title,
            body=observed_body,
            has_list=has_list,
        )
    return metadata


class KnowledgeService:
    def __init__(self, conn: Connection, *, repository: KnowledgeRepository | None = None):
        self.repository = repository or KnowledgeRepository(conn)

    def enrich_exact_version(
        self,
        *,
        tenant_id: str,
        resource_id: str,
        resource_version: int,
    ) -> KnowledgeEnrichResult:
        # The decision depends on mutable facts outside the immutable resource version
        # (confirmation, lifecycle target, live status and exact evidence edges).  Hold
        # one exact-resource lock across read, classification and persistence so an
        # older snapshot cannot win after a newer fact was committed.
        with self.repository.classification_scope(
            tenant_id=tenant_id,
            resource_id=resource_id,
        ):
            snapshot = self.repository.load_snapshot(
                tenant_id=tenant_id,
                resource_id=resource_id,
                resource_version=resource_version,
            )
            if snapshot is None:
                return KnowledgeEnrichResult(
                    status="superseded",
                    resource_id=resource_id,
                    resource_version=resource_version,
                )
            normalized = normalize_knowledge_text(snapshot.content_text)
            decision = classify_knowledge_asset(snapshot, normalized_text=normalized)
            enrichment = extract_deterministic_metadata(
                snapshot.content_json,
                normalized,
                title=snapshot.title,
            )
            return self.repository.persist_enrichment(
                snapshot=snapshot,
                decision=decision,
                normalized_text=normalized,
                enrichment_metadata=enrichment,
            )
