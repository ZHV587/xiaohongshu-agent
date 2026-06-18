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


def _build_chat_model(model_id: str, base_url: str, api_key: str) -> BaseChatModel:
    """按铁律一构造模型实例:provider=openai + 网关 base_url/key。"""
    return init_chat_model(
        model=model_id,
        model_provider="openai",
        base_url=base_url,
        api_key=api_key,
        temperature=0.7,
        timeout=60,
        max_retries=2,
    )


def _read_gateways() -> list[tuple[str, str, str]]:
    """读 env 得到 [(gateway_name, base_url, api_key)]。主网关 + 编号附加网关。"""
    gateways: list[tuple[str, str, str]] = []
    base = os.environ.get("LLM_BASE_URL", "").strip()
    key = os.environ.get("LLM_API_KEY", "").strip()
    if base and key:
        gateways.append(("gateway_1", base, key))
    n = 2
    while True:
        b = os.environ.get(f"LLM_GATEWAY_{n}_BASE_URL", "").strip()
        k = os.environ.get(f"LLM_GATEWAY_{n}_API_KEY", "").strip()
        if not (b and k):
            break
        gateways.append((f"gateway_{n}", b, k))
        n += 1
    return gateways


def _read_whitelist() -> list[str]:
    """读 LLM_QUALITY_MODELS env,返回去空白过滤后的模型 id 列表;未设置返回 []。"""
    raw = os.environ.get("LLM_QUALITY_MODELS", "")
    return [m.strip() for m in raw.split(",") if m.strip()]


def build_pool() -> list[ModelCandidate]:
    """构造高质量候选池:各网关清单 ∩ 白名单;池为空则降级到白名单首个。"""
    gateways = _read_gateways()
    whitelist = _read_whitelist()
    whitelist_set = set(whitelist)

    pool: list[ModelCandidate] = []
    for gw_name, base_url, api_key in gateways:
        available = discover_models(base_url, api_key)
        if not available:
            continue
        for model_id in available:
            if model_id in whitelist_set:
                pool.append(ModelCandidate(
                    gateway_name=gw_name,
                    model_id=model_id,
                    model=_build_chat_model(model_id, base_url, api_key),
                ))

    if not pool:
        if not gateways or not whitelist:
            raise RuntimeError(
                "无法构造模型池:LLM_BASE_URL/LLM_API_KEY/LLM_QUALITY_MODELS 至少一项缺失"
            )
        gw_name, base_url, api_key = gateways[0]
        fallback_id = whitelist[0]
        logger.warning(
            "模型池为空(探测失败或白名单无交集),降级到白名单首个 %s @ %s",
            fallback_id, base_url,
        )
        pool.append(ModelCandidate(
            gateway_name=gw_name,
            model_id=fallback_id,
            model=_build_chat_model(fallback_id, base_url, api_key),
        ))

    return pool


_COOLDOWN_SECONDS = 30.0


class ModelRouterMiddleware(AgentMiddleware):
    """质量优先的运行时调度:从健康候选轮转选模型,失败切同档下一个。

    健康度为 best-effort 无锁状态(spec §6):_health 存网关名→冷却到期时间。
    """

    def __init__(self, pool: list[ModelCandidate]) -> None:
        super().__init__()
        if not pool:
            raise ValueError("ModelRouterMiddleware 需要非空候选池")
        self._pool = pool
        self._health: dict[str, float] = {}  # gateway_name -> 冷却到期(monotonic)
        self._rr = 0  # 轮询游标

    def _is_cooling(self, gateway_name: str) -> bool:
        until = self._health.get(gateway_name)
        return until is not None and time.monotonic() < until

    def _mark_unhealthy(self, candidate: ModelCandidate) -> None:
        self._health[candidate.gateway_name] = time.monotonic() + _COOLDOWN_SECONDS

    def _ordered_candidates(self) -> list[ModelCandidate]:
        """轮询起点 + 健康优先:先健康候选(从轮询游标起),冷却中的垫后(兜底)。"""
        n = len(self._pool)
        rotated = [self._pool[(self._rr + i) % n] for i in range(n)]
        self._rr = (self._rr + 1) % n
        healthy = [c for c in rotated if not self._is_cooling(c.gateway_name)]
        cooling = [c for c in rotated if self._is_cooling(c.gateway_name)]
        return healthy + cooling  # 全冷却时仍尝试(自愈窗口)

    def wrap_model_call(self, request: ModelRequest, handler):
        last_exc: Exception | None = None
        for cand in self._ordered_candidates():
            try:
                return handler(request.override(model=cand.model))
            except Exception as exc:  # noqa: BLE001
                if is_retryable_error(exc):
                    self._mark_unhealthy(cand)
                    last_exc = exc
                    continue
                raise  # 非瞬时错误(400/鉴权)不换候选
        assert last_exc is not None
        raise last_exc

    async def awrap_model_call(self, request: ModelRequest, handler):
        last_exc: Exception | None = None
        for cand in self._ordered_candidates():
            try:
                return await handler(request.override(model=cand.model))
            except Exception as exc:  # noqa: BLE001
                if is_retryable_error(exc):
                    self._mark_unhealthy(cand)
                    last_exc = exc
                    continue
                raise  # 非瞬时错误(400/鉴权)不换候选
        assert last_exc is not None
        raise last_exc
