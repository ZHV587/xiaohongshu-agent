import os
from unittest.mock import MagicMock, patch

import httpx
import pytest

import tools.redfox_search as rfs
from tools.redfox_search import search_xhs_online, _map_article, _note_id_from_url


def _resp(payload, status=200):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload
    r.raise_for_status.return_value = None
    return r


_SAMPLE = {
    "code": 2000,
    "data": {
        "articles": [
            {
                "title": "秋冬护肤攻略",
                "desc": "x" * 200,
                "authorNickname": "护肤老师",
                "authorFans": 12000,
                "cover": "http://sns-webpic-qc.xhscdn.com/a.jpg",
                "shareInfoLink": "http://xhslink.com/o/abc123def456",
                "interactiveCount": 5000,
                "likedCount": 3000,
                "collectedCount": 1500,
                "commentsCount": 300,
                "sharedCount": 200,
                "topicsName": "护肤,秋冬",
                "createTime": "2026-06-20",
                "relevanceScore": 0.9,
                "popularityScore": 0.8,
                "recencyScore": 0.7,
                "totalScore": 0.85,
            }
        ],
        "relatedSearches": ["秋冬护肤", "面霜推荐"],
    },
}


def test_empty_keyword_short_circuits():
    res = search_xhs_online.func(keyword="  ")
    assert res["ok"] is False
    assert res["reason"] == "EMPTY_KEYWORD"


def test_missing_api_key():
    with patch.dict(os.environ, {}, clear=True):
        res = search_xhs_online.func(keyword="护肤")
    assert res["ok"] is False
    assert res["reason"] == "REDFOX_API_KEY_MISSING"


@patch.object(rfs, "_mark_already_local", lambda notes: None)
def test_maps_articles(monkeypatch):
    monkeypatch.setenv("REDFOX_API_KEY", "ak_test")
    with patch("tools.redfox_search.httpx.post", return_value=_resp(_SAMPLE)):
        res = search_xhs_online.func(keyword="护肤", days=7, page_size=20)
    assert res["ok"] is True
    assert res["related_searches"] == ["秋冬护肤", "面霜推荐"]
    note = res["results"][0]
    assert note["note_id"] == "abc123def456"
    assert note["title"] == "秋冬护肤攻略"
    assert note["cover_url"].startswith("http://sns-webpic-qc")
    assert note["note_url"].startswith("http://xhslink.com/o/")
    assert note["likes"] == 3000 and note["collects"] == 1500
    assert note["interactive"] == 5000
    assert note["tags"] == ["护肤", "秋冬"]
    assert note["scores"]["total"] == 0.85
    assert note["source"] == "online"
    assert note["already_local"] is False
    # 摘要被截断
    assert len(note["summary"]) <= 141


def test_non_2000_degrades(monkeypatch):
    monkeypatch.setenv("REDFOX_API_KEY", "ak_test")
    with patch("tools.redfox_search.httpx.post", return_value=_resp({"code": 4001, "msg": "bad"})):
        res = search_xhs_online.func(keyword="护肤")
    assert res["ok"] is False
    assert "REDFOX_NON_2000" in res["reason"]
    assert res["results"] == []


def test_http_error_degrades(monkeypatch):
    monkeypatch.setenv("REDFOX_API_KEY", "ak_test")
    with patch("tools.redfox_search.httpx.post", side_effect=httpx.ConnectTimeout("t")):
        res = search_xhs_online.func(keyword="护肤")
    assert res["ok"] is False
    assert "REDFOX_HTTP_ERROR" in res["reason"]


@patch.object(rfs, "_mark_already_local")
def test_already_local_marking(mark, monkeypatch):
    def _mark(notes):
        for n in notes:
            n["already_local"] = True
    mark.side_effect = _mark
    monkeypatch.setenv("REDFOX_API_KEY", "ak_test")
    with patch("tools.redfox_search.httpx.post", return_value=_resp(_SAMPLE)):
        res = search_xhs_online.func(keyword="护肤")
    assert res["results"][0]["already_local"] is True


def test_note_id_from_url_variants():
    assert _note_id_from_url("http://xhslink.com/o/abc123def456") == "abc123def456"
    assert _note_id_from_url("https://www.xiaohongshu.com/explore/64f0a1b2c3d4e5f6") == "64f0a1b2c3d4e5f6"
    assert _note_id_from_url("") == ""


def test_map_article_handles_missing_fields():
    card = _map_article({})
    assert card["note_id"] == ""
    assert card["likes"] == 0
    assert card["tags"] == []
    assert card["scores"]["total"] == 0.0


@patch.object(rfs, "_mark_already_local", lambda notes: None)
def test_related_searches_dicts_and_page_size_cap(monkeypatch):
    monkeypatch.setenv("REDFOX_API_KEY", "ak_test")
    payload = {
        "code": 2000,
        "data": {
            "articles": [{"title": f"n{i}", "shareInfoLink": f"http://xhslink.com/o/id{i}"} for i in range(50)],
            "relatedSearches": [
                {"keyword": "护肤分享", "articleCount": 12309},
                {"keyword": "抗老", "articleCount": 6139},
            ],
        },
    }
    with patch("tools.redfox_search.httpx.post", return_value=_resp(payload)):
        res = search_xhs_online.func(keyword="护肤", page_size=5)
    assert res["ok"] is True
    assert len(res["results"]) == 5  # 截断到 page_size,即使 API 返回 50 条
    assert res["related_searches"] == ["护肤分享", "抗老"]  # 取 keyword,不吐裸 dict

