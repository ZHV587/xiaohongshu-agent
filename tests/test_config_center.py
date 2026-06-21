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


def test_config_center_rejects_internal_base_url(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ConfigValidationError, match="XHS_INTERNAL_BASE_URL"):
        center.save(actor_open_id="ou_admin", updates={"XHS_INTERNAL_BASE_URL": "http://127.0.0.1:2024"})


def test_config_center_records_audit_history(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    first = center.save(actor_open_id="ou_admin", updates={"LLM_PROVIDER": "openai"})
    second = center.save(actor_open_id="ou_admin", updates={"LLM_QUALITY_MODELS": "gpt-4o"})

    history = center.history()
    assert [item.version for item in history] == [first.version, second.version]
    assert history[0].actor_open_id == "ou_admin"
    assert history[1].changed_keys == ["LLM_QUALITY_MODELS"]


def test_config_center_gets_historical_profile(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    first = center.save(
        actor_open_id="ou_admin",
        updates={
            "XHS_EMBEDDING_BASE_URL": "https://embedding.example/v1",
            "XHS_EMBEDDING_API_KEY": "embedding-key",
            "XHS_EMBEDDING_MODEL": "model-a",
            "XHS_EMBEDDING_DIMENSIONS": "1536",
            "XHS_EMBEDDING_BATCH_SIZE": "64",
            "XHS_EMBEDDING_TIMEOUT_SECONDS": "30",
        },
    )
    center.save(actor_open_id="ou_admin", updates={"XHS_EMBEDDING_MODEL": "model-b"})

    assert center.get_version(first.version).values["XHS_EMBEDDING_MODEL"] == "model-a"
    with pytest.raises(KeyError):
        center.get_version("missing-version")


def test_config_center_redacts_embedding_api_key(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    center.save(
        actor_open_id="ou_admin",
        updates={
            "XHS_EMBEDDING_BASE_URL": "https://embedding.example/v1",
            "XHS_EMBEDDING_API_KEY": "embedding-secret",
            "XHS_EMBEDDING_MODEL": "text-embedding-3-small",
        },
    )

    redacted = center.get_redacted()

    assert redacted["XHS_EMBEDDING_API_KEY"] == "********"
    assert redacted["XHS_EMBEDDING_BASE_URL"] == "https://embedding.example/v1"


def test_bootstrap_snapshot_from_env_imports_allowed_keys(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-bootstrap")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "gpt-4o")
    monkeypatch.setenv("XHS_JWT_SECRET", "not-imported")

    snapshot = bootstrap_snapshot_from_env(actor_open_id="system-bootstrap")

    assert snapshot.values["LLM_API_KEY"] == "sk-bootstrap"
    assert "XHS_JWT_SECRET" not in snapshot.values


def test_engine_keys_are_deploy_only():
    from config_center import DEPLOY_ONLY_KEYS, SECRET_KEYS
    assert "XHS_MEILI_URL" in DEPLOY_ONLY_KEYS
    assert "XHS_MEILI_KEY" in DEPLOY_ONLY_KEYS
    assert "XHS_FALKOR_URL" in DEPLOY_ONLY_KEYS
    assert "XHS_FALKOR_GRAPH" in DEPLOY_ONLY_KEYS
    assert "XHS_MEILI_KEY" in SECRET_KEYS
