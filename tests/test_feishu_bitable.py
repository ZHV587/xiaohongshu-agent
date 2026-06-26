import os
import json
import pytest
from unittest.mock import patch
from tools.feishu_bitable import read_xhs_data, list_base_tables, _read_single_table


def test_read_xhs_data_missing_env():
    with patch.dict(os.environ, {}, clear=True):
        res = read_xhs_data.func()
        assert "error" in res
        assert "FEISHU_BITABLE_APP_TOKEN" in res["error"]


def _table_list_resp(tables):
    return json.dumps({"data": {"has_more": False, "items": tables}})


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_aggregates_all_tables(mock_lark_cli):
    # 第一次调用列出表;之后每张表读取一次。
    table_list = _table_list_resp([
        {"table_id": "tblA", "name": "关键词搜索"},
        {"table_id": "tblB", "name": "选题仓库"},
    ])
    tblA_records = json.dumps({"data": {"has_more": False, "items": [
        {"record_id": "recA1", "fields": {"标题": "爆款笔记", "点赞数": 999}},
    ]}})
    tblB_records = json.dumps({"data": {"has_more": False, "items": [
        {"record_id": "recB1", "fields": {"选题": "秋季护肤", "创作方向": "成分党"}},
    ]}})
    mock_lark_cli.func.side_effect = [table_list, tblA_records, tblB_records]

    with patch.dict(os.environ, {"FEISHU_BITABLE_APP_TOKEN": "app_tok"}):
        res = read_xhs_data.func()

    assert "error" not in res
    # 聚合了两张表的记录
    assert len(res["sync_rows"]) == 2
    names = {r["table_name"] for r in res["sync_rows"]}
    assert names == {"关键词搜索", "选题仓库"}
    # 每行带来源 table_id / table_name
    a = next(r for r in res["sync_rows"] if r["table_name"] == "关键词搜索")
    assert a["table_id"] == "tblA"
    assert a["fields"]["标题"] == "爆款笔记"
    b = next(r for r in res["sync_rows"] if r["table_name"] == "选题仓库")
    assert b["fields"]["选题"] == "秋季护肤"
    # 表清单摘要
    assert {t["name"] for t in res["tables"]} == {"关键词搜索", "选题仓库"}


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_keeps_link_columns_drops_attachments(mock_lark_cli):
    """收窄修正:放行「封面链接」「原文链接」「图片链接」等文本直链列;
    仅剔除附件【对象】列(含 file_token)与提示词/设置等系统/噪声列。"""
    mock_lark_cli.func.side_effect = [
        _table_list_resp([{"table_id": "tblA", "name": "笔记"}]),
        json.dumps({"data": {"has_more": False, "items": [
            {"record_id": "rec1", "fields": {
                "标题": "x",
                "正文": "body",
                "封面链接": "http://sns-webpic-qc.xhscdn.com/abc.jpg",
                "原文链接": "[查看原文](http://xhslink.com/o/abc)",
                "图片链接": "http://img.example.com/1.png",
                # 附件对象列(含 file_token)→ 按值形状剔除
                "封面": [{"file_token": "tok1", "name": "c.png", "type": "image/png"}],
                "图片附件": [{"file_token": "tok2", "name": "a.png"}],
                "提示词": "请写一篇...",
                "⚙️设置": "系统列",
            }},
        ]}}),
    ]
    with patch.dict(os.environ, {"FEISHU_BITABLE_APP_TOKEN": "app_tok"}):
        res = read_xhs_data.func()
    fields = res["sync_rows"][0]["fields"]
    # 文本直链列被放行
    assert fields["封面链接"] == "http://sns-webpic-qc.xhscdn.com/abc.jpg"
    assert fields["原文链接"] == "[查看原文](http://xhslink.com/o/abc)"
    assert fields["图片链接"] == "http://img.example.com/1.png"
    assert "标题" in fields and "正文" in fields
    # 附件对象列与系统/噪声列被剔除
    assert "封面" not in fields
    assert "图片附件" not in fields
    assert "提示词" not in fields
    assert "⚙️设置" not in fields


