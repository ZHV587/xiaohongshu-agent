import httpx
from middlewares import is_retryable_error


class FakeStatusError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


def test_is_retryable_error_on_503():
    assert is_retryable_error(FakeStatusError(503)) is True


def test_is_retryable_error_on_429():
    assert is_retryable_error(FakeStatusError(429)) is True


def test_is_retryable_error_on_400_is_false():
    assert is_retryable_error(FakeStatusError(400)) is False


def test_is_retryable_error_on_httpx_transport():
    assert is_retryable_error(httpx.ConnectError("boom")) is True


def test_is_retryable_error_on_value_error_is_false():
    assert is_retryable_error(ValueError("nope")) is False


from models import ModelCandidate


def test_model_candidate_holds_fields():
    sentinel = object()  # 占位模型实例
    c = ModelCandidate(gateway_name="g1", model_id="claude-sonnet-4-6", model=sentinel)
    assert c.gateway_name == "g1"
    assert c.model_id == "claude-sonnet-4-6"
    assert c.model is sentinel


import models as models_mod


def _fake_models_response():
    return {"data": [{"id": "claude-sonnet-4-6"}, {"id": "gpt-4o"}]}


def test_discover_models_parses_ids(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()

    class FakeResp:
        status_code = 200
        def json(self): return _fake_models_response()
        def raise_for_status(self): pass

    def fake_get(url, headers=None, timeout=None):
        return FakeResp()

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    ids = models_mod.discover_models("https://gw/v1", "key")
    assert ids == ["claude-sonnet-4-6", "gpt-4o"]


def test_discover_models_non_200_returns_none(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()

    def fake_get(url, headers=None, timeout=None):
        raise httpx.HTTPStatusError("500", request=None, response=None)

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    assert models_mod.discover_models("https://gw/v1", "key") is None


def test_discover_models_timeout_returns_none(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()

    def fake_get(url, headers=None, timeout=None):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    assert models_mod.discover_models("https://gw/v1", "key") is None


def test_discover_models_cached(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    calls = {"n": 0}

    class FakeResp:
        status_code = 200
        def json(self): return _fake_models_response()
        def raise_for_status(self): pass

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    models_mod.discover_models("https://gw/v1", "key")
    models_mod.discover_models("https://gw/v1", "key")
    assert calls["n"] == 1


def test_discover_models_disabled_returns_none(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    monkeypatch.setenv("DISCOVER_MODELS", "false")
    assert models_mod.discover_models("https://gw/v1", "key") is None


from models import build_pool


def _set_single_gateway(monkeypatch, quality="claude-sonnet-4-6,gpt-4o"):
    monkeypatch.setenv("LLM_BASE_URL", "https://gw1/v1")
    monkeypatch.setenv("LLM_API_KEY", "key1")
    monkeypatch.setenv("LLM_QUALITY_MODELS", quality)
    for n in (2, 3):
        monkeypatch.delenv(f"LLM_GATEWAY_{n}_BASE_URL", raising=False)
        monkeypatch.delenv(f"LLM_GATEWAY_{n}_API_KEY", raising=False)


def test_build_pool_intersects_whitelist(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    _set_single_gateway(monkeypatch)
    monkeypatch.setattr(
        models_mod, "discover_models",
        lambda url, key: ["claude-sonnet-4-6", "gpt-4o", "cheap-model-x"],
    )
    monkeypatch.setattr(models_mod, "_build_chat_model", lambda mid, url, key: f"M:{mid}@{url}")
    pool = build_pool()
    ids = [c.model_id for c in pool]
    assert ids == ["claude-sonnet-4-6", "gpt-4o"]  # cheap-model-x 不在白名单被剔除


def test_build_pool_multi_gateway(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    _set_single_gateway(monkeypatch)
    monkeypatch.setenv("LLM_GATEWAY_2_BASE_URL", "https://gw2/v1")
    monkeypatch.setenv("LLM_GATEWAY_2_API_KEY", "key2")

    def fake_discover(url, key):
        return ["claude-sonnet-4-6"] if "gw1" in url else ["gpt-4o"]

    monkeypatch.setattr(models_mod, "discover_models", fake_discover)
    monkeypatch.setattr(models_mod, "_build_chat_model", lambda mid, url, key: f"M:{mid}@{url}")
    pool = build_pool()
    assert [(c.gateway_name, c.model_id) for c in pool] == [
        ("gateway_1", "claude-sonnet-4-6"),
        ("gateway_2", "gpt-4o"),
    ]


def test_build_pool_empty_falls_back_to_first_whitelist(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    _set_single_gateway(monkeypatch, quality="claude-sonnet-4-6,gpt-4o")
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key: None)  # 探测全失败
    monkeypatch.setattr(models_mod, "_build_chat_model", lambda mid, url, key: f"M:{mid}@{url}")
    pool = build_pool()
    assert len(pool) == 1
    assert pool[0].model_id == "claude-sonnet-4-6"  # 白名单首个降级
    assert pool[0].gateway_name == "gateway_1"


def test_build_pool_no_intersection_falls_back(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    _set_single_gateway(monkeypatch, quality="claude-sonnet-4-6,gpt-4o")
    # 探测成功,但返回的型号都不在白名单 → 无交集 → 应降级到白名单首个
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key: ["only-cheap-x", "only-cheap-y"])
    monkeypatch.setattr(models_mod, "_build_chat_model", lambda mid, url, key: f"M:{mid}@{url}")
    pool = build_pool()
    assert len(pool) == 1
    assert pool[0].model_id == "claude-sonnet-4-6"
    assert pool[0].gateway_name == "gateway_1"


from models import ModelRouterMiddleware, StaticModelPoolProvider


def _candidate(name, mid):
    return ModelCandidate(gateway_name=name, model_id=mid, model=object())


def _fake_request():
    """最小 ModelRequest 替身:只需 override(model=...) 返回带 model 的对象。"""
    class Req:
        def __init__(self, model=None):
            self.model = model
        def override(self, model):
            return Req(model=model)
    return Req()


def test_router_first_candidate_success():
    pool = [_candidate("g1", "claude-sonnet-4-6"), _candidate("g2", "gpt-4o")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))
    seen = []

    def handler(req):
        seen.append(req.model)
        return "OK"

    out = mw.wrap_model_call(_fake_request(), handler)
    assert out == "OK"
    assert seen == [pool[0].model]  # 只用了首候选


def test_router_switches_on_retryable():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))
    seen = []

    def handler(req):
        seen.append(req.model)
        if req.model is pool[0].model:
            raise FakeStatusError(503)
        return "OK2"

    out = mw.wrap_model_call(_fake_request(), handler)
    assert out == "OK2"
    assert seen == [pool[0].model, pool[1].model]  # 切到了第二个
    assert mw._is_cooling(pool[0]) is True            # g1 被标记不健康


def test_router_non_retryable_raises_immediately():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))
    calls = []

    def handler(req):
        calls.append(req.model)
        raise FakeStatusError(400)  # 鉴权/参数类,不换

    try:
        mw.wrap_model_call(_fake_request(), handler)
        assert False, "应抛出"
    except FakeStatusError as e:
        assert e.status_code == 400
    assert calls == [pool[0].model]  # 没切第二个


def test_router_all_exhausted_raises_last():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))

    def handler(req):
        raise FakeStatusError(503)

    try:
        mw.wrap_model_call(_fake_request(), handler)
        assert False, "应抛出"
    except FakeStatusError as e:
        assert e.status_code == 503


