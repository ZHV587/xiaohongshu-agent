# 高质量模型自主调度系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一个纯原生 `AgentMiddleware` 子类替换脆弱的 monkey-patch,实现质量优先、多网关、健康度容灾的运行时模型调度。

**Architecture:** 新建 `models.py`,从 env 读多网关资源池,探测各网关 `GET /v1/models`,与质量白名单求交集得到"高质量候选实例"列表;`ModelRouterMiddleware`(实现原生 `wrap_model_call` + `awrap_model_call` 双扩展点)在每次模型调用时从健康候选里选一个、失败则标记不健康并切同档下一个。主/子/评分共用同一池。删除所有 monkey-patch 与重复的 `build_*_model`。

**Tech Stack:** Python、langchain 1.3.9(`AgentMiddleware`/`ModelRequest.override`/`init_chat_model`)、deepagents 0.6.10(`create_deep_agent`/`SubAgent` middleware 字段)、httpx(探测)、pytest + pytest-asyncio(`asyncio_mode="auto"`)。

**关键约束(来自 spec §4 两条铁律):**
1. 所有模型用 `model_provider="openai"` + 该网关的 `base_url`/`api_key` 构造(裸 id 不走 provider 推断)。
2. `ModelRouterMiddleware` 必须**同时**实现 sync 的 `wrap_model_call` 和 async 的 `awrap_model_call` —— 默认 sync 版会 `raise NotImplementedError`,只写 async 会让 CLI(`stream`)崩、只写 sync 会让 Server(`astream`)绕过调度。

> **执行修正(2026-06-18,实际偏离本计划文字之处以此为准):**
> 1. **get_quality_model_name 已废弃删除。** 本计划 Task 7/8/10 让 RubricMiddleware 用 get_quality_model_name(pool)(返回裸 id 字符串)。执行中发现:裸 id 字符串经 RubricMiddleware 内部 init 会按名推断 provider(claude-* 推成 anthropic 原生端点),拿真实 ANTHROPIC_API_KEY 绕开网关泄漏,违反铁律一。已改为 model=build_primary_model(pool)(传按铁律一构造好的 BaseChatModel 实例,resolve_model 对实例不推断),并删除该函数。下文凡 get_quality_model_name 字样均作废。
> 2. **铁律三(新增):register_harness_profile 的 key 必须用 openai。** 铁律一钉死 provider=openai 后,旧 anthropic key 会让 harness profile 失配,导致 excluded_tools(execute/write_todos)安全加固失效、execute shell 工具暴露。详见 spec 铁律三。
> 3. 上述两点均已加回归测试钉死(tests/test_agent_assembly.py),反证验证可捕获回归。

---

## File Structure

| 文件 | 职责 | 操作 |
|---|---|---|
| `middlewares.py` | 抽取共享的 `is_retryable_error` 谓词 + 保留 `build_retry_middleware` | 修改 |
| `models.py` | 资源池构造 + 探测 + `ModelRouterMiddleware` + 装配工厂(唯一模型出口) | 新建 |
| `agent.py` | 删 patch/build_llm_model,改用 `models.py` | 修改 |
| `subagents.py` | 删 patch/build_analyst_model/常量,改用 `models.py` | 修改 |
| `cli.py` | 删裸 init_chat_model,改用 `models.py` | 修改 |
| `.env` / `.env.example` | 多网关资源池 + 质量白名单文档 | 修改 |
| `tests/test_models.py` | 调度系统全部单测(含 async) | 新建 |
| `tests/test_agent_assembly.py` | 加 `DISCOVER_MODELS=false` 避免真实网络 | 修改 |

依赖顺序:Task 1(谓词)→ 2(数据结构)→ 3(探测)→ 4(池)→ 5(router sync)→ 6(router async)→ 7(工厂)→ 8(agent.py)→ 9(subagents.py)→ 10(cli.py)→ 11(env/文档)→ 12(组装测试)。

---