def test_extract_cover_url_prefers_text_direct_link():
    from tools.feishu_bitable import extract_cover_url
    assert extract_cover_url({"封面链接": "http://cdn/x.jpg"}) == "http://cdn/x.jpg"
    # 富文本片段数组
    assert extract_cover_url({"图片链接": [{"type": "text", "text": "http://cdn/y.png"}]}) == "http://cdn/y.png"
    # 无封面列
    assert extract_cover_url({"标题": "x"}) == ""


def test_extract_note_url_from_markdown():
    from tools.feishu_bitable import extract_note_url
    assert extract_note_url({"原文链接": "[查看原文](http://xhslink.com/o/abc)"}) == "http://xhslink.com/o/abc"
    # 裸 URL
    assert extract_note_url({"笔记链接": "http://xhslink.com/o/def"}) == "http://xhslink.com/o/def"
    assert extract_note_url({"标题": "x"}) == ""


def test_is_attachment_value_shape():
    from tools.feishu_bitable import _is_attachment_value
    assert _is_attachment_value([{"file_token": "t", "name": "a.png"}]) is True
    assert _is_attachment_value("http://cdn/x.jpg") is False
    assert _is_attachment_value([]) is False
    assert _is_attachment_value([{"text": "x"}]) is False


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_table_list_error(mock_lark_cli):
    mock_lark_cli.func.return_value = "Error: permission denied"
    with patch.dict(os.environ, {"FEISHU_BITABLE_APP_TOKEN": "app_tok"}):
        res = read_xhs_data.func()
    assert "error" in res
    assert "失败" in res["error"]


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_per_table_error_is_collected_not_fatal(mock_lark_cli):
    # 一张表读失败,不影响其他表;失败记入 source_errors。
    mock_lark_cli.func.side_effect = [
        _table_list_resp([
            {"table_id": "tblA", "name": "好表"},
            {"table_id": "tblB", "name": "坏表"},
        ]),
        json.dumps({"data": {"has_more": False, "items": [
            {"record_id": "recA1", "fields": {"标题": "ok"}},
        ]}}),
        "Feishu authorization scope insufficient",
    ]
    with patch.dict(os.environ, {"FEISHU_BITABLE_APP_TOKEN": "app_tok"}):
        res = read_xhs_data.func()
    assert len(res["sync_rows"]) == 1
    assert any("坏表" in e for e in res["source_errors"])


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_does_not_print_tokens(capsys):
    with patch.dict(os.environ, {"FEISHU_BITABLE_APP_TOKEN": "secret_app_token"}):
        with patch("tools.lark_cli.lark_cli") as m:
            m.func.return_value = "Error: stop"
            read_xhs_data.func()
    captured = capsys.readouterr()
    assert "secret_app_token" not in captured.out


@patch("tools.lark_cli.lark_cli")
def test_read_single_table_paginates(mock_lark_cli):
    page1 = json.dumps({"data": {"has_more": True, "items": [
        {"record_id": "r1", "fields": {"标题": "第一篇"}}]}})
    page2 = json.dumps({"data": {"has_more": False, "items": [
        {"record_id": "r2", "fields": {"标题": "第二篇"}}]}})
    mock_lark_cli.func.side_effect = [page1, page2]
    rows, err = _read_single_table(app_token="app", table_id="tblA", table_name="t")
    assert err is None
    assert [r["record_id"] for r in rows] == ["r1", "r2"]
    # 第二页带 offset
    assert "--offset 200" in mock_lark_cli.func.call_args_list[1][0][0]


@patch("tools.lark_cli.lark_cli")
def test_list_base_tables(mock_lark_cli):
    mock_lark_cli.func.return_value = _table_list_resp([
        {"table_id": "t1", "name": "表一"},
        {"table_id": "t2", "name": "表二"},
    ])
    tables, err = list_base_tables("app_tok")
    assert err is None
    assert tables == [{"table_id": "t1", "name": "表一"}, {"table_id": "t2", "name": "表二"}]
