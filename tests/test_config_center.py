import pytest
from cryptography.fernet import Fernet

from config_center import (
    ConfigCenter,
    ConfigValidationError,
    bootstrap_snapshot_from_env,
)


def test_config_center_encrypts_secret_values(tmp_path):
    key = Fernet.generate_key().decode()
    path = tmp_path / "config-center.enc"
    center = ConfigCenter(path=path, encryption_key=key)

    saved = center.save(
        actor_open_id="ou_admin",
        updates={
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://gateway.example/v1",
            "LLM_API_KEY": "sk-secret",
            "LLM_QUALITY_MODELS": "gpt-4o,claude-sonnet-4-6",
        },
    )

    raw = path.read_bytes()
    assert b"sk-secret" not in raw
    assert saved.version
    assert center.get_plain()["LLM_API_KEY"] == "sk-secret"
    assert center.get_redacted()["LLM_API_KEY"] == "********"


def test_config_center_rejects_deploy_only_keys(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ConfigValidationError, match="XHS_JWT_SECRET"):
        center.save(actor_open_id="ou_admin", updates={"XHS_JWT_SECRET": "do-not-edit"})


def test_config_center_records_audit_history(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    first = center.save(actor_open_id="ou_admin", updates={"LLM_PROVIDER": "openai"})
    second = center.save(actor_open_id="ou_admin", updates={"LLM_QUALITY_MODELS": "gpt-4o"})

    history = center.history()
    assert [item.version for item in history] == [first.version, second.version]
    assert history[0].actor_open_id == "ou_admin"
    assert history[1].changed_keys == ["LLM_QUALITY_MODELS"]


def test_bootstrap_snapshot_from_env_imports_allowed_keys(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-bootstrap")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "gpt-4o")
    monkeypatch.setenv("XHS_JWT_SECRET", "not-imported")

    snapshot = bootstrap_snapshot_from_env(actor_open_id="system-bootstrap")

    assert snapshot.values["LLM_API_KEY"] == "sk-bootstrap"
    assert "XHS_JWT_SECRET" not in snapshot.values
