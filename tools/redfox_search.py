"""线上小红书实时检索工具(红狐 API)。

实时搜索小红书热门笔记,返回结构化卡片字段用于发现面板;**不落库**(瞬态)。
失败时优雅降级(返回 ok=False + reason),不抛错中断对话。
"""
from __future__ import annotations

import os
import re
from datetime import date, timedelta
from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

_REDFOX_URL = "https://redfox.hk/story/api/xhs/search/search"
_TIMEOUT_SECONDS = 20.0
_SUMMARY_MAX = 140

_NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item|item)/([0-9a-zA-Z]+)")
_BARE_TOKEN_RE = re.compile(r"([0-9a-f]{16,32})")


def _note_id_from_url(url: str) -> str:
    """从分享链接提取稳定 note_id;取不到回退整条 url。"""
    if not url:
        return ""
    m = _NOTE_ID_RE.search(url)
    if m:
        return m.group(1)
    m = _BARE_TOKEN_RE.search(url)
    if m:
        return m.group(1)
    return url.rstrip("/").rsplit("/", 1)[-1] or url


def _coerce_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    if isinstance(value, str):
        return [t.strip() for t in re.split(r"[,，#\s]+", value) if t.strip()]
    return []


def _to_int(value: Any) -> int:
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _to_float(value: Any) -> float:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return 0.0


def _map_article(item: dict[str, Any]) -> dict[str, Any]:
    note_url = str(item.get("shareInfoLink") or item.get("noteUrl") or "").strip()
    desc = str(item.get("desc") or "").strip()
    summary = desc[:_SUMMARY_MAX] + ("…" if len(desc) > _SUMMARY_MAX else "")
    return {
        "note_id": _note_id_from_url(note_url),
        "title": str(item.get("title") or "").strip(),
        "summary": summary,
        "author": str(item.get("authorNickname") or "").strip(),
        "author_fans": _to_int(item.get("authorFans")),
        "cover_url": str(item.get("cover") or "").strip(),
        "note_url": note_url,
        "likes": _to_int(item.get("likedCount")),
        "collects": _to_int(item.get("collectedCount")),
        "comments": _to_int(item.get("commentsCount")),
        "shares": _to_int(item.get("sharedCount")),
        "interactive": _to_int(item.get("interactiveCount")),
        "created_at": str(item.get("createTime") or "").strip(),
        "tags": _coerce_tags(item.get("topicsName")),
        "scores": {
            "relevance": _to_float(item.get("relevanceScore")),
            "popularity": _to_float(item.get("popularityScore")),
            "recency": _to_float(item.get("recencyScore")),
            "total": _to_float(item.get("totalScore")),
        },
        "source": "online",
        "already_local": False,
    }


def _mark_already_local(notes: list[dict[str, Any]]) -> None:
    """标记已被采纳入库的笔记(跨源去重 / 防重复采纳)。DB 不可用时静默跳过。"""
    note_ids = [n["note_id"] for n in notes if n.get("note_id")]
    if not note_ids:
        return
    try:
        from data_foundation.db import connect
        from data_foundation.permissions import default_tenant_id
        from data_foundation.repositories.resource import ResourceRepository
        from data_foundation.online_notes import find_adopted_note_ids

        conn = connect()
        try:
            repo = ResourceRepository(conn)
            adopted = find_adopted_note_ids(repo, tenant_id=default_tenant_id(), note_ids=note_ids)
        finally:
            conn.close()
    except Exception:  # noqa: BLE001 - 去重是增强,不可因 DB 故障阻断线上检索
        return
    for note in notes:
        if note.get("note_id") in adopted:
            note["already_local"] = True


@tool
def search_xhs_online(
    keyword: str,
    days: int = 30,
    page_size: int = 20,
    config: RunnableConfig = None,
) -> dict[str, Any]:
    """实时搜索小红书线上热门笔记(红狐 API),返回结构化卡片列表用于面板展示。

    线上结果默认瞬态、不落库;用户在面板勾选「采纳收录」后才入库 + 同步飞书。

    关键词用法(命中率关键):传**简短的核心词**(1 个名词/短词,如「握力圈」「敏感肌护肤」),
    **不要堆叠修饰词**(如「秋冬握力圈正确用法」往往 0 命中)。红狐对小众/长词组覆盖有限,
    返回空 `results` 是正常情况(非故障),此时可改用更宽泛的核心词重试,或仅用本地结果。

    Args:
        keyword: 搜索关键词(简短核心词,勿堆砌修饰)。
        days: 回溯天数(默认 30;红狐仅覆盖近 30 天,取满窗命中更多)。
        page_size: 返回条数。
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return {"ok": False, "reason": "EMPTY_KEYWORD", "results": []}

    api_key = os.environ.get("REDFOX_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "reason": "REDFOX_API_KEY_MISSING", "results": []}

    today = date.today()
    start_date = (today - timedelta(days=max(int(days), 1))).isoformat()
    payload = {
        "keyword": keyword,
        "pageNum": 1,
        "pageSize": min(max(int(page_size), 1), 50),
        "startDate": start_date,
        "endDate": today.isoformat(),
        "source": "search",
    }
    try:
        response = httpx.post(
            _REDFOX_URL,
            headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"REDFOX_HTTP_ERROR: {type(exc).__name__}", "results": []}
    except ValueError as exc:
        return {"ok": False, "reason": f"REDFOX_BAD_JSON: {exc}", "results": []}

    if not isinstance(body, dict) or body.get("code") != 2000:
        code = body.get("code") if isinstance(body, dict) else "non_dict"
        return {"ok": False, "reason": f"REDFOX_NON_2000: {code}", "results": []}

    data = body.get("data") or {}
    articles = data.get("articles") or []
    want = min(max(int(page_size), 1), 50)
    results = [_map_article(item) for item in articles if isinstance(item, dict)][:want]
    _mark_already_local(results)

    related = data.get("relatedSearches") or []
    related_searches: list[str] = []
    if isinstance(related, list):
        for item in related:
            kw = item.get("keyword") if isinstance(item, dict) else item
            if kw and str(kw).strip():
                related_searches.append(str(kw).strip())

    return {
        "ok": True,
        "keyword": keyword,
        "results": results,
        "related_searches": related_searches[:8],
    }
