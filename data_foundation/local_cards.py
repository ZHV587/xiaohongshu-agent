"""发现专用本地卡片 hydration(真问题A 修复)。

把本地已收录资源(feishu_base_record / xhs_online_note)的 content_json 映射成与线上
统一的细致卡片形状(封面/互动/标签),供发现面板渲染。

**独立于** rank_evidence / EvidencePackage 证据链:那条路径(search_resources /
semantic_search_resources)的返回结构不受本模块影响。
"""
from __future__ import annotations

from typing import Any

from tools.feishu_bitable import extract_cover_url, extract_note_url

NOTE_CARD_TYPES = ("feishu_base_record", "xhs_online_note")

_SUMMARY_MAX = 140
_TITLE_FIELDS = ("标题", "选题", "title", "Title")
_BODY_FIELDS = ("正文", "正文内容", "视频文案", "笔记正文", "content", "Content")
_AUTHOR_FIELDS = ("博主", "作者", "博主昵称", "达人", "author")
_FANS_FIELDS = ("粉丝数", "粉丝量", "博主粉丝数", "fans")
_CREATED_FIELDS = ("发布时间", "笔记发布时间", "创建时间", "createTime", "时间")
_TAGS_FIELDS = ("话题标签", "标签", "话题", "tags")
_METRIC_FIELDS = {
    "likes": ("点赞数", "点赞", "likes"),
    "collects": ("收藏数", "收藏", "collects"),
    "comments": ("评论数", "评论", "comments"),
    "shares": ("转发数", "分享数", "转发", "shares"),
    "interactive": ("互动数", "互动量", "interactive"),
}


def _first(fields: dict[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = fields.get(name)
        if value not in (None, "", [], {}):
            if isinstance(value, list):
                return " ".join(str(v) for v in value if str(v).strip())
            return str(value)
    return ""


def _to_int(value: Any) -> int:
    try:
        n = int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _metric(fields: dict[str, Any], key: str) -> int:
    return _to_int(fields.get(next((n for n in _METRIC_FIELDS[key] if n in fields), "")))


def _coerce_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        import re

        return [t.strip() for t in re.split(r"[,，#\s]+", value) if t.strip()]
    return []


def _hydrate_feishu_record(content_json: dict[str, Any]) -> dict[str, Any]:
    fields = content_json.get("fields") or {}
    if not isinstance(fields, dict):
        fields = {}
    body = _first(fields, _BODY_FIELDS)
    summary = body[:_SUMMARY_MAX] + ("…" if len(body) > _SUMMARY_MAX else "")
    interactive = _metric(fields, "interactive")
    likes = _metric(fields, "likes")
    collects = _metric(fields, "collects")
    comments = _metric(fields, "comments")
    shares = _metric(fields, "shares")
    if not interactive:
        interactive = likes + collects + comments + shares
    return {
        "title": _first(fields, _TITLE_FIELDS),
        "summary": summary,
        "author": _first(fields, _AUTHOR_FIELDS),
        "author_fans": _to_int(_first(fields, _FANS_FIELDS)),
        "cover_url": extract_cover_url(fields),
        "note_url": extract_note_url(fields),
        "likes": likes,
        "collects": collects,
        "comments": comments,
        "shares": shares,
        "interactive": interactive,
        "created_at": _first(fields, _CREATED_FIELDS),
        "tags": _coerce_tags(fields.get(next((n for n in _TAGS_FIELDS if n in fields), ""))),
    }


def _hydrate_online_note(content_json: dict[str, Any]) -> dict[str, Any]:
    """xhs_online_note 的 content_json 已是卡片形状,直接取用。"""
    cj = content_json
    return {
        "title": str(cj.get("title") or ""),
        "summary": str(cj.get("summary") or ""),
        "author": str(cj.get("author") or ""),
        "author_fans": _to_int(cj.get("author_fans")),
        "cover_url": str(cj.get("cover_url") or ""),
        "note_url": str(cj.get("note_url") or ""),
        "likes": _to_int(cj.get("likes")),
        "collects": _to_int(cj.get("collects")),
        "comments": _to_int(cj.get("comments")),
        "shares": _to_int(cj.get("shares")),
        "interactive": _to_int(cj.get("interactive")),
        "created_at": str(cj.get("created_at") or ""),
        "tags": _coerce_tags(cj.get("tags")),
    }


def hydrate_note_card(
    resource_id: str,
    resource_type: str,
    content_json: dict[str, Any] | None,
    *,
    score: float = 0.0,
) -> dict[str, Any] | None:
    """把一条本地资源映射为统一卡片;非笔记类型 → None。"""
    if resource_type not in NOTE_CARD_TYPES:
        return None
    cj = content_json or {}
    base = (
        _hydrate_online_note(cj)
        if resource_type == "xhs_online_note"
        else _hydrate_feishu_record(cj)
    )
    base.update({
        "note_id": base.get("note_url") or resource_id,
        "resource_id": str(resource_id),
        "source": "local",
        "already_local": True,
        "score": round(float(score or 0.0), 4),
    })
    return base


def dedupe_by_note_url(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 note_url 去重(空 note_url 用 resource_id 兜底,不误并)。保序。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for card in cards:
        key = card.get("note_url") or f"__rid__{card.get('resource_id')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(card)
    return out
