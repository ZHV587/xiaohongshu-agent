from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Literal, Mapping

from data_foundation.search_ranker import (
    DEFAULT_KEYWORD_RELEVANCE_FLOOR,
    DEFAULT_RELEVANCE_FLOOR,
)


EMBEDDING_REQUIRED_KEYS = (
    "XHS_EMBEDDING_BASE_URL",
    "XHS_EMBEDDING_API_KEY",
    "XHS_EMBEDDING_MODEL",
)

EMBEDDING_CONFIG_KEYS = (
    *EMBEDDING_REQUIRED_KEYS,
    "XHS_EMBEDDING_DIMENSIONS",
    "XHS_EMBEDDING_BATCH_SIZE",
    "XHS_EMBEDDING_TIMEOUT_SECONDS",
    "XHS_EMBEDDING_QUERY_INSTRUCTION",
    "XHS_EMBEDDING_RELEVANCE_FLOOR",
)

# 绝对相关度下限默认值(单一定义点在 search_ranker;顶部 import 复用,避免漂移)。

# 模型感知查询指令默认模板(仅对 Qwen3 类非对称检索模型启用)。含 {query} 占位符。
_DEFAULT_QUERY_INSTRUCTION = (
    "Instruct: 给定一个内容创作检索查询,找出与之相关的小红书素材\nQuery: {query}"
)


def _is_asymmetric_model(model: str) -> bool:
    """是否为需要查询指令前缀的非对称检索模型(当前:Qwen3-Embedding 系列)。"""
    return "qwen3-embedding" in (model or "").lower()


def query_instruction_template_valid(template: str | None) -> bool:
    """显式指令模板必须含 {query} 占位符;空值视为"未配置"(合法)。"""
    if not template:
        return True
    return "{query}" in template


def _model_aware_query_instruction(model: str, explicit: str | None) -> str | None:
    """解析查询指令模板:显式配置优先(须含 {query},否则忽略);
    否则 Qwen3 类模型用默认模板;其他模型返回 None(裸文本,不硬套)。"""
    if explicit and query_instruction_template_valid(explicit):
        return explicit
    if _is_asymmetric_model(model):
        return _DEFAULT_QUERY_INSTRUCTION
    return None


def _current_embedding_values() -> dict[str, str]:
    """读取**当前生效**的 embedding 配置原始值(配置中心当前快照或 env),只读不 bootstrap。

    与 runtime_embedding_snapshot 的来源选择一致,但不触发空 history 时的 bootstrap 写盘,
    用于解析检索期策略(query_instruction / relevance_floor)——这两者取当前配置,
    不随 active index 的 config_version 历史回放。
    """
    center = _config_center()
    if center is None:
        return _embedding_values_from_environment()
    history = center.history()
    current = history[-1].values if history else {}
    return _embedding_values(current)


def current_query_instruction() -> str | None:
    """当前显式 XHS_EMBEDDING_QUERY_INSTRUCTION(无效模板视为未配置,返回 None)。"""
    explicit = _current_embedding_values().get("XHS_EMBEDDING_QUERY_INSTRUCTION", "").strip()
    if explicit and query_instruction_template_valid(explicit):
        return explicit
    return None


def resolve_query_instruction(model: str) -> str | None:
    """查询路径解析入口:模型名取 active index(判定 Qwen3),显式覆盖取当前配置。"""
    return _model_aware_query_instruction(model, current_query_instruction())


def current_relevance_floor() -> float:
    """当前 XHS_EMBEDDING_RELEVANCE_FLOOR;未配置或非法时回退 DEFAULT_RELEVANCE_FLOOR。"""
    raw = _current_embedding_values().get("XHS_EMBEDDING_RELEVANCE_FLOOR", "").strip()
    if not raw:
        return DEFAULT_RELEVANCE_FLOOR
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_RELEVANCE_FLOOR
    # 余弦相似度阈值的有效域 [0, 1];越界视为误配,回退默认。
    if not (0.0 <= value <= 1.0):
        return DEFAULT_RELEVANCE_FLOOR
    return value


