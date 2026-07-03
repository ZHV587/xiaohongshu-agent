import json
from unittest.mock import patch

from tools.runtime_identity import identity_config


def test_sync_copy_to_feishu_requires_content():
    from tools.feishu_actions import sync_copy_to_feishu

    result = sync_copy_to_feishu.func(title="", content="", config=identity_config("ou_user"))

    assert result["ok"] is False
    assert "title and content are required" in result["error"]


def test_sync_copy_to_feishu_requires_base_configuration(monkeypatch):
    from tools.feishu_actions import sync_copy_to_feishu

    monkeypatch.delenv("FEISHU_BITABLE_APP_TOKEN", raising=False)
    monkeypatch.delenv("FEISHU_BITABLE_TABLE_ID", raising=False)

    result = sync_copy_to_feishu.func(title="标题", content="正文", config=identity_config("ou_user"))

    assert result == {
        "ok": False,
        "error": "FEISHU_BITABLE_APP_TOKEN and FEISHU_BITABLE_TABLE_ID are required",
    }


@patch("tools.feishu_actions.lark_cli")
def test_sync_copy_to_feishu_calls_lark_cli(mock_lark_cli, monkeypatch):
    from tools.feishu_actions import sync_copy_to_feishu

    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl_id")
    mock_lark_cli.func.return_value = json.dumps(
        {"code": 0, "data": {"record": {"record_id": "rec_1"}}},
        ensure_ascii=False,
    )

    result = sync_copy_to_feishu.func(
        title="标题",
        content="正文",
        tags="标签1,标签2",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert result["record_id"] == "rec_1"
    called_command = mock_lark_cli.func.call_args.args[0]
    assert "base +record-upsert" in called_command
    assert "--base-token base_token" in called_command
    assert "--table-id tbl_id" in called_command
    assert mock_lark_cli.func.call_args.kwargs["config"] == identity_config("ou_user")


@patch("tools.feishu_actions.lark_cli")
def test_sync_copy_to_feishu_returns_lark_json_error(mock_lark_cli, monkeypatch):
    from tools.feishu_actions import sync_copy_to_feishu

    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl_id")
    mock_lark_cli.func.return_value = json.dumps({"code": 999, "msg": "permission denied"})

    result = sync_copy_to_feishu.func(title="标题", content="正文", config=identity_config("ou_user"))

    assert result == {"ok": False, "error": "permission denied"}


@patch("tools.feishu_actions.lark_cli")
def test_sync_copy_to_feishu_returns_invalid_lark_json_error(mock_lark_cli, monkeypatch):
    from tools.feishu_actions import sync_copy_to_feishu

    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl_id")
    mock_lark_cli.func.return_value = "not json"

    result = sync_copy_to_feishu.func(title="标题", content="正文", config=identity_config("ou_user"))

    assert result == {"ok": False, "error": "Lark CLI returned invalid JSON", "raw": "not json"}


@patch("tools.feishu_actions.lark_cli")
def test_send_review_notification_calls_lark_cli(mock_lark_cli):
    from tools.feishu_actions import send_review_notification

    mock_lark_cli.func.return_value = json.dumps({"code": 0}, ensure_ascii=False)

    result = send_review_notification.func(
        chat_id="oc_chat",
        title="标题",
        content="正文",
        config=identity_config("ou_user"),
    )

    assert result == {"ok": True}
    called_command = mock_lark_cli.func.call_args.args[0]
    assert "im +messages-send" in called_command
    assert "--chat-id oc_chat" in called_command
    assert "--msg-type interactive" in called_command
    assert mock_lark_cli.func.call_args.kwargs["config"] == identity_config("ou_user")


@patch("tools.feishu_actions.lark_cli")
def test_send_review_notification_returns_lark_json_error(mock_lark_cli):
    from tools.feishu_actions import send_review_notification

    mock_lark_cli.func.return_value = json.dumps({"code": 999, "message": "chat not found"})

    result = send_review_notification.func(
        chat_id="oc_chat",
        title="标题",
        content="正文",
        config=identity_config("ou_user"),
    )

    assert result == {"ok": False, "error": "chat not found"}


@patch("tools.feishu_actions.lark_cli")
def test_sync_topic_to_feishu_calls_lark_cli(mock_lark_cli, monkeypatch):
    from tools.feishu_actions import sync_topic_to_feishu

    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_BITABLE_TOPIC_TABLE_ID", "tbl_topic")
    mock_lark_cli.func.return_value = json.dumps(
        {"code": 0, "data": {"record": {"record_id": "rec_topic"}}},
        ensure_ascii=False,
    )

    result = sync_topic_to_feishu.func(
        direction="露营装备",
        topics=["装备挑选指南", "户外睡袋推荐"],
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert len(result["record_ids"]) == 2
    assert result["record_ids"][0] == "rec_topic"
    assert "table=tbl_topic" in result["redirect_url"]


@patch("tools.feishu_actions.lark_cli")
def test_sync_diagnosis_to_feishu_calls_lark_cli(mock_lark_cli, monkeypatch):
    from tools.feishu_actions import sync_diagnosis_to_feishu

    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl_diag")
    # mock list_base_tables to return empty to fallback to FEISHU_BITABLE_TABLE_ID
    with patch("tools.feishu_bitable.list_base_tables") as mock_list:
        mock_list.return_value = ([], None)
        mock_lark_cli.func.return_value = json.dumps(
            {"code": 0, "data": {"record": {"record_id": "rec_diag"}}},
            ensure_ascii=False,
        )

        result = sync_diagnosis_to_feishu.func(
            project_name="新项目",
            title="商业变现诊断",
            content="这是一份商业模式诊断...",
            config=identity_config("ou_user"),
        )

        assert result["ok"] is True
        assert result["record_id"] == "rec_diag"
        assert "table=tbl_diag" in result["redirect_url"]



@patch("tools.feishu_actions.lark_cli")
def test_create_online_note_record_maps_columns_to_collect_table(mock_lark_cli, monkeypatch):
    from tools.feishu_actions import create_online_note_record

    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base_token")
    monkeypatch.delenv("FEISHU_BITABLE_COLLECT_TABLE_ID", raising=False)  # 用默认 tbl24vSVeLvz45ig
    mock_lark_cli.func.return_value = json.dumps(
        {"code": 0, "data": {"record": {"record_id": "rec_x"}}}, ensure_ascii=False
    )
    note = {
        "title": "秋冬护肤", "summary": "摘要", "author": "护肤老师",
        "cover_url": "http://cdn/a.jpg", "note_url": "http://xhslink.com/o/abc",
        "tags": ["护肤", "秋冬"], "created_at": "2026-06-20",
        "likes": 3000, "collects": 1500, "comments": 300, "shares": 200,
    }
    result = create_online_note_record(note, config=identity_config("ou_user"))
    assert result["ok"] is True
    assert result["record_id"] == "rec_x"
    assert result["table_id"] == "tbl24vSVeLvz45ig"  # 默认采集库,非草稿表
    # 校验下发到 lark-cli 的列映射
    sent = mock_lark_cli.func.call_args[0][0]
    assert "--table-id tbl24vSVeLvz45ig" in sent
    payload = json.loads(sent.split("--json ", 1)[1].strip().strip("'"))
    assert payload["标题"] == "秋冬护肤"
    assert payload["封面链接"] == "http://cdn/a.jpg"
    assert payload["原文链接"] == "http://xhslink.com/o/abc"
    assert payload["点赞数"] == 3000 and payload["收藏数"] == 1500
    assert payload["采集平台"] == "线上实时"
    assert "#护肤" in payload["话题标签"]


def test_create_online_note_record_requires_app_token(monkeypatch):
    from tools.feishu_actions import create_online_note_record

    monkeypatch.delenv("FEISHU_BITABLE_APP_TOKEN", raising=False)
    result = create_online_note_record({"title": "x"}, config=identity_config("ou_user"))
    assert result["ok"] is False
    assert "FEISHU_BITABLE_APP_TOKEN" in result["error"]