## Task 1: 抽取共享的 `is_retryable_error` 谓词

**Files:**
- Modify: `middlewares.py`
- Test: `tests/test_models.py`(新建)

`middlewares.py` 现有模块私有 `_is_retryable`。router 也要同款判定,抽成公开函数避免漂移(spec §5.1)。

- [ ] **Step 1: 写失败测试**

创建 `tests/test_models.py`:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd "e:/小红书智能体" && .venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_retryable_error' from 'middlewares'`

- [ ] **Step 3: 抽取函数**

在 `middlewares.py` 中,把现有 `_is_retryable` 改名为公开 `is_retryable_error`(函数体不变),并让 `build_retry_middleware` 引用新名。改动后 `middlewares.py` 的相关部分:

```python
def is_retryable_error(exc: Exception) -> bool:
    """渠道无关地判断异常是否值得重试。"""
    # 各家 SDK 的 APIStatusError 都把 HTTP 状态码挂在 .status_code 上。
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and status in _RETRYABLE_STATUS:
        return True
    # 连接断开 / 各类超时 —— anthropic/openai 底层都用 httpx,统一兜住。
    if isinstance(exc, httpx.TransportError):
        return True
    # SDK 自己包装的连接/超时异常(如 APIConnectionError/APITimeoutError),
    # 不一定继承 httpx,按类名兜底。
    name = type(exc).__name__.lower()
    return "connection" in name or "timeout" in name


def build_retry_middleware() -> ModelRetryMiddleware:
    """构造 agent 节点级重试 middleware(指数退避 + jitter,渠道无关)。"""
    return ModelRetryMiddleware(
        max_retries=2,
        retry_on=is_retryable_error,
        backoff_factor=2.0,
        initial_delay=1.0,
        max_delay=30.0,
        jitter=True,
        on_failure="error",
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add middlewares.py tests/test_models.py
git commit -m "refactor: 抽取共享 is_retryable_error 谓词供 router 复用"
```

---

## Task 2: `ModelCandidate` 数据结构

**Files:**
- Create: `models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 追加:

```python
from models import ModelCandidate


def test_model_candidate_holds_fields():
    sentinel = object()  # 占位模型实例
    c = ModelCandidate(gateway_name="g1", model_id="claude-sonnet-4-6", model=sentinel)
    assert c.gateway_name == "g1"
    assert c.model_id == "claude-sonnet-4-6"
    assert c.model is sentinel
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py::test_model_candidate_holds_fields -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'models'`

- [ ] **Step 3: 创建 models.py 头部 + 数据结构**

创建 `models.py`:

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py::test_model_candidate_holds_fields -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py
git commit -m "feat: models.py 骨架 + ModelCandidate 数据结构"
```

---

## Task 3: `discover_models` 探测网关可用模型

**Files:**
- Modify: `models.py`
- Test: `tests/test_models.py`

探测 `GET {base_url}/v1/models`,超时 5s,带进程内缓存,`DISCOVER_MODELS=false` 可禁用(spec §5、§8)。

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 追加:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k discover -v`
Expected: FAIL — `AttributeError: module 'models' has no attribute '_DISCOVER_CACHE'` / `discover_models`

- [ ] **Step 3: 实现 discover_models**

在 `models.py` 的 `ModelCandidate` 之后追加:

```python
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
```

注:`base_url` 约定为含 `/v1` 的网关根(如 `https://gw/v1`),拼接后为 `…/v1/models`。

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k discover -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py
git commit -m "feat: discover_models 探测 /v1/models(超时/缓存/可禁用)"
```

---

## Task 4: `build_pool` 构造高质量候选池

**Files:**
- Modify: `models.py`
- Test: `tests/test_models.py`

读多网关 env + 白名单,各网关清单 ∩ 白名单 → 候选实例列表;池为空时降级到白名单首个(spec §5、§7、§8)。

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 追加:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k build_pool -v`
Expected: FAIL — `ImportError: cannot import name 'build_pool'` / `_build_chat_model`

