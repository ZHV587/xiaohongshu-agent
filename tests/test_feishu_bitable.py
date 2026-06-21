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
def test_read_xhs_data_drops_noise_columns(mock_lark_cli):
    mock_lark_cli.func.side_effect = [
        _table_list_resp([{"table_id": "tblA", "name": "笔记"}]),
        json.dumps({"data": {"has_more": False, "items": [
            {"record_id": "rec1", "fields": {"标题": "x", "封面": "img_url", "图片附件": "a.png", "正文": "body"}},
        ]}}),
    ]
    with patch.dict(os.environ, {"FEISHU_BITABLE_APP_TOKEN": "app_tok"}):
        res = read_xhs_data.func()
    fields = res["sync_rows"][0]["fields"]
    assert "标题" in fields and "正文" in fields
    # 噪声列被剔除
    assert "封面" not in fields and "图片附件" not in fields


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
