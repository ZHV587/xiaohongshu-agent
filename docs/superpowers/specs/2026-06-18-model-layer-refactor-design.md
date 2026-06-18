# 高质量模型自主调度系统 · 设计

- 日期:2026-06-18
- 范围:后端模型装配与运行时调度(`agent.py` / `subagents.py` / `cli.py` + 新建 `models.py`)
- 状态:设计已定,待写实现计划
- 演进说明:本 spec 由"模型层重构(删 patch + 发现式选型)"演化而来。那只是本系统的**地基子集**;完整目标是一个**在 deepagents/langchain 原生机制基础上构建的、质量优先的多网关自主调度系统**。

---

## 1. 背景与动机

### 1.1 现状的根本问题

**问题一:monkey-patch 篡改 deepagents 内部类型检查(脆弱 + 不合规)**

`agent.py` 与 `subagents.py` 各有一段逐字重复的 ~35 行 monkey-patch,替换 `deepagents._models.resolve_model`、`deepagents.graph.resolve_model` 及 `summarization` 模块内的 `isinstance`,目的是让 `RunnableWithFallbacks` 绕过 deepagents 的 `isinstance(model, BaseChatModel)` 检查。

已查证:deepagents 官方只支持 `str` 或 `BaseChatModel`(文档 + main 源码);LangChain [Issue #33129](https://github.com/langchain-ai/langchain/issues/33129) 将"`create_agent` 接受 `RunnableWithFallbacks`"归为 Feature 并关闭,无支持承诺。这段 patch 赌的是无契约保证的内部实现细节,升级即可能失效。

**问题二:模型构建逻辑重复 ~200 行**

`agent.py::build_llm_model` 与 `subagents.py::build_analyst_model` 近乎逐字重复(各 ~100 行):解析 env → `init_chat_model` → 硬编码 5 家 fallback 链 → `with_fallbacks`。

**问题三:盲目指定模型 + 无运行时容灾**

代码硬编码具体型号(`gpt-4o`/`deepseek-chat`/…),触发仅看"env 有无该家 key"。实际走 OneAPI 中转网关时,代码不知道网关实际开通了哪些模型,硬调可能 404 / 名字对不上。且容灾是静态 `with_fallbacks`,无健康度感知、不能跨网关、改链路要改代码。

### 1.2 现状事实快照(2026-06-18 实测)

- `.env` 中 `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` 三者全空 → OneAPI 路径空跑;实际走默认分支 `init_chat_model("claude-sonnet")` 经 `ANTHROPIC_BASE_URL=https://chat.aiprox.net`(一个 OpenAI/Anthropic 兼容中转网关)。
- `KIMI/DEEPSEEK/OPENAI` 的 key 为 `sk-test-xxx` 假值,`GEMINI` 为空 → 当前 fallback 链一条都装不起来。
- `ANALYST_MODEL_NAME` 常量除作子智能体模型外,还被 `RubricMiddleware` 当评分模型字符串用(`agent.py`/`cli.py`)。

---

## 2. 核心决策(全部已确认)

| # | 决策 | 选择 |
|---|---|---|
| 1 | 容灾/选择实现机制 | 原生中间件 `wrap_model_call` 扩展点,**非 monkey-patch、非自研框架** |
| 2 | 智能选择由谁做 | **中间件自动调度,agent 无感**(非 LLM 运行时自选) |
| 3 | 范围 | 一次设计完整的自主调度系统 |
| 4 | 实现约束 | **在 deepagents/langchain 原生基础上改**,产物是标准 `AgentMiddleware` 子类 |
| 5 | 质量原则 | **质量优先,绝不为省钱降级** |
| 6 | 主/子质量档 | **同档**,子智能体也用最高质量,共用一个池 |
| 7 | 够格模型来源 | **配置白名单**,质量下限由用户掌控 |

### 2.1 "智能"在质量优先下的准确含义

池里**只放高质量模型**(白名单保证),因此任何选择都不掉质量。"智能"= **高质量模型之间的健康度感知容灾与负载分摊**,fallback 方向永远是"换一个一样好的",**绝不降级到低质量/廉价模型**。耗尽高质量候选则抛错交上层,不将就。

---

## 3. 可行性验证(全原生,已实测)

| 能力 | 原生支持点 | 验证 |
|---|---|---|
| 运行时换 url+key+model | `ModelRequest.override(model=任意 BaseChatModel 实例)`;每实例自带 url/key | ✅ override 即换网关 |
| 按上下文做调度决策 | `wrap_model_call` 的 `request` 携带 `state`/`messages`/`runtime` | ✅ 中间件可读上下文 |
| 失败换候选重试 | 同一 `wrap_model_call` 内反复 `handler(request.override(...))` | ✅ `ModelFallbackMiddleware` 即此模式 |
| 官方扩展点 | `AgentMiddleware.wrap_model_call` / `awrap_model_call`,deepagents 自带中间件均重写 | ✅ 公开扩展点 |
| 中间件单例持久 | 实例在图生命周期内复用,实例属性可存健康状态 | ✅ |

---

## 4. 两条实现铁律(自审实测,违反必崩)

**铁律一:provider 一律 `openai`,所有模型经其所属网关的 base_url。**

OneAPI 是 OpenAI 兼容网关,把 Claude/GPT/… 统一成 OpenAI 格式。`/v1/models` 返回**裸 id**(无 provider 前缀)。任何模型构造必须:

```python
init_chat_model(
    model=model_id,            # /v1/models 返回的裸 id
    model_provider="openai",   # 钉死 openai,不按名字推断 provider
    base_url=<该候选所属网关 url>,
    api_key=<该网关 key>,
    temperature=..., timeout=60, max_retries=...,
)
```

否则裸名 `claude-*` 会被推成 anthropic 原生端点,绕开网关、base_url 失效。

**铁律二:`ModelRouterMiddleware` 必须同时实现 `wrap_model_call`(sync)与 `awrap_model_call`(async)。**

`AgentMiddleware` 有 sync/async 两个扩展点。**CLI**(`agent.stream`,同步)走 sync;**LangGraph Server**(生产前端路径,async)走 async。**只实现 sync 版会导致调度在 server 模式被完全绕过、静默失效**。两版共享同一套健康度状态与选择逻辑,差异仅 `handler` vs `await handler`。

**铁律三:`register_harness_profile` 的 key 必须用 `"openai"`(铁律一的衍生约束)。**

deepagents 按模型**解析后的 provider** 匹配 harness profile key(先 `provider:model` 精确,再 `provider` 前缀,否则 None→空默认 profile)。铁律一把所有模型钉死 `provider="openai"`,故 `agent.py` / `cli.py` 顶部用于安全加固的 `register_harness_profile(...)` 必须以 `"openai"` 注册。**若沿用历史的 `"anthropic"` key,profile 静默失配 → `excluded_tools`(`execute`/`write_todos`)与 `general_purpose_subagent=disabled` 全部失效 → `execute`(shell)等危险工具重新暴露给文案智能体。****验证方式(重要)**:工具排除由 `_ToolExclusionMiddleware` 在模型调用时对 `request.tools` 做 `override(tools=filtered)` 实现,不从编译图的 `tools` 节点删除——故静态读 `agent.nodes['tools']` 永远是全集,观测不到此修复。正确验证:(a) 主模型(openai)的 `_harness_profile_for_model` 命中且解析出的 `excluded_tools` 非空;(b) 驱动 `_ToolExclusionMiddleware` 确认 `execute`/`write_todos` 被实际滤掉;(c) 主模型的 "No harness profile matched" 日志消失。已实测:key=`"anthropic"` 时主模型 profile 未命中、`excluded_tools` 为空;改 `"openai"` 后命中、`execute`/`write_todos` 被过滤。Task 12 须加回归测试钉住(防改回 `"anthropic"`,静态测试测不出)。

---

## 5. 模块设计:`models.py`

唯一模型装配与调度出口。

```
ModelCandidate(dataclass):
    gateway_name: str         # 网关标识(日志/健康度键用)
    model_id: str             # 裸 id
    model: BaseChatModel       # 按铁律一构造的完整实例(provider=openai+该网关url/key)

build_pool() -> list[ModelCandidate]
    1. 从 env 读资源池:一个或多个网关 (name, url, key)(§7)
    2. 读质量白名单 LLM_QUALITY_MODELS(逗号分隔的裸 id 集合)
    3. 对每个网关 discover_models(url, key) 探测 GET /v1/models(超时5s,带缓存,可禁用)
    4. 候选 = Σ_网关 (该网关清单 ∩ 白名单),各构造为 ModelCandidate(铁律一)
    5. 池为空时降级:见 §8

verify_gateway(url, key) -> bool
    配置时连通性验证:探测一次 /v1/models,可解析即视为"配上能用"。
    供配置写入路径调用(本次后端提供函数;web 联动后续立项)。

build_primary_model(pool) -> BaseChatModel
    返回池中第一个候选的 model 实例,作为 create_deep_agent(model=...) 的初始模型。
    (运行时实际用哪个由 ModelRouterMiddleware 每次覆盖决定)

build_router_middleware(pool) -> ModelRouterMiddleware
    构造调度中间件,主/子/评分各取一个(共用同一 pool,同档)。

[已删除] get_quality_model_name —— 设计修正:原返回裸 id 字符串供 RubricMiddleware,
    但其收字符串后 init 会按名推断 provider(claude-*→anthropic 原生端点),拿
    ANTHROPIC_API_KEY 直发官方绕开网关,违反铁律一且密钥外泄。RubricMiddleware 文档明确
    接受 BaseChatModel 实例,故评分改传 build_primary_model(pool) 实例(resolve_model
    对实例不推断)。本函数已删。评分仍用高质量池(与主/子同档)。
```

### 5.1 `ModelRouterMiddleware`(系统核心)

```
class ModelRouterMiddleware(AgentMiddleware):
    持有:pool(候选列表)、_health(dict: gateway_name → 冷却到期时间戳/健康标记)

    _select_healthy() -> list[ModelCandidate]   # 过滤掉冷却中的,按轮询排序
    _mark_unhealthy(candidate)                   # 记一个冷却到期时间(如 +30s)
    _is_retryable(exc) -> bool                   # 瞬时错误判定(503/超时/限流…)

    wrap_model_call(request, handler):           # sync(CLI)
        for cand in 健康候选轮转:
            try: return handler(request.override(model=cand.model))
            except e:
                if _is_retryable(e): _mark_unhealthy(cand); continue
                else: raise                       # 非瞬时错误(400/鉴权)直接抛,不换
        raise last_exception                      # 全部高质量候选耗尽

    awrap_model_call(request, handler):          # async(Server)—— 同逻辑,await handler
```

**共享瞬时错误谓词**:`middlewares.py` 已有渠道无关的 `_is_retryable`(看状态码 503/限流 + httpx 传输层异常)。本系统将其**抽取为共享函数**(如 `middlewares.is_retryable_error`),`ModelRetryMiddleware` 与 `ModelRouterMiddleware` 共用,避免两套判定漂移。

**职责单一**:`models.py` 只做"读 env → 探测 → 按白名单构造高质量候选 → 提供调度中间件"。不碰 deepagents 内部,可单测。

---

## 6. 健康度并发语义(自审澄清)

健康度状态(`_health` dict)在 server 模式下被并发请求读写。设计为 **best-effort 提示,非强一致状态**:

- 只记"某网关不健康 + 冷却到期时间戳";读时用 `time.monotonic()` 比较当前时间(运行时代码,标准库可用,不受时钟回拨影响)。
- **不加锁**(锁会拖慢热路径)。竞态下最坏后果:两个并发请求同时试了同一个刚挂的网关,各失败一次后各自标记——**无害,只多一次重试**。
- 冷却到期后自动重新纳入候选(自愈)。

---

## 7. 配置(env)

**废弃**:`ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` 作为模型主路径(历史死路)。

**资源池(多网关)**:
```
# 主网关(必填)
LLM_BASE_URL / LLM_API_KEY
# 附加网关(可选,按序号扩展;留空即单网关)
LLM_GATEWAY_2_BASE_URL / LLM_GATEWAY_2_API_KEY
LLM_GATEWAY_3_BASE_URL / LLM_GATEWAY_3_API_KEY
...
```

**质量白名单(必填)**:
```
LLM_QUALITY_MODELS=claude-sonnet-4-6,claude-opus-4,gpt-4o,...
# 裸 id,逗号分隔。池 = 各网关清单 ∩ 此白名单。默认安全:不在白名单的模型永不被用。
```

**开关(可选)**:
```
DISCOVER_MODELS=false   # 关探测,走 §8 降级(测试/离线)
```

**迁移动作(实施时必做)**:当前 `.env` 用 `ANTHROPIC_BASE_URL=https://chat.aiprox.net` + `ANTHROPIC_API_KEY` 在跑。统一后迁入 `LLM_BASE_URL=https://chat.aiprox.net`、`LLM_API_KEY=<原 ANTHROPIC_API_KEY 值>`,并设 `LLM_QUALITY_MODELS`。`models.py` 只读新变量。`.env.example` 重写本节文档化。

> ⚠️ 安全提醒:当前 `.env` 的真实密钥(`ANTHROPIC_API_KEY`/`FEISHU_APP_SECRET` 等)已在本次对话暴露,实施时一并轮换。

---

## 8. 错误处理与降级

- **探测失败**(超时/非200/无 /v1/models/JSON异常):`discover_models` 返回 None,`logger.warning`,该网关本次不纳入池。
- **池为空降级**:所有网关都探测失败 / 白名单交集为空时 → 用一个降级默认候选(`LLM_QUALITY_MODELS` 的**第一个**裸 id,按铁律一构造,走主网关)启动 + 醒目 warning。降级也只在白名单内,**绝不掉质量**。系统继续可用。
- **运行时容灾链**:`ModelRetryMiddleware`(`middlewares.py`,同模型瞬时错误 2 次退避)→ `ModelRouterMiddleware`(换同档候选/跨网关)→ 全部耗尽抛错交上层(CLI try/except、前端错误提示)。retry 与 router 正交叠加。

---

## 9. 三入口收敛

```python
# 共用:pool = build_pool()

# agent.py —— 删:顶部35行patch、build_llm_model
pool = build_pool()
agent = create_deep_agent(
    model=build_primary_model(pool),
    subagents=[baokuan_analyst],                                  # 见 subagents.py
    middleware=[build_retry_middleware(),
                RubricMiddleware(model=get_quality_model_name(pool), ...),
                build_router_middleware(pool)],                    # 调度中间件
    ...                                                            # backend/skills/memory/permissions 不变
)

# subagents.py —— 删:顶部35行patch、build_analyst_model(~100行)、ANALYST_MODEL_NAME 常量
baokuan_analyst = {
    "name": "baokuan-analyst", "description": ..., "system_prompt": ANALYST_SYSTEM_PROMPT,
    "model": build_primary_model(pool),                           # 同池(同档)
    "tools": [read_xhs_data],
    "middleware": [build_router_middleware(pool)],                # 子智能体自挂调度(SubAgent spec 支持 middleware 字段,已验证)
}

# cli.py —— 删:裸 init_chat_model;与 agent.py 同款,三入口零特例
```

`SubAgent` spec 的 `middleware` 字段被 `create_sub_agent` 读取(`spec.get("middleware", [])`,已实测),给子智能体挂调度中间件是官方支持路径。

---

## 10. 测试策略

- **`test_agent_assembly.py`(现有)**:`sk-ant-test` 假环境下设 `DISCOVER_MODELS=false`,确保组装不发真实网络请求。验证 agent 仍可组装。
- **`tests/test_models.py`(新增)**:
  - `build_pool`:单网关 / 多网关 / 白名单交集 / 池为空降级。
  - `discover_models`:mock 200 正常解析 / 非200→None / 超时→None / 缓存只请求一次 / `DISCOVER_MODELS=false` 跳过。
  - `ModelRouterMiddleware.wrap_model_call`:首候选成功直接返回 / 首候选 503 标记不健康并切下一个 / 全部耗尽抛错 / 非瞬时错误(400)不换直接抛 / 冷却到期重新纳入。
  - **`awrap_model_call`:与 sync 同样的分支全覆盖**(铁律二,async 不可漏测)。
  - 健康度并发:模拟两个并发标记同一网关不健康,断言无异常、最终一致冷却。

---

## 11. 改动清单

| 操作 | 文件 | 说明 |
|---|---|---|
| 🆕 新建 | `models.py` | 资源池 + `ModelRouterMiddleware` + 探测/验证(核心,~200 行) |
| ➖ 删 monkey-patch ×35 行 | `agent.py`、`subagents.py` | 逐字重复 patch |
| ➖ 删 `build_llm_model`/`build_analyst_model`(~200行) | `agent.py`、`subagents.py` | 含直连多厂商旧 fallback |
| ➖ 删 `ANALYST_MODEL_NAME` 常量 | `subagents.py` | 改 `get_quality_model_name(pool)` |
| ✏️ 改入口装配 | `agent.py`、`subagents.py`、`cli.py` | 三入口共用 pool + 调度中间件 |
| ✏️ env 统一 + 重写文档 | `.env` / `.env.example` | 多网关资源池 + 质量白名单 |
| ✏️ 测试 | `tests/test_agent_assembly.py` + 新 `tests/test_models.py` | 见 §10,含 async 全覆盖 |

**净效果**:删 ~270 行重复/脆弱代码,加 ~200 行集中可测代码。获得:零 monkey-patch、零自研框架(纯原生中间件)、质量优先的多网关健康度容灾调度,sync/async 双路径生效。

---

## 12. 显式非目标(本次不做)

- **web 配置界面联动**(前端拉取/下拉选模型、可视化配置、配置时调 `verify_gateway`)—— 后端调度稳定后单独立项。本次仅提供 `verify_gateway` 后端函数。
- **按任务难度选模型**(质量优先已排除"简单任务用弱模型")。
- **LLM 真·自主选模型**(已定为中间件调度)。
- **跨进程共享健康度状态**(本次进程内 best-effort;多副本部署各自独立,可接受)。