- [ ] **Step 3: 实现 _build_chat_model + _read_gateways + build_pool**

在 `models.py` 追加:

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k build_pool -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py
git commit -m "feat: build_pool 多网关∩白名单构造高质量候选池 + 降级"
```

---

## Task 5: `ModelRouterMiddleware` 的 sync `wrap_model_call`

**Files:**
- Modify: `models.py`
- Test: `tests/test_models.py`

每次调用从健康候选轮转选一个;瞬时错误标记不健康并切下一个;非瞬时错误直接抛;全耗尽抛最后异常(spec §5.1、§6)。

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 追加:

```python
from models import ModelRouterMiddleware


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
    mw = ModelRouterMiddleware(pool)
    seen = []

    def handler(req):
        seen.append(req.model)
        return "OK"

    out = mw.wrap_model_call(_fake_request(), handler)
    assert out == "OK"
    assert seen == [pool[0].model]  # 只用了首候选


def test_router_switches_on_retryable():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(pool)
    seen = []

    def handler(req):
        seen.append(req.model)
        if req.model is pool[0].model:
            raise FakeStatusError(503)
        return "OK2"

    out = mw.wrap_model_call(_fake_request(), handler)
    assert out == "OK2"
    assert seen == [pool[0].model, pool[1].model]  # 切到了第二个
    assert mw._is_cooling("g1") is True            # g1 被标记不健康


def test_router_non_retryable_raises_immediately():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(pool)
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
    mw = ModelRouterMiddleware(pool)

    def handler(req):
        raise FakeStatusError(503)

    try:
        mw.wrap_model_call(_fake_request(), handler)
        assert False, "应抛出"
    except FakeStatusError as e:
        assert e.status_code == 503
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k router -v`
Expected: FAIL — `ImportError: cannot import name 'ModelRouterMiddleware'`

- [ ] **Step 3: 实现 ModelRouterMiddleware(sync)**

在 `models.py` 追加(import 区已含 `time`、`AgentMiddleware`、`ModelRequest`、`is_retryable_error`):

```python
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
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k router -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py
git commit -m "feat: ModelRouterMiddleware sync wrap_model_call(健康度轮转容灾)"
```

---

## Task 6: `ModelRouterMiddleware` 的 async `awrap_model_call`(铁律二)

**Files:**
- Modify: `models.py`
- Test: `tests/test_models.py`

server 模式走 async,必须实现,否则调度被绕过(spec §4 铁律二)。pytest 已配 `asyncio_mode="auto"`,async 测试直接写。

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 追加:

```python
async def test_router_async_first_success():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(pool)
    seen = []

    async def handler(req):
        seen.append(req.model)
        return "OK"

    out = await mw.awrap_model_call(_fake_request(), handler)
    assert out == "OK"
    assert seen == [pool[0].model]


async def test_router_async_switches_on_retryable():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(pool)
    seen = []

    async def handler(req):
        seen.append(req.model)
        if req.model is pool[0].model:
            raise FakeStatusError(503)
        return "OK2"

    out = await mw.awrap_model_call(_fake_request(), handler)
    assert out == "OK2"
    assert seen == [pool[0].model, pool[1].model]
    assert mw._is_cooling("g1") is True


async def test_router_async_non_retryable_raises():
    pool = [_candidate("g1", "a"), _candidate("g2", "b")]
    mw = ModelRouterMiddleware(pool)
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
    mw = ModelRouterMiddleware(pool)

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
    mw = ModelRouterMiddleware(pool)
    errors = []

    def worker():
        try:
            mw._mark_unhealthy(pool[0])
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert errors == []                 # 无锁写 dict 不抛
    assert mw._is_cooling("g1") is True  # 最终一致:g1 处于冷却
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k "async or concurrent" -v`
Expected: FAIL — `NotImplementedError`(默认 `awrap_model_call` 未实现)或缺方法

- [ ] **Step 3: 实现 awrap_model_call**

在 `ModelRouterMiddleware` 内,`wrap_model_call` 之后追加(逻辑同 sync,差异仅 `await handler`):

```python
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
                raise
        assert last_exc is not None
        raise last_exc
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k "async or concurrent" -v`
Expected: PASS(5 passed:4 async + 1 concurrent)

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py
git commit -m "feat: ModelRouterMiddleware async awrap_model_call(铁律二) + 并发健康度测试"
```

