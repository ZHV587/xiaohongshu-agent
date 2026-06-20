from __future__ import annotations

import pytest

from cryptography.fernet import Fernet

from data_foundation.config import (
    EmbeddingConfigError,
    embedding_snapshot,
    embedding_snapshot_for_version,
    runtime_embedding_snapshot,
)


def complete_embedding_values(**overrides: str) -> dict[str, str]:
    values = {
        "XHS_EMBEDDING_BASE_URL": "https://embedding.example/v1",
        "XHS_EMBEDDING_API_KEY": "embedding-key",
        "XHS_EMBEDDING_MODEL": "text-embedding-3-small",
        "XHS_EMBEDDING_DIMENSIONS": "1536",
        "XHS_EMBEDDING_BATCH_SIZE": "64",
        "XHS_EMBEDDING_TIMEOUT_SECONDS": "30",
    }
    values.update(overrides)
    return values


def test_embedding_snapshot_requires_independent_keys():
    with pytest.raises(EmbeddingConfigError, match="XHS_EMBEDDING_API_KEY"):
        embedding_snapshot({"LLM_API_KEY": "must-not-fallback"}, version="v1")


def test_embedding_snapshot_rejects_non_1536_dimensions():
    values = complete_embedding_values(XHS_EMBEDDING_DIMENSIONS="3072")

    snapshot = embedding_snapshot(values, version="v2")

    assert snapshot.state == "misconfigured"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("XHS_EMBEDDING_DIMENSIONS", "not-a-number"),
        ("XHS_EMBEDDING_BATCH_SIZE", "0"),
        ("XHS_EMBEDDING_TIMEOUT_SECONDS", "-1"),
    ],
)
def test_embedding_snapshot_rejects_invalid_numeric_values(key: str, value: str):
    snapshot = embedding_snapshot(complete_embedding_values(**{key: value}), version="v2")

    assert snapshot.state == "misconfigured"


def test_embedding_snapshot_disables_when_all_required_keys_are_empty():
    snapshot = embedding_snapshot({}, version="v3")

    assert snapshot.state == "disabled"
    assert snapshot.version == "v3"


def test_embedding_snapshot_enables_complete_profile():
    snapshot = embedding_snapshot(complete_embedding_values(), version="v4")

    assert snapshot.state == "enabled"
    assert snapshot.base_url == "https://embedding.example/v1"
    assert snapshot.api_key == "embedding-key"
    assert snapshot.model == "text-embedding-3-small"
    assert snapshot.dimensions == 1536
    assert snapshot.batch_size == 64
    assert snapshot.timeout_seconds == 30.0


def test_runtime_embedding_snapshot_bootstraps_config_center_and_keeps_history(monkeypatch, tmp_path):
    from config_center import ConfigCenter

    path = tmp_path / "config-center.enc"
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("XHS_CONFIG_CENTER_PATH", str(path))
    monkeypatch.setenv("XHS_CONFIG_ENCRYPTION_KEY", key)
    for name, value in complete_embedding_values().items():
        monkeypatch.setenv(name, value)

    first = runtime_embedding_snapshot()
    center = ConfigCenter(path=path, encryption_key=key)
    current = center.save(actor_open_id="ou_admin", updates={"XHS_EMBEDDING_MODEL": "model-b"})

    assert first.model == "text-embedding-3-small"
    assert first.version != current.version
    assert runtime_embedding_snapshot().model == "model-b"
    assert embedding_snapshot_for_version(first.version).model == "text-embedding-3-small"


def test_embedding_snapshot_for_version_rejects_unavailable_env_history(monkeypatch):
    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    for name, value in complete_embedding_values().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("XHS_EMBEDDING_CONFIG_VERSION", "env-v1")

    assert runtime_embedding_snapshot().version == "env-v1"
    assert embedding_snapshot_for_version("retired-v0") is None
