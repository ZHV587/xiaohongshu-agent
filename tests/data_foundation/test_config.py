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


# --- retrieval-relevance-overhaul: 查询指令前缀与检索期策略读取器 ---

from data_foundation.config import (  # noqa: E402
    _model_aware_query_instruction,
    current_keyword_relevance_floor,
    current_query_instruction,
    current_relevance_floor,
    query_instruction_template_valid,
    resolve_query_instruction,
)
from data_foundation.search_ranker import (  # noqa: E402
    DEFAULT_KEYWORD_RELEVANCE_FLOOR,
    DEFAULT_RELEVANCE_FLOOR,
)


def test_model_aware_instruction_qwen3_gets_default_prefix():
    instr = _model_aware_query_instruction("Qwen/Qwen3-Embedding-4B", None)
    assert instr is not None
    assert "{query}" in instr


def test_model_aware_instruction_other_model_is_none():
    assert _model_aware_query_instruction("text-embedding-3-small", None) is None


def test_model_aware_instruction_explicit_overrides_default():
    explicit = "Instruct: x\nQuery: {query}"
    assert _model_aware_query_instruction("Qwen/Qwen3-Embedding-4B", explicit) == explicit


def test_model_aware_instruction_ignores_invalid_explicit():
    # 无 {query} 占位符的显式模板被忽略,回退到模型感知默认(Qwen3)
    instr = _model_aware_query_instruction("Qwen/Qwen3-Embedding-4B", "no placeholder")
    assert instr is not None and "{query}" in instr
    # 非 Qwen3 模型 + 非法显式 → None
    assert _model_aware_query_instruction("text-embedding-3-small", "no placeholder") is None


def test_query_instruction_template_valid():
    assert query_instruction_template_valid("a {query} b") is True
    assert query_instruction_template_valid("") is True   # 空=未配置,合法
    assert query_instruction_template_valid(None) is True
    assert query_instruction_template_valid("no placeholder") is False


def test_current_relevance_floor_env_default(monkeypatch):
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.delenv("XHS_EMBEDDING_RELEVANCE_FLOOR", raising=False)
    assert current_relevance_floor() == DEFAULT_RELEVANCE_FLOOR


def test_current_relevance_floor_env_override(monkeypatch):
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.setenv("XHS_EMBEDDING_RELEVANCE_FLOOR", "0.7")
    assert current_relevance_floor() == 0.7


def test_current_relevance_floor_invalid_falls_back(monkeypatch):
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    for bad in ("abc", "1.5", "-0.1"):
        monkeypatch.setenv("XHS_EMBEDDING_RELEVANCE_FLOOR", bad)
        assert current_relevance_floor() == DEFAULT_RELEVANCE_FLOOR


def test_current_keyword_relevance_floor_is_independently_configurable(monkeypatch):
    monkeypatch.delenv("XHS_KEYWORD_RELEVANCE_FLOOR", raising=False)
    assert current_keyword_relevance_floor() == DEFAULT_KEYWORD_RELEVANCE_FLOOR
    monkeypatch.setenv("XHS_KEYWORD_RELEVANCE_FLOOR", "0.25")
    assert current_keyword_relevance_floor() == 0.25
    for bad in ("bad", "-0.1", "1.1"):
        monkeypatch.setenv("XHS_KEYWORD_RELEVANCE_FLOOR", bad)
        assert current_keyword_relevance_floor() == DEFAULT_KEYWORD_RELEVANCE_FLOOR


def test_current_query_instruction_reads_env(monkeypatch):
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.setenv("XHS_EMBEDDING_QUERY_INSTRUCTION", "Instruct: y\nQuery: {query}")
    assert current_query_instruction() == "Instruct: y\nQuery: {query}"
    # 非法(无占位符)→ 视为未配置
    monkeypatch.setenv("XHS_EMBEDDING_QUERY_INSTRUCTION", "bad")
    assert current_query_instruction() is None


def test_resolve_query_instruction_uses_current_explicit_and_model(monkeypatch):
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    monkeypatch.setenv("XHS_EMBEDDING_QUERY_INSTRUCTION", "Instruct: z\nQuery: {query}")
    # 显式当前配置优先,即使模型非 Qwen3
    assert resolve_query_instruction("text-embedding-3-small") == "Instruct: z\nQuery: {query}"