---

## Task 7: 装配工厂 + `verify_gateway`

**Files:**
- Modify: `models.py`
- Test: `tests/test_models.py`

三入口共用的薄工厂 + 配置时连通性验证函数(spec §5、§12:本次仅提供后端函数,web 联动后续立项)。

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 追加:

```python
from models import build_primary_model, build_router_middleware, get_quality_model_name


def test_build_primary_model_returns_first_candidate_model():
    pool = [_candidate("g1", "claude-sonnet-4-6"), _candidate("g2", "gpt-4o")]
    assert build_primary_model(pool) is pool[0].model


def test_get_quality_model_name_returns_first_id():
    pool = [_candidate("g1", "claude-sonnet-4-6"), _candidate("g2", "gpt-4o")]
    assert get_quality_model_name(pool) == "claude-sonnet-4-6"


def test_build_router_middleware_wraps_pool():
    pool = [_candidate("g1", "a")]
    mw = build_router_middleware(pool)
    assert isinstance(mw, ModelRouterMiddleware)
    assert mw._pool is pool


def test_verify_gateway_true_when_discoverable(monkeypatch):
    from models import verify_gateway
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key: ["claude-sonnet-4-6"])
    assert verify_gateway("https://gw/v1", "key") is True


def test_verify_gateway_false_when_none(monkeypatch):
    from models import verify_gateway
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key: None)
    assert verify_gateway("https://gw/v1", "key") is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -k "primary_model or quality_model_name or router_middleware_wraps or verify_gateway" -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: 实现工厂**

在 `models.py` 末尾追加:

```python
def build_primary_model(pool: list[ModelCandidate]) -> BaseChatModel:
    """池中第一个候选实例,作为 create_deep_agent(model=...) 初始模型。"""
    return pool[0].model


def build_router_middleware(pool: list[ModelCandidate]) -> ModelRouterMiddleware:
    """构造调度中间件(主/子/评分各取一个,共用同一池)。"""
    return ModelRouterMiddleware(pool)


def get_quality_model_name(pool: list[ModelCandidate]) -> str:
    """池中第一个候选的裸 id,供 RubricMiddleware(收字符串)。"""
    return pool[0].model_id


def verify_gateway(base_url: str, api_key: str) -> bool:
    """配置时连通性验证:能探到非空清单即视为'配上能用'。

    委托 discover_models;能返回非空清单为 True。供配置写入路径调用
    (本次仅后端函数;web 联动后续立项,见 spec §12)。
    """
    return bool(discover_models(base_url, api_key))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py -v`
Expected: PASS(全部,~29 passed)

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py
git commit -m "feat: 装配工厂 build_primary_model/build_router_middleware/get_quality_model_name + verify_gateway"
```

---

## Task 8: 收敛 `agent.py`(删 patch + build_llm_model,改用 models.py)

**Files:**
- Modify: `agent.py`(删除第 8-42 行 patch、`build_llm_model` 全函数及 `model = build_llm_model(...)`;改装配)
- Test: 由 Task 12 的组装测试覆盖

- [ ] **Step 1: 删除 monkey-patch 块**

删除 `agent.py` 第 8-42 行(`# Patch deepagents model resolver ...` 到 `except Exception as e: ... warning(...)` 整块)。

- [ ] **Step 2: 删除 build_llm_model 与其调用**

删除 `agent.py::build_llm_model` 整个函数定义(约第 82-231 行),以及 `model = build_llm_model(MAIN_MODEL)`(约第 233 行)。

