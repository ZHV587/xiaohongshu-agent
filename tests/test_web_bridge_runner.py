import argparse
import json
import os
from unittest.mock import patch

from cryptography.fernet import Fernet

from tools import web_bridge_runner


def test_handle_uat_status_reports_authorized(capsys):
    args = argparse.Namespace(open_id="ou_123")

    with patch("tools.web_bridge_runner.get_uat", return_value="uat_token"):
        web_bridge_runner.handle_uat_status(args)

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": True, "authorized": True}


def test_handle_sync_creates_draft_record(capsys):
    args = argparse.Namespace(
        open_id="ou_123",
        title="标题",
        content="正文",
        tags="#露营,#户外",
        thread_id="thread_123",
    )

    with patch.dict(
        os.environ,
        {
            "FEISHU_BITABLE_APP_TOKEN": "base_token",
            "FEISHU_BITABLE_TABLE_ID": "tbl_id",
        },
    ):
        with patch("tools.web_bridge_runner.get_uat", return_value="uat_token"):
            with patch("tools.web_bridge_runner.lark_cli") as mock_lark_cli:
                mock_lark_cli.return_value = json.dumps(
                    {"data": {"record": {"record_id": "rec_new"}}}
                )

                web_bridge_runner.handle_sync(args)

    command = mock_lark_cli.call_args.args[0]
    assert "+record-create" in command
    assert "+record-batch-update" not in command
    assert '"状态": "草稿"' in command
    assert '"标签": "#露营,#户外"' in command

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "ok": True,
        "record_id": "rec_new",
        "redirect_url": "https://feishu.cn/base/base_token?table=tbl_id",
    }


def test_config_status_reads_redacted_center(tmp_path, capsys):
    from config_center import ConfigCenter

    key = Fernet.generate_key().decode()
    path = tmp_path / "config.enc"
    center = ConfigCenter(path=path, encryption_key=key)
    center.save(actor_open_id="ou_admin", updates={
        "LLM_PROVIDER": "openai",
        "LLM_API_KEY": "sk-secret",
        "LLM_QUALITY_MODELS": "gpt-4o",
    })

    args = argparse.Namespace(config_path=str(path), encryption_key=key)
    web_bridge_runner.handle_config_status(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["configs"]["LLM_API_KEY"] == "********"
    assert payload["configs"]["LLM_QUALITY_MODELS"] == "gpt-4o"


def test_config_set_writes_encrypted_center(tmp_path, capsys):
    from config_center import ConfigCenter

    key = Fernet.generate_key().decode()
    path = tmp_path / "config.enc"
    args = argparse.Namespace(
        config_path=str(path),
        encryption_key=key,
        open_id="ou_admin",
        configs=json.dumps({
            "LLM_PROVIDER": "openai",
            "LLM_API_KEY": "sk-secret",
            "LLM_QUALITY_MODELS": "gpt-4o",
        }),
    )

    web_bridge_runner.handle_config_set(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["version"]
    assert payload["changed_keys"] == ["LLM_API_KEY", "LLM_PROVIDER", "LLM_QUALITY_MODELS"]
    assert b"sk-secret" not in path.read_bytes()
    assert ConfigCenter(path=path, encryption_key=key).get_plain()["LLM_API_KEY"] == "sk-secret"
