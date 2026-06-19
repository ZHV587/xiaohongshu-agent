import os
import json
from unittest.mock import patch

from tools.feishu_wiki import read_feishu_wiki


@patch("tools.lark_cli.lark_cli")
def test_read_feishu_wiki_missing_env(mock_lark_cli):
    # Test when FEISHU_WIKI_SPACE_ID is explicitly empty
    with patch.dict(os.environ, {"FEISHU_WIKI_SPACE_ID": ""}, clear=True):
        res = read_feishu_wiki.func()
        assert "error" in res
        assert "FEISHU_WIKI_SPACE_ID" in res["error"]
        assert res["source_errors"] == []


@patch("tools.lark_cli.lark_cli")
def test_read_feishu_wiki_success(mock_lark_cli):
    # Set mock environment variable
    with patch.dict(os.environ, {
        "FEISHU_WIKI_SPACE_ID": "mock_space_id"
    }):
        # Mock node list response
        mock_node_list_resp = {
            "data": {
                "items": [
                    {
                        "node_token": "wikcn1",
                        "obj_token": "docx1",
                        "obj_type": "docx",
                        "title": "露营核心装备"
                    },
                    {
                        "node_token": "wikcn2",
                        "obj_token": "sheet1",
                        "obj_type": "sheet",
                        "title": "预算明细表"
                    },
                    {
                        "node_token": "wikcn3",
                        "obj_token": "docx2",
                        "obj_type": "doc",
                        "title": "营地防坑指南"
                    }
                ]
            }
        }
        
        # Mock doc content response
        mock_doc1_resp = {
            "data": {
                "document": {
                    "content": "# 天幕推荐\n- 双顶天幕效果好。"
                }
            }
        }
        mock_doc2_resp = {
            "data": {
                "document": {
                    "content": "# 营地防坑\n- 检查草坪排水。"
                }
            }
        }

        # Mock the side effect for successive lark_cli calls
        mock_lark_cli.func.side_effect = [
            json.dumps(mock_node_list_resp),
            json.dumps(mock_doc1_resp),
            json.dumps(mock_doc2_resp)
        ]

        res = read_feishu_wiki.func()

        # Check results
        assert "error" not in res
        assert len(res["documents"]) == 2
        assert res["documents"][0]["title"] == "露营核心装备"
        assert res["documents"][0]["node_token"] == "wikcn1"
        assert res["documents"][0]["obj_token"] == "docx1"
        assert "双顶天幕" in res["documents"][0]["content"]
        assert res["wiki_space_id"] == "mock_space_id"
        assert res["documents"][1]["title"] == "营地防坑指南"
        assert res["documents"][1]["node_token"] == "wikcn3"
        assert res["documents"][1]["obj_token"] == "docx2"
        assert "检查草坪" in res["documents"][1]["content"]

        # Assert calls
        assert mock_lark_cli.func.call_count == 3
        # First call is node-list
        first_call = mock_lark_cli.func.call_args_list[0][0][0]
        assert "wiki +node-list" in first_call
        assert "--space-id mock_space_id" in first_call
        
        # Second call is fetching first doc
        second_call = mock_lark_cli.func.call_args_list[1][0][0]
        assert "docs +fetch" in second_call
        assert "--doc docx1" in second_call

        # Third call is fetching second doc
        third_call = mock_lark_cli.func.call_args_list[2][0][0]
        assert "docs +fetch" in third_call
        assert "--doc docx2" in third_call


@patch("tools.lark_cli.lark_cli")
def test_read_feishu_wiki_lark_cli_error(mock_lark_cli):
    with patch.dict(os.environ, {
        "FEISHU_WIKI_SPACE_ID": "mock_space_id"
    }):
        # Mock error string return from first call
        mock_lark_cli.func.return_value = "Error: Invalid permission"

        res = read_feishu_wiki.func()
        assert "error" in res
        assert "lark-cli" in res["error"]


@patch("tools.lark_cli.lark_cli")
def test_read_feishu_wiki_collects_document_fetch_errors(mock_lark_cli):
    mock_lark_cli.func.side_effect = [
        json.dumps({"data": {"items": [{
            "node_token": "wik_bad",
            "obj_token": "doc_bad",
            "obj_type": "docx",
            "title": "读取失败",
        }]}}),
        "Error: denied",
    ]
    with patch.dict(os.environ, {"FEISHU_WIKI_SPACE_ID": "mock_space_id"}):
        res = read_feishu_wiki.func()

    assert res["documents"] == []
    assert res["source_errors"] == ["wiki document doc_bad: Error: denied"]