- [ ] **Step 3: 改导入与装配**

将 `agent.py` 顶部导入区的模型相关导入替换为(保留其余 deepagents/工具导入不变):

```python
from models import build_pool, build_primary_model, build_router_middleware, get_quality_model_name
```

删除不再需要的 `from langchain.chat_models import init_chat_model`(若该文件他处不再使用)。

在 `register_harness_profile(...)` 之后、`agent = create_deep_agent(...)` 之前,构造池:

```python
pool = build_pool()
```

将 `rubric_middleware` 的 `model=` 改为:

```python
rubric_middleware = RubricMiddleware(
    model=get_quality_model_name(pool),
    system_prompt="""...原文不变...""",
    max_iterations=2,
)
```

将 `create_deep_agent(...)` 调用改为:

```python
agent = create_deep_agent(
    model=build_primary_model(pool),
    tools=[read_xhs_data, lark_cli],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
    backend=backend,
    middleware=[build_retry_middleware(), rubric_middleware, build_router_middleware(pool)],
    memory=["/memories/team/AGENTS.md", "/user-memories/AGENTS.md"],
    permissions=[...原文不变...],
    name="xhs-content-agent",
)
```

- [ ] **Step 4: 验证可导入(假环境,禁探测)**

Run:
```bash
cd "e:/小红书智能体" && DISCOVER_MODELS=false LLM_BASE_URL=https://x/v1 LLM_API_KEY=k LLM_QUALITY_MODELS=claude-sonnet-4-6 ANTHROPIC_API_KEY=sk-ant-test .venv/Scripts/python.exe -c "import agent; print('agent ok:', hasattr(agent.agent, 'invoke'))"
```
Expected: 打印 `agent ok: True`(降级到白名单首个,组装成功)

- [ ] **Step 5: 提交**

```bash
git add agent.py
git commit -m "refactor: agent.py 改用 models.py 调度,删 monkey-patch 与 build_llm_model"
```

---

## Task 9: 收敛 `subagents.py`(删 patch + build_analyst_model + 常量)

**Files:**
- Modify: `subagents.py`(删第 2-36 行 patch、`build_analyst_model`、`ANALYST_MODEL_NAME`、`ANALYST_MODEL`;改 spec)
- Test: 由 Task 12 覆盖

注:`agent.py` 与 `cli.py` 当前从 `subagents` 导入 `ANALYST_MODEL_NAME`(已在 Task 8 移除 agent.py 的用法;cli.py 在 Task 10 处理)。本任务移除该常量。

- [ ] **Step 1: 删除 monkey-patch 块**

删除 `subagents.py` 第 2-36 行(`# Patch deepagents ...` 整块,与 agent.py 同款)。

- [ ] **Step 2: 删除 build_analyst_model / 常量 / 模块级构造**

删除:`ANALYST_MODEL_NAME = "..."`(第 54 行)、`build_analyst_model` 整函数(约 56-201 行)、`ANALYST_MODEL = build_analyst_model()`(第 203 行)。保留 `ANALYST_SYSTEM_PROMPT`。

- [ ] **Step 3: 改导入与 spec 装配**

`subagents.py` 顶部改为(保留 `read_xhs_data` 导入、`load_dotenv()`):

```python
from models import build_pool, build_primary_model, build_router_middleware
```

将 `baokuan_analyst` 定义改为(构造一次池供子智能体用):

```python
_pool = build_pool()

baokuan_analyst = {
    "name": "baokuan-analyst",
    "description": (
        "拆解飞书数据里某个方向的小红书爆款,提炼选题角度、标题套路、正文结构、"
        "情绪点与标签习惯。委派时请说明:分析哪个方向,以及把结论写到哪个文件路径"
        "(如 '分析露营装备方向,结论写到 /analysis/露营装备.md')。"
    ),
    "system_prompt": ANALYST_SYSTEM_PROMPT,
    "model": build_primary_model(_pool),
    "tools": [read_xhs_data],
    "middleware": [build_router_middleware(_pool)],
}
```