def test_router_cooldown_expires_and_heals(monkeypatch):
    """冷却到期后,被标记的网关重新回到健康候选(spec §6 自愈)。"""
    clock = {"t": 1000.0}
    monkeypatch.setattr(models_mod.time, "monotonic", lambda: clock["t"])

    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))

    # 标记 g1 不健康(冷却 30s,到期时间 = 1000 + 30 = 1030)
    mw._mark_unhealthy(pool[0])
    assert mw._is_cooling(pool[0]) is True       # 当前 t=1000 < 1030,冷却中

    clock["t"] = 1029.0                        # 还没到期
    assert mw._is_cooling(pool[0]) is True

    clock["t"] = 1031.0                        # 已过 30s 冷却窗口
    assert mw._is_cooling(pool[0]) is False       # 自愈:重新可用


async def test_router_async_first_success():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))
    seen = []

    async def handler(req):
        seen.append(req.model)
        return "OK"

    out = await mw.awrap_model_call(_fake_request(), handler)
    assert out == "OK"
    assert seen == [pool[0].model]


async def test_router_async_switches_on_retryable():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))
    seen = []

    async def handler(req):
        seen.append(req.model)
        if req.model is pool[0].model:
            raise FakeStatusError(503)
        return "OK2"

    out = await mw.awrap_model_call(_fake_request(), handler)
    assert out == "OK2"
    assert seen == [pool[0].model, pool[1].model]
    assert mw._is_cooling(pool[0]) is True


