"""高质量模型自主调度系统:多网关资源池 + ModelRouterMiddleware。

设计见 docs/superpowers/specs/2026-06-18-model-layer-refactor-design.md。
铁律一:所有模型用 model_provider="openai" + 该网关 base_url/key 构造。
铁律二:ModelRouterMiddleware 同时实现 wrap_model_call 与 awrap_model_call。
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import httpx
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from middlewares import is_retryable_error

logger = logging.getLogger(__name__)


@dataclass
class ModelCandidate:
    """资源池中的一个候选:某网关下的一个高质量模型实例。"""
    gateway_name: str
    model_id: str
    model: BaseChatModel


# 进程内探测缓存:同 (base_url, key) 只探一次。
_DISCOVER_CACHE: dict[tuple[str, str], list[str] | None] = {}

_DISCOVER_TIMEOUT = 5.0


def discover_models(base_url: str, api_key: str) -> list[str] | None:
    """探测网关 GET /v1/models,返回裸 id 列表;失败或禁用返回 None。"""
    if os.environ.get("DISCOVER_MODELS") == "false":
        return None

    cache_key = (base_url, api_key)
    if cache_key in _DISCOVER_CACHE:
        return _DISCOVER_CACHE[cache_key]

    url = base_url.rstrip("/") + "/models"
    result: list[str] | None
    try:
        resp = httpx.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=_DISCOVER_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        result = [item["id"] for item in data.get("data", []) if "id" in item]
        if not result:
            logger.warning("discover_models: %s 返回空清单", url)
            result = None
    except Exception as exc:  # noqa: BLE001 — 探测失败一律降级,不致命
        logger.warning("discover_models 探测 %s 失败,降级: %s", url, exc)
        result = None

    _DISCOVER_CACHE[cache_key] = result
    return result