- [ ] **Step 4: 验证可导入**

Run:
```bash
cd "e:/小红书智能体" && DISCOVER_MODELS=false LLM_BASE_URL=https://x/v1 LLM_API_KEY=k LLM_QUALITY_MODELS=claude-sonnet-4-6 ANTHROPIC_API_KEY=sk-ant-test .venv/Scripts/python.exe -c "import subagents; print('subagents ok:', subagents.baokuan_analyst['name'])"
```
Expected: 打印 `subagents ok: baokuan-analyst`

- [ ] **Step 5: 提交**

```bash
git add subagents.py
git commit -m "refactor: subagents.py 改用 models.py 池,删 patch/build_analyst_model/常量"
```

---

## Task 10: 收敛 `cli.py`(删裸 init_chat_model,改用 models.py)

**Files:**
- Modify: `cli.py`(改导入、rubric model、create_deep_agent 的 model/middleware)
- Test: Task 12 覆盖 + 手动冒烟

- [ ] **Step 1: 改导入**

`cli.py` 顶部:移除 `from langchain.chat_models import init_chat_model`(若他处不用)与 `from subagents import ANALYST_MODEL_NAME, baokuan_analyst`,改为:

```python
from models import build_pool, build_primary_model, build_router_middleware, get_quality_model_name
from subagents import baokuan_analyst
```

- [ ] **Step 2: 构造池 + 改 rubric + 改 create_deep_agent**

在 `register_harness_profile(...)` 之后加:

```python
pool = build_pool()
```

将 `rubric_middleware` 的 `model=ANALYST_MODEL_NAME` 改为 `model=get_quality_model_name(pool)`。

将 `create_deep_agent(...)` 的 `model=init_chat_model(model=MAIN_MODEL, ...)` 改为 `model=build_primary_model(pool)`,并把 `middleware=[build_retry_middleware(), rubric_middleware]` 改为 `middleware=[build_retry_middleware(), rubric_middleware, build_router_middleware(pool)]`。其余参数(tools/skills/backend/memory/permissions/name)不变。

- [ ] **Step 3: 验证可导入**

Run:
```bash
cd "e:/小红书智能体" && DISCOVER_MODELS=false LLM_BASE_URL=https://x/v1 LLM_API_KEY=k LLM_QUALITY_MODELS=claude-sonnet-4-6 ANTHROPIC_API_KEY=sk-ant-test .venv/Scripts/python.exe -c "import cli; print('cli ok:', hasattr(cli.agent, 'stream'))"
```
Expected: 打印 `cli ok: True`

- [ ] **Step 4: 提交**

```bash
git add cli.py
git commit -m "refactor: cli.py 改用 models.py 调度,三入口零特例"
```

---

## Task 11: env 统一与文档(`.env` / `.env.example`)

**Files:**
- Modify: `.env`(本地迁移,不提交真实密钥)
- Modify: `.env.example`(文档化新配置)

- [ ] **Step 1: 迁移本地 .env**

在 `.env` 中新增/设置(把现有 `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY` 的值迁过来):

```
LLM_BASE_URL=https://chat.aiprox.net/v1
LLM_API_KEY=<原 ANTHROPIC_API_KEY 的值>
LLM_QUALITY_MODELS=claude-sonnet-4-6,claude-opus-4-1
```

> 注:`LLM_BASE_URL` 末尾需含 `/v1`(discover 拼 `/models`)。`LLM_QUALITY_MODELS` 的具体型号以网关 `/v1/models` 实际返回为准,首个为降级默认。

- [ ] **Step 2: 重写 .env.example 模型节**

将 `.env.example` 顶部"# 模型"节替换为:

