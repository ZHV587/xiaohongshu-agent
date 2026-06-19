import os
import json
import pytest
from unittest.mock import patch, MagicMock
from tools.feishu_bitable import read_xhs_data


def test_read_xhs_data_missing_env():
    # Test when environment variables are missing
    with patch.dict(os.environ, {}, clear=True):
        res = read_xhs_data.func()
        assert "error" in res
        assert "FEISHU_BITABLE_APP_TOKEN" in res["error"]


def test_read_xhs_data_does_not_print_tokens(capsys):
    with patch.dict(os.environ, {
        "FEISHU_BITABLE_APP_TOKEN": "mock_app_token",
        "FEISHU_BITABLE_TABLE_ID": "mock_table_id",
    }):
        with patch("tools.lark_cli.lark_cli") as mock_lark_cli:
            mock_lark_cli.func.return_value = "Error: stop"
            read_xhs_data.func()

    captured = capsys.readouterr()
    assert "mock_app_token" not in captured.out
    assert "mock_table_id" not in captured.out


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_success(mock_lark_cli):
    # Set mock environment variables
    with patch.dict(os.environ, {
        "FEISHU_BITABLE_APP_TOKEN": "mock_app_token",
        "FEISHU_BITABLE_TABLE_ID": "mock_table_id"
    }):
        # Mock successful return from lark_cli using modern matrix structure
        mock_response = {
            "data": {
                "has_more": False,
                "fields": ["标题", "点赞", "噪声图片", "正文"],
                "data": [
                    ["如何露营", 120, "ignore_me", None],
                    ["装备指南", None, None, "正文内容"]
                ]
            }
        }
        mock_lark_cli.func.return_value = json.dumps(mock_response)

        res = read_xhs_data.func()

        # Check that it called lark_cli correctly
        mock_lark_cli.func.assert_called_once()
        args_str = mock_lark_cli.func.call_args[0][0]
        assert "base +record-list" in args_str
        assert "--base-token mock_app_token" in args_str
        assert "--table-id mock_table_id" in args_str

        # Check result
        assert "error" not in res
        # Columns filter logic: 标题 and 正文 are white-listed core keywords.
        assert "标题" in res["columns"]
        assert "正文" in res["columns"]
        assert "噪声图片" not in res["columns"]
        assert len(res["rows"]) == 2
        assert res["rows"][0]["标题"] == "如何露营"
        assert "噪声图片" not in res["rows"][0]


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_pagination(mock_lark_cli):
    with patch.dict(os.environ, {
        "FEISHU_BITABLE_APP_TOKEN": "mock_app_token",
        "FEISHU_BITABLE_TABLE_ID": "mock_table_id"
    }):
        # Mock two pages in modern matrix structure
        page1 = {
            "data": {
                "has_more": True,
                "fields": ["标题", "点赞"],
                "data": [
                    ["第一篇", 100]
                ]
            }
        }
        page2 = {
            "data": {
                "has_more": False,
                "fields": ["标题", "点赞"],
                "data": [
                    ["第二篇", 200]
                ]
            }
        }
        mock_lark_cli.func.side_effect = [json.dumps(page1), json.dumps(page2)]

        res = read_xhs_data.func()

        assert mock_lark_cli.func.call_count == 2
        
        # Verify first call args
        first_call_args = mock_lark_cli.func.call_args_list[0][0][0]
        assert "--offset 0" in first_call_args

        # Verify second call args carried the offset
        second_call_args = mock_lark_cli.func.call_args_list[1][0][0]
        assert "--offset 200" in second_call_args

        assert len(res["rows"]) == 2
        assert res["rows"][0]["标题"] == "第一篇"
        assert res["rows"][1]["标题"] == "第二篇"


@patch("tools.lark_cli.lark_cli")
def test_read_xhs_data_lark_cli_error(mock_lark_cli):
    with patch.dict(os.environ, {
        "FEISHU_BITABLE_APP_TOKEN": "mock_app_token",
        "FEISHU_BITABLE_TABLE_ID": "mock_table_id"
    }):
        # Mock error string return
        mock_lark_cli.func.return_value = "Error: Invalid permission"

        res = read_xhs_data.func()
        assert "error" in res
        assert "失败" in res["error"]
