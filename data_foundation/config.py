from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


EMBEDDING_REQUIRED_KEYS = (
    "XHS_EMBEDDING_BASE_URL",
    "XHS_EMBEDDING_API_KEY",
    "XHS_EMBEDDING_MODEL",
)


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
