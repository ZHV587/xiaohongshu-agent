from data_foundation.local_cards import (
    dedupe_by_note_url,
    hydrate_note_card,
)


def test_hydrate_feishu_record_maps_fields():
    content_json = {
        "fields": {
            "标题": "秋冬护肤攻略",
            "正文": "正" * 200,
            "博主": "护肤老师",
            "粉丝数": "12000",
            "封面链接": "http://sns-webpic-qc.xhscdn.com/a.jpg",
            "原文链接": "[查看原文](http://xhslink.com/o/abc)",
            "话题标签": "护肤,秋冬",
            "点赞数": 3000,
            "收藏数": 1500,
            "评论数": 300,
            "转发数": 200,
        },
        "table_name": "单篇采集库",
    }
    card = hydrate_note_card("rid-1", "feishu_base_record", content_json, score=0.7)
    assert card is not None
    assert card["title"] == "秋冬护肤攻略"
    assert card["author"] == "护肤老师"
    assert card["author_fans"] == 12000
    assert card["cover_url"] == "http://sns-webpic-qc.xhscdn.com/a.jpg"
    assert card["note_url"] == "http://xhslink.com/o/abc"
    assert card["likes"] == 3000 and card["collects"] == 1500
    # 无显式互动数 → 累加
    assert card["interactive"] == 3000 + 1500 + 300 + 200
    assert card["tags"] == ["护肤", "秋冬"]
    assert card["source"] == "local"
    assert card["already_local"] is True
    assert card["resource_id"] == "rid-1"
    assert len(card["summary"]) <= 141


def test_hydrate_online_note_uses_card_shape():
    content_json = {
        "note_id": "abc",
        "title": "线上笔记",
        "summary": "摘要",
        "author": "博主",
        "author_fans": 500,
        "cover_url": "http://cdn/x.jpg",
        "note_url": "http://xhslink.com/o/abc",
        "likes": 100,
        "collects": 50,
        "comments": 10,
        "shares": 5,
        "interactive": 165,
        "created_at": "2026-06-20",
        "tags": ["标签1", "标签2"],
    }
    card = hydrate_note_card("rid-2", "xhs_online_note", content_json, score=0.9)
    assert card["title"] == "线上笔记"
    assert card["note_url"] == "http://xhslink.com/o/abc"
    assert card["interactive"] == 165
    assert card["tags"] == ["标签1", "标签2"]
    assert card["source"] == "local"


def test_hydrate_non_note_type_returns_none():
    assert hydrate_note_card("rid", "generated_copy", {"title": "x"}) is None


def test_dedupe_by_note_url():
    cards = [
        {"resource_id": "1", "note_url": "http://a"},
        {"resource_id": "2", "note_url": "http://a"},  # dup
        {"resource_id": "3", "note_url": "http://b"},
        {"resource_id": "4", "note_url": ""},  # 空 url 用 rid 兜底,不并
        {"resource_id": "5", "note_url": ""},
    ]
    out = dedupe_by_note_url(cards)
    assert [c["resource_id"] for c in out] == ["1", "3", "4", "5"]