def current_keyword_relevance_floor() -> float:
    """Meilisearch 原始相关度下限；防止低分 rank-1 被 RRF 人为抬高。"""

    raw = os.environ.get("XHS_KEYWORD_RELEVANCE_FLOOR", "").strip()
    if not raw:
        return DEFAULT_KEYWORD_RELEVANCE_FLOOR
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_KEYWORD_RELEVANCE_FLOOR
    if not (0.0 <= value <= 1.0):
        return DEFAULT_KEYWORD_RELEVANCE_FLOOR
    return value


class EmbeddingConfigError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingConfigSnapshot:
    version: str
    state: Literal["enabled", "disabled", "misconfigured"]
    base_url: str
    api_key: str
    model: str
    dimensions: int
    batch_size: int
    timeout_seconds: float


def embedding_snapshot(values: Mapping[str, str], *, version: str) -> EmbeddingConfigSnapshot:
    normalized = {key: str(value or "").strip() for key, value in values.items()}
    missing = [key for key in EMBEDDING_REQUIRED_KEYS if not normalized.get(key)]
    has_embedding_keys = any(key.startswith("XHS_EMBEDDING_") for key in normalized)
    if missing and normalized and not has_embedding_keys:
        raise EmbeddingConfigError("Missing embedding config key: XHS_EMBEDDING_API_KEY")

    base_url = normalized.get("XHS_EMBEDDING_BASE_URL", "")
    api_key = normalized.get("XHS_EMBEDDING_API_KEY", "")
    model = normalized.get("XHS_EMBEDDING_MODEL", "")
    dimensions = _parse_int(normalized.get("XHS_EMBEDDING_DIMENSIONS", "1536"), default=1536)
    batch_size = _parse_int(normalized.get("XHS_EMBEDDING_BATCH_SIZE", "64"), default=64)
    timeout_seconds = _parse_float(normalized.get("XHS_EMBEDDING_TIMEOUT_SECONDS", "30"), default=30.0)

    state: Literal["enabled", "disabled", "misconfigured"]
    if missing:
        state = "disabled"
    elif dimensions != 1536 or dimensions <= 0 or batch_size <= 0 or timeout_seconds <= 0:
        state = "misconfigured"
    else:
        state = "enabled"

    return EmbeddingConfigSnapshot(
        version=version,
        state=state,
        base_url=base_url,
        api_key=api_key,
        model=model,
        dimensions=dimensions,
        batch_size=batch_size,
        timeout_seconds=timeout_seconds,
    )


def runtime_embedding_snapshot() -> EmbeddingConfigSnapshot:
    center = _config_center()
    if center is None:
        return embedding_snapshot(
            _embedding_values_from_environment(),
            version=os.environ.get("XHS_EMBEDDING_CONFIG_VERSION", "env").strip() or "env",
        )

    history = center.history()
    if not history:
        from config_center import bootstrap_snapshot_from_env

        bootstrap = bootstrap_snapshot_from_env(actor_open_id="system-bootstrap")
        current = center.save(actor_open_id=bootstrap.actor_open_id, updates=bootstrap.values)
    else:
        current = history[-1]
    return embedding_snapshot(_embedding_values(current.values), version=current.version)


def embedding_snapshot_for_version(version: str) -> EmbeddingConfigSnapshot | None:
    center = _config_center()
    if center is not None:
        try:
            snapshot = center.get_version(version)
        except KeyError:
            return None
        return embedding_snapshot(_embedding_values(snapshot.values), version=snapshot.version)

    current = runtime_embedding_snapshot()
    return current if current.version == version else None


def _config_center():
    if not (
        os.environ.get("XHS_CONFIG_ENCRYPTION_KEY")
        and os.environ.get("XHS_CONFIG_CENTER_PATH")
    ):
        return None
    from config_center import default_config_center

    return default_config_center()


def _embedding_values(values: Mapping[str, str]) -> dict[str, str]:
    return {key: str(values.get(key, "")) for key in EMBEDDING_CONFIG_KEYS}


def _embedding_values_from_environment() -> dict[str, str]:
    return {key: os.environ.get(key, "") for key in EMBEDDING_CONFIG_KEYS}


def _parse_int(value: str, *, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return -1


def _parse_float(value: str, *, default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return -1.0
