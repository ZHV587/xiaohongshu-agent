from __future__ import annotations

import pytest

from data_foundation.config import EmbeddingConfigError, embedding_snapshot


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
