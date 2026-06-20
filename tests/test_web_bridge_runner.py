import argparse
import json
from unittest.mock import patch

from cryptography.fernet import Fernet

from tools import web_bridge_runner


def test_handle_uat_status_reports_authorized(capsys):
    args = argparse.Namespace(open_id="ou_123")

    with patch("tools.web_bridge_runner.get_uat", return_value="uat_token"):
        web_bridge_runner.handle_uat_status(args)

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": True, "authorized": True}


def test_config_status_reads_plain_center_for_admin_config_page(tmp_path, capsys):
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
    assert payload["version"]
    assert payload["configs"]["LLM_API_KEY"] == "sk-secret"
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