```
# ── 模型网关(多网关资源池)──────────────────────────────────
# 主网关(必填):OneAPI / OpenAI 兼容中转,base_url 末尾含 /v1
LLM_BASE_URL=https://your-gateway/v1
LLM_API_KEY=your-gateway-key
# 附加网关(可选,按序号扩展;不需要可留空)
# LLM_GATEWAY_2_BASE_URL=https://your-second-gateway/v1
# LLM_GATEWAY_2_API_KEY=your-second-key

# 质量白名单(必填):允许使用的高质量模型裸 id,逗号分隔。
# 池 = 各网关 /v1/models 清单 ∩ 此白名单。不在白名单的模型永不被用(默认安全)。
# 首个 id 作为探测失败时的降级默认。
LLM_QUALITY_MODELS=claude-sonnet-4-6,claude-opus-4-1,gpt-4o

# 关闭启动探测(测试/离线用):置 false 走降级单模型,不发网络请求
# DISCOVER_MODELS=false
```

并删除 `.env.example` 中旧的 `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` 模型行(LangSmith/飞书/JWT 节保留不变)。

- [ ] **Step 3: 验证 build_pool 读新 env(冒烟)**

Run:
```bash
cd "e:/小红书智能体" && DISCOVER_MODELS=false LLM_BASE_URL=https://chat.aiprox.net/v1 LLM_API_KEY=k LLM_QUALITY_MODELS=claude-sonnet-4-6 .venv/Scripts/python.exe -c "from models import build_pool; p=build_pool(); print('pool:', [(c.gateway_name,c.model_id) for c in p])"
```
Expected: 打印 `pool: [('gateway_1', 'claude-sonnet-4-6')]`(降级,因禁探测)

- [ ] **Step 4: 提交(仅 .env.example,.env 不入库)**

```bash
git add .env.example
git commit -m "docs: .env.example 改为多网关资源池 + 质量白名单"
```

---

## Task 12: 组装测试加固(避免真实网络)+ 全量回归

**Files:**
- Modify: `tests/test_agent_assembly.py`

- [ ] **Step 1: 改组装测试,禁探测 + 设新 env**

将 `tests/test_agent_assembly.py` 改为:

```python
def test_agent_importable_and_compiled(monkeypatch):
    # 组装阶段构造模型池,需 env 存在但禁止真实探测(不发网络请求)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DISCOVER_MODELS", "false")
    monkeypatch.setenv("LLM_BASE_URL", "https://test-gw/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "claude-sonnet-4-6")
    import importlib
    import agent as agent_module
    importlib.reload(agent_module)
    assert hasattr(agent_module.agent, "invoke")
    assert hasattr(agent_module.agent, "astream")
```

- [ ] **Step 2: 运行组装测试**

Run: `.venv/Scripts/python.exe -m pytest tests/test_agent_assembly.py -v`
Expected: PASS

- [ ] **Step 3: 全量回归**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: 全部 PASS(新 `test_models.py` + 既有测试无回归)

- [ ] **Step 4: 提交**

```bash
git add tests/test_agent_assembly.py
git commit -m "test: 组装测试禁探测+设池 env,避免真实网络请求"
```

---

## 完成标准

- [ ] `pytest -v` 全绿,`test_models.py` 覆盖(27):谓词(5)、ModelCandidate(1)、discover(5)、build_pool(3)、router sync(4)、router async(4)、并发(1)、工厂(3)、verify_gateway(2)。
- [ ] `agent.py` / `subagents.py` / `cli.py` 中无 `RunnableWithFallbacks` / monkey-patch / `with_fallbacks` / `build_llm_model` / `build_analyst_model` / `ANALYST_MODEL_NAME`。
- [ ] 三入口均 `import` 成功(Task 8/9/10 的冒烟)。
- [ ] `.env.example` 文档化多网关 + 白名单;`.env` 已本地迁移(密钥建议轮换)。
- [ ] grep 校验:`grep -rn "with_fallbacks\|monkey\|resolve_model" agent.py subagents.py cli.py` 无输出。
