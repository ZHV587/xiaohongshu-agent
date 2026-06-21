"""高质量模型自主调度系统:多网关资源池 + ModelRouterMiddleware。

设计见 docs/superpowers/specs/2026-06-18-model-layer-refactor-design.md。
铁律一:所有模型用 model_provider="openai" + 该网关 base_url/key 构造。
铁律二:ModelRouterMiddleware 同时实现 wrap_model_call 与 awrap_model_call。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import httpx
from langchain.agents.middleware import AgentMiddleware, ModelRequest
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


class ModelPoolProvider(Protocol):
    def get_pool(self) -> list[ModelCandidate]:
        raise NotImplementedError


class StaticModelPoolProvider:
    """把启动时构造的静态候选池显式暴露成 provider。"""

    def __init__(self, pool: list[ModelCandidate]) -> None:
        self._pool = pool

    def get_pool(self) -> list[ModelCandidate]:
        return list(self._pool)


# 进程内探测缓存:同 (base_url, key) 在 TTL 内复用,过期重探。
# 值为 (探测时刻 monotonic, 结果)。定时健康探测周期 300s,TTL 取略小的 250s,
# 保证每个探测周期都拿到新鲜结果(网关增减模型能在一个周期内被感知)。
_DISCOVER_CACHE: dict[tuple[str, str], tuple[float, list[str] | None]] = {}

_DISCOVER_TIMEOUT = 5.0
_DISCOVER_TTL = 250.0


def discover_models(base_url: str, api_key: str, *, force: bool = False) -> list[str] | None:
    """探测网关 GET /v1/models,返回裸 id 列表;失败或禁用返回 None。

    force=True 跳过缓存强制重探(定时健康探测、配置保存 verify 用),
    并把新鲜结果写回缓存。普通构池调用走 TTL 缓存,减负载。
    """
    if os.environ.get("DISCOVER_MODELS") == "false":
        return None

    cache_key = (base_url, api_key)
    if not force:
        cached = _DISCOVER_CACHE.get(cache_key)
        if cached is not None and (time.monotonic() - cached[0]) < _DISCOVER_TTL:
            return cached[1]

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

    _DISCOVER_CACHE[cache_key] = (time.monotonic(), result)
    return result


def _build_chat_model(model_id: str, base_url: str, api_key: str) -> BaseChatModel:
    """按铁律一构造模型实例:provider=openai + 网关 base_url/key。"""
    provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model_id,
            api_key=api_key,
            temperature=0.7,
            timeout=60,
            max_retries=2,
        )
    elif provider == "google_genai":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=model_id,
            api_key=api_key,
            temperature=0.7,
            timeout=60,
            max_retries=2,
        )
    else:
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


class LazyPool(list):
    """线程安全的延迟加载模型候选池。
    在模块导入时不触发任何网络请求，只有在首次使用（如迭代、取值或算长度）时才开始网络探测。
    """
    def __init__(self) -> None:
        super().__init__()
        self._loaded = False
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        with self._lock:
            if not self._loaded:
                pool = _actual_build_pool()
                self.extend(pool)
                self._loaded = True

    def __iter__(self):
        self._ensure_loaded()
        return super().__iter__()

    def __len__(self) -> int:
        self._ensure_loaded()
        return super().__len__()

    def __getitem__(self, index):
        self._ensure_loaded()
        return super().__getitem__(index)

    def __bool__(self) -> bool:
        self._ensure_loaded()
        return len(self) > 0


def _actual_build_pool() -> list[ModelCandidate]:
    """真正构造高质量候选池:各网关清单 ∩ 白名单;池为空则降级到白名单首个。"""
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


def build_pool() -> list[ModelCandidate]:
    """构造高质量候选池（延迟加载包装）。"""
    return LazyPool()


_COOLDOWN_SECONDS = 30.0


class ModelRouterMiddleware(AgentMiddleware):
    """严格质量优先的运行时调度:总是用池里最强(白名单序靠前)且健康的模型,
    它冷却/失败才降级到次强,恢复后立刻切回。

    健康度为 best-effort 无锁状态:_health 存 (网关名,模型id)→冷却到期时间。
    池来自 pool_provider(通常包 ModelRegistry),每次调用实时读最新池,
    故定时探测/配置热重载替换 registry 池后,本中间件下次调用即生效。
    """

    def __init__(self, pool_provider: ModelPoolProvider) -> None:
        super().__init__()
        self._pool_provider = pool_provider
        self._health: dict[tuple[str, str], float] = {}  # (gateway_name, model_id) -> 冷却到期

    def _current_pool(self) -> list[ModelCandidate]:
        return self._pool_provider.get_pool()

    def _is_cooling(self, candidate: ModelCandidate) -> bool:
        until = self._health.get((candidate.gateway_name, candidate.model_id))
        return until is not None and time.monotonic() < until

    def _mark_unhealthy(self, candidate: ModelCandidate) -> None:
        self._health[(candidate.gateway_name, candidate.model_id)] = time.monotonic() + _COOLDOWN_SECONDS

    def _ordered_candidates(self) -> list[ModelCandidate]:
        """严格质量优先:池按白名单序(强→弱)排列,本方法不打乱顺序。

        健康候选按质量序在前(永远先试最强健康的那个),冷却中的按质量序垫后
        (全冷却时仍按强→弱尝试,作自愈窗口)。区别于负载均衡的轮询——这里
        不轮转、不均摊,总是优先最强可用模型,只有它冷却/失败才降级到次强。
        """
        pool = self._current_pool()
        if not pool:
            return []  # 池空由调用方(wrap/awrap)回退到 request 装配占位 model
        healthy = [c for c in pool if not self._is_cooling(c)]
        cooling = [c for c in pool if self._is_cooling(c)]
        return healthy + cooling

    def wrap_model_call(self, request: ModelRequest, handler):
        candidates = self._ordered_candidates()
        if not candidates:
            # 池为空:registry 尚未被 lifespan/探测/事件填充(server 接客前不会命中),
            # 或测试/CLI 态。回退到 request 自带的装配占位 model,不阻断调用。
            return handler(request)
        last_exc: Exception | None = None
        for cand in candidates:
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
        candidates = self._ordered_candidates()
        if not candidates:
            return await handler(request)
        last_exc: Exception | None = None
        for cand in candidates:
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


def build_primary_model(pool: list[ModelCandidate]) -> BaseChatModel:
    """静态构造初始模型实例，以避免在模块导入阶段触发 LazyPool 加载和网络请求。"""
    if isinstance(pool, LazyPool) and not pool._loaded:
        gateways = _read_gateways()
        whitelist = _read_whitelist()
        if not gateways or not whitelist:
            raise RuntimeError(
                "无法构造初始模型:LLM_BASE_URL/LLM_API_KEY/LLM_QUALITY_MODELS 至少一项缺失"
            )
        gw_name, base_url, api_key = gateways[0]
        fallback_id = whitelist[0]
        return _build_chat_model(fallback_id, base_url, api_key)

    if pool:
        return pool[0].model
    raise ValueError("候选池为空，无法构建初始模型")


def build_static_model_provider(pool: list[ModelCandidate]) -> StaticModelPoolProvider:
    return StaticModelPoolProvider(pool)


def build_router_middleware(pool_provider: ModelPoolProvider) -> ModelRouterMiddleware:
    """构造调度中间件(主/子/评分各取一个,共用同一池)。"""
    return ModelRouterMiddleware(pool_provider)


def build_pool_from_config(values: dict[str, str], *, force_discover: bool = False) -> list[ModelCandidate]:
    """从配置中心快照构造模型候选池，不依赖进程 env 作为权威源。

    池按白名单(LLM_QUALITY_MODELS)顺序构建 —— 白名单序即质量优先序。
    只收"网关探测确认存在 ∩ 在白名单"的模型,绝不塞未探测确认的模型。
    force_discover=True 强制重探(定时健康探测、配置 verify 用)。
    全挂(无任一可用)时 raise RuntimeError,由调用方决定处理(保留旧池/记错)。
    """
    gateways: list[tuple[str, str, str]] = []
    base = values.get("LLM_BASE_URL", "").strip()
    key = values.get("LLM_API_KEY", "").strip()
    if base and key:
        gateways.append(("gateway_1", base, key))
    for n in (2, 3):
        b = values.get(f"LLM_GATEWAY_{n}_BASE_URL", "").strip()
        k = values.get(f"LLM_GATEWAY_{n}_API_KEY", "").strip()
        if b and k:
            gateways.append((f"gateway_{n}", b, k))

    whitelist = [m.strip() for m in values.get("LLM_QUALITY_MODELS", "").split(",") if m.strip()]
    pool: list[ModelCandidate] = []

    old_provider = os.environ.get("LLM_PROVIDER")
    if values.get("LLM_PROVIDER"):
        os.environ["LLM_PROVIDER"] = values["LLM_PROVIDER"]
    try:
        # 先探测每个网关的可用清单(一次),再按白名单序匹配,保证质量优先序。
        gateway_available = {
            gw_name: set(discover_models(base_url, api_key, force=force_discover) or [])
            for gw_name, base_url, api_key in gateways
        }
        for model_id in whitelist:  # 白名单序 = 质量序
            for gw_name, base_url, api_key in gateways:
                if model_id in gateway_available[gw_name]:
                    pool.append(ModelCandidate(
                        gateway_name=gw_name,
                        model_id=model_id,
                        model=_build_chat_model(model_id, base_url, api_key),
                    ))
    finally:
        if old_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = old_provider

    if not pool:
        raise RuntimeError("无法从配置中心构造模型池:白名单内无任一模型被网关探测确认可用")
    return pool


def verify_gateway(base_url: str, api_key: str) -> bool:
    """配置时连通性验证:能探到非空清单即视为'配上能用'。

    委托 discover_models;能返回非空清单为 True。供配置写入路径调用。
    force=True:admin 刚改的网关配置必须新鲜探测,不命中旧缓存。
    """
    return bool(discover_models(base_url, api_key, force=True))
