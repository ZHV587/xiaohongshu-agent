"""发现专用本地卡片 hydration(真问题A 修复)。

把本地已收录资源(feishu_base_record / xhs_online_note)的 content_json 映射成与线上
统一的细致卡片形状(封面/互动/标签),供发现面板渲染。

**独立于** EvidencePackage 证据链:`retrieve_knowledge` 的返回结构不受本模块影响。
"""
from __future__ import annotations

from typing import Any

from data_foundation.metric_parse import parse_count_int
from tools.feishu_bitable import extract_cover_url, extract_note_url

NOTE_CARD_TYPES = ("feishu_base_record", "xhs_online_note")

_SUMMARY_MAX = 140
_TITLE_FIELDS = ("标题", "选题", "title", "Title")
_BODY_FIELDS = ("正文", "正文内容", "视频文案", "笔记正文", "content", "Content")
_AUTHOR_FIELDS = ("博主", "作者", "博主昵称", "达人", "author")
_FANS_FIELDS = ("粉丝数", "粉丝量", "博主粉丝数", "fans")
_CREATED_FIELDS = ("发布时间", "笔记发布时间", "创建时间", "createTime", "时间")
_TAGS_FIELDS = ("话题标签", "标签", "话题", "tags")
# 评论行标志字段:飞书表里评论数据与笔记混在一张表,评论行有「评论内容」等字段但无正文/封面,
# 不该当作参考笔记卡出现在发现面板(报告的 bug:本地卡里混入无封面的评论/配置行)。
_COMMENT_MARKER_FIELDS = ("评论内容", "评论时间", "回复数")
# 配置/字典行:如「搜索下拉词」「选题类型」等运营配置,标题是这些固定词、无正文无链接,同样过滤。
_CONFIG_TITLE_MARKERS = ("搜索下拉词", "爆款搜索", "选题类型", "选题分类", "种子词", "关键词")
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
    # 经 parse_count_int 统一解析,支持 "1.2万"/"10w+" 等单位(卡片互动数展示用)。
    return parse_count_int(value)


def _metric(fields: dict[str, Any], key: str) -> int:
    return _to_int(fields.get(next((n for n in _METRIC_FIELDS[key] if n in fields), "")))


def _coerce_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        import re

        return [t.strip() for t in re.split(r"[,，#\s]+", value) if t.strip()]
    return []


def _is_non_note_row(fields: dict[str, Any], title: str, body: str) -> bool:
    """判定一行是否**不是**参考笔记(评论行 / 配置字典行),这类行不该当笔记卡渲染。

    - 评论行:有「评论内容」等字段,且没有正文(评论本身不是一篇笔记)。
    - 配置行:标题命中「搜索下拉词/选题类型」等固定运营字典词,且无正文。
    真笔记(有正文或标题且非上述字典词)一律放行,缺封面走占位,不误杀。
    """
    has_comment_marker = any(f in fields for f in _COMMENT_MARKER_FIELDS)
    if has_comment_marker and not body:
        return True
    if not body and any(marker in title for marker in _CONFIG_TITLE_MARKERS):
        return True
    return False


def _fallback_cover(fields: dict[str, Any]) -> str:
    """封面直链取空时的兜底:从附件对象列的公网 url 里捞一张(有则用,无则空,不伪造)。

    飞书附件对象通常只有带时效的 tmp_url,但部分同步会带 url 直链;能取到就比破图/占位强。
    """
    for name, value in fields.items():
        if "图" not in name and "封面" not in name and "附件" not in name:
            continue
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    url = item.get("url") or item.get("tmp_url")
                    if isinstance(url, str) and url.startswith("http"):
                        return url
    return ""


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
    resource_version: int,
    resource_type: str,
    content_json: dict[str, Any] | None,
    *,
    score: float = 0.0,
) -> dict[str, Any] | None:
    if (
        not isinstance(resource_version, int)
        or isinstance(resource_version, bool)
        or resource_version <= 0
    ):
        raise ValueError("resource_version must be a positive integer")
    """把一条本地资源映射为统一卡片;非笔记类型 → None。"""
    if resource_type not in NOTE_CARD_TYPES:
        return None
    cj = content_json or {}
    base = (
        _hydrate_online_note(cj)
        if resource_type == "xhs_online_note"
        else _hydrate_feishu_record(cj)
    )
    # 过滤非笔记行(评论/配置字典行):它们无正文无封面,不该当参考笔记卡出现。
    if resource_type == "feishu_base_record":
        fields = cj.get("fields") if isinstance(cj.get("fields"), dict) else {}
        if _is_non_note_row(fields, base.get("title") or "", base.get("summary") or ""):
            return None
        # 真笔记但封面直链取空 → 从附件对象列兜底捞一张公网 url(取不到则留空走前端占位)。
        if not base.get("cover_url"):
            base["cover_url"] = _fallback_cover(fields)
    base.update({
        "note_id": base.get("note_url") or resource_id,
        "resource_id": str(resource_id),
        "resource_version": resource_version,
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