async def test_router_async_non_retryable_raises():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))
    calls = []

    async def handler(req):
        calls.append(req.model)
        raise FakeStatusError(400)

    try:
        await mw.awrap_model_call(_fake_request(), handler)
        assert False, "应抛出"
    except FakeStatusError as e:
        assert e.status_code == 400
    assert calls == [pool[0].model]


async def test_router_async_all_exhausted_raises_last():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))

    async def handler(req):
        raise FakeStatusError(503)

    try:
        await mw.awrap_model_call(_fake_request(), handler)
        assert False, "应抛出"
    except FakeStatusError as e:
        assert e.status_code == 503


def test_router_concurrent_mark_unhealthy_consistent():
    """并发标记同一网关不健康:无异常,最终一致冷却(spec §6 best-effort 无锁)。"""
    import threading
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(StaticModelPoolProvider(pool))
    errors = []

    def worker():
        try:
            mw._mark_unhealthy(pool[0])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []
    assert mw._is_cooling(pool[0]) is True


from models import build_primary_model, build_router_middleware


def test_build_primary_model_returns_first_candidate_model():
    pool = [_candidate("g1", "claude-sonnet-4-6"), _candidate("g2", "gpt-4o")]
    assert build_primary_model(pool) is pool[0].model


def test_build_router_middleware_wraps_pool():
    pool = [_candidate("g1", "a")]
    provider = StaticModelPoolProvider(pool)
    mw = build_router_middleware(provider)
    assert isinstance(mw, ModelRouterMiddleware)
    assert mw._pool_provider.get_pool() == pool


def test_verify_gateway_true_when_discoverable(monkeypatch):
    from models import verify_gateway
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key: ["claude-sonnet-4-6"])
    assert verify_gateway("https://gw/v1", "key") is True


def test_verify_gateway_false_when_none(monkeypatch):
    from models import verify_gateway
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key: None)
    assert verify_gateway("https://gw/v1", "key") is False


def test_lazy_pool_deferred_loading(monkeypatch):
    """验证 LazyPool 确实延迟加载且线程安全。"""
    from models import LazyPool, ModelCandidate

    calls = {"n": 0}

    def fake_actual_build_pool():
        calls["n"] += 1
        return [ModelCandidate(gateway_name="g1", model_id="m1", model=object())]

    monkeypatch.setattr(models_mod, "_actual_build_pool", fake_actual_build_pool)

    pool = LazyPool()
    assert pool._loaded is False
    assert calls["n"] == 0

    assert len(pool) == 1
    assert pool._loaded is True
    assert calls["n"] == 1

    assert pool[0].model_id == "m1"
    assert calls["n"] == 1


def test_build_chat_model_providers(monkeypatch):
    from models import _build_chat_model
    from langchain_anthropic import ChatAnthropic
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_openai import ChatOpenAI

    # Ensure NO_PROXY does not cause httpx initialization failures
    monkeypatch.delenv("NO_PROXY", raising=False)

    # Test anthropic
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    model_anthropic = _build_chat_model("claude-3-5-sonnet", "https://api.anthropic.com", "fake-key")
    assert isinstance(model_anthropic, ChatAnthropic)

    # Test google_genai
    monkeypatch.setenv("LLM_PROVIDER", "google_genai")
    model_google = _build_chat_model("gemini-1.5-pro", "https://generativelanguage.googleapis.com", "fake-key")
    assert isinstance(model_google, ChatGoogleGenerativeAI)

    # Test default/openai fallback
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    model_openai = _build_chat_model("gpt-4o", "https://api.openai.com/v1", "fake-key")
    assert isinstance(model_openai, ChatOpenAI)

    # Test default/openai fallback when LLM_PROVIDER is unset or empty
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    model_default = _build_chat_model("gpt-4o", "https://api.openai.com/v1", "fake-key")
    assert isinstance(model_default, ChatOpenAI)

