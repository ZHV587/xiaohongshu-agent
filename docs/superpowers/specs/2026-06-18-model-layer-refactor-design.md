# 模型层重构设计 · 发现式选型 + 官方原生 fallback

- 日期:2026-06-18
- 范围:后端模型装配层(`agent.py` / `subagents.py` / `cli.py` + 新建 `models.py`)
- 状态:设计已定,待写实现计划

---

## 1. 背景与动机

### 1.1 现状的三个根本问题

**问题一:monkey-patch 篡改 deepagents 内部类型检查(脆弱 + 不合规)**

`agent.py` 和 `subagents.py` 各自顶部有一段**逐字重复**的 ~35 行 monkey-patch,作用是:

- 替换 `deepagents._models.resolve_model` 和 `deepagents.graph.resolve_model`
- 替换 `deepagents.middleware.summarization` 模块内的内置 `isinstance`

目的是让一个 `RunnableWithFallbacks` 对象绕过 deepagents 的 `isinstance(model, BaseChatModel)` 检查。

已查证(deepagents 官方文档 + main 分支源码):**deepagents 只支持 `str` 或 `BaseChatModel` 两种 model 形态**,从未承诺支持 `RunnableWithFallbacks`。这段 patch 赌的是"官方永远只用 `isinstance` 卡类型"这个无契约保证的内部细节,升级即可能失效。LangChain 官方 [Issue #33129](https://github.com/langchain-ai/langchain/issues/33129) 已将"`create_agent` 接受 `RunnableWithFallbacks`"归类为 **Feature 并关闭**,无支持承诺。

**问题二:模型构建逻辑重复 ~200 行**

`agent.py::build_llm_model`(~100 行)与 `subagents.py::build_analyst_model`(~100 行)近乎逐字重复,仅"默认模型名"不同。两者都做:解析 env → `init_chat_model` → 硬编码 5 家 fallback 链 → `with_fallbacks`。

**问题三:盲目指定模型,不问网关实际支持哪些**

代码硬编码具体型号(`gpt-4o`、`deepseek-chat`、`gemini-2.5-flash`…),触发条件仅"env 里有没有该家 key"。但实际部署走 OneAPI 这类中转网关(`LLM_BASE_URL`),一个 key 后面挂一批模型,代码**不知道这个网关实际开通了哪些**,硬调可能 404 / 型号名对不上 / 整条 fallback 是死的。

正确姿势:**先发现(问网关 `GET /v1/models`),再从真实可用清单里选**。

### 1.2 现状事实快照(2026-06-18 实测)

- `.env` 里 `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL` **三者全空** → `build_llm_model` 的"OneAPI 路径"当前空跑。
- 实际生效的是默认分支 `init_chat_model("claude-sonnet")`,经 `ANTHROPIC_BASE_URL=https://chat.aiprox.net` 打到中转网关。
- `KIMI/DEEPSEEK/OPENAI` 的 key 均为 `sk-test-xxx` 假值,`GEMINI` 为空 → 当前 fallback 链**一条都装不起来**。
- `ANALYST_MODEL_NAME` 这个常量除了给子智能体当模型,还被 `RubricMiddleware` 当评分模型字符串用(`agent.py`、`cli.py`)——删除时必须替换,否则 rubric 崩。

---

## 2. 设计目标

完整、彻底消除历史债,所有路径走 LangChain / deepagents 官方接口,**零 monkey-patch、零自研模型包装类**:

1. **合规**:主/子模型都只传单个合法 `BaseChatModel`;fallback 用官方原生 `ModelFallbackMiddleware`。
2. **发现式选型**:启动时探测网关 `GET /v1/models`,从真实可用清单选模型,彻底消灭硬编码型号。
3. **单一出口**:新建 `models.py` 为唯一模型装配模块,`agent.py` / `subagents.py` / `cli.py` 三入口完全共用,零特例。
4. **单一配置路径**:统一到 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 一套 env,废弃 `ANTHROPIC_BASE_URL` 死路。
5. **健壮**:探测失败优雅降级(单模型 + warning),绝不因网关抖动罢工。

---

## 3. 关键技术决策(全部已用源码验证)

| 决策 | 结论 | 验证 |
|---|---|---|
| fallback 实现 | 官方 `langchain.agents.middleware.ModelFallbackMiddleware`,零自研 | 本地 langchain 1.3.9 已含此类;签名 `(first_model, *additional_models: str\|BaseChatModel)` |
| 为何不自研 `FallbackChatModel(BaseChatModel)` | LangChain 1.3.9 / master **无** chat-model 层 fallback 类(`RunnableWithFallbacks` 继承 `RunnableSerializable` 非 `BaseChatModel`),官方解法是中间件而非包模型 | 实测 `issubclass` + master 源码 |
| 中间件兼容性 | `ModelFallbackMiddleware` 经 `wrap_model_call` 工作(出错时 `request.override(model=fallback)` 依次重试),与 deepagents 必装的 `SummarizationMiddleware`、已用的 `ModelRetryMiddleware` 同机制,正交叠加无冲突 | 读 `model_fallback.py` 源码 |
| retry 与 fallback 关系 | 互补:retry 对**同一模型**瞬时错误重试(`middlewares.py`,2 次指数退避);fallback 在某模型**彻底失败后切下一个**。叠加 = 完整容灾 | `middlewares.py` |
| 模型发现 | `GET {base_url}/v1/models`,OpenAI 兼容标准接口,OneAPI 支持 | OneAPI 标准 |
| 探测失败 | 优雅降级:偏好首选单模型 + warning,继续启动 | 用户决策 |

---

## 4. 模块设计:`models.py`

唯一模型装配出口。对外接口:

```
discover_models(base_url, api_key) -> list[str] | None
    GET {base_url}/v1/models,带 Authorization: Bearer {key},超时 5s。
    成功:解析 {"data":[{"id":...}]} 返回 id 列表。
    失败(超时/非200/无此接口/JSON异常):返回 None + logger.warning。
    进程内缓存:同 (base_url, key) 只探测一次(模块级 dict)。
    可禁用:DISCOVER_MODELS=false 直接返回 None(测试/离线用)。

select_models(role, available) -> tuple[primary_name: str, fallback_names: list[str]]
    role ∈ {"main", "analyst"}。available 为清单 list[str] 或 None。
    各 role 有偏好优先级序常量 MAIN_PREFERENCE / ANALYST_PREFERENCE(按能力档位)。
    规则见 §5。

build_main_agent_model()  -> tuple[BaseChatModel, ModelFallbackMiddleware | None]
build_analyst_model()     -> tuple[BaseChatModel, ModelFallbackMiddleware | None]
    1. available = discover_models(...)            # 带缓存
    2. primary_name, fb_names = select_models(role, available)
    3. primary = init_chat_model(primary_name, temperature, timeout, max_retries, ...)
    4. fb_names 非空 → ModelFallbackMiddleware(*[init_chat_model(n,...) for n in fb_names])
       fb_names 为空 → 第二返回值 None
    返回 (primary_model, fallback_middleware_or_None)

get_analyst_model_name()  -> str
    复用 analyst 的 select 结果,返回 primary_name 字符串。
    供 RubricMiddleware(收模型字符串,非实例)。评分模型与子智能体同档同源。
```

**职责单一性**:`models.py` 只做"读已有 env → 探测 → 选型 → 拼成官方接口对象"。不引入新配置项语义,不碰 deepagents 内部。可被单测独立覆盖。

---

## 5. 选型规则(配置优先 + 清单校验)

`select_models(role, available)` 决策表:

| 情况 | primary | fallbacks |
|---|---|---|
| 清单可用 且 用户 `LLM_MODEL` 在清单中 | 用 `LLM_MODEL` | 清单 ∩ role 偏好序的其余模型,按偏好序排列 |
| 清单可用 且 `LLM_MODEL` 未设或不在清单 | role 偏好序中**第一个命中清单**的 | 清单 ∩ role 偏好序的其余模型 |
| **清单不可用(None)** 且 `LLM_MODEL` 已设 | 用 `LLM_MODEL`(尊重用户显式指定) | **空 → 不挂 fallback** |
| **清单不可用(None)** 且 `LLM_MODEL` 未设 | role 的 `DEFAULT_MODEL`(见下) | **空 → 不挂 fallback** |

**降级默认值**:每个 role 有一个独立常量 `MAIN_DEFAULT_MODEL` / `ANALYST_DEFAULT_MODEL`(如 `claude-sonnet-4-6` / `claude-haiku-4-5`),它是 `*_PREFERENCE` 序的首元素的**完整 provider:model 形式**,保证 `init_chat_model` 能直接构造。降级时它是"无清单可校验下的最佳猜测",与今天默认分支行为一致 —— 这是 §1.2 现状下唯一已知能跑通的型号,故作为兜底是安全的。

- `MAIN_PREFERENCE`:强模型档(sonnet 档优先,后接同档其他厂商强模型)。
- `ANALYST_PREFERENCE`:便宜快档(haiku 档优先,后接同档便宜模型)。
- 主/子从**同一份**清单各选自己档位 —— 容灾策略分离,子智能体不会 fallback 到昂贵模型。
- 偏好序仅含**档位语义的型号名**,真实可用性由清单交集裁决;清单里没有的型号自动跳过,**不会再出现"硬调一个不存在的型号"**。

---

## 6. 三入口收敛

```python
# agent.py —— 删:顶部 35 行 patch、build_llm_model 全函数
main_model, main_fb = build_main_agent_model()
rubric_middleware = RubricMiddleware(model=get_analyst_model_name(), ...)
agent = create_deep_agent(
    model=main_model,                                   # 单个合法 BaseChatModel
    subagents=[baokuan_analyst],
    middleware=[build_retry_middleware(), rubric_middleware]
               + ([main_fb] if main_fb else []),        # 官方 ModelFallbackMiddleware
    ...                                                 # 其余 backend/skills/memory/permissions 不变
)

# subagents.py —— 删:顶部 35 行 patch、build_analyst_model(~100 行)、ANALYST_MODEL_NAME 常量
analyst_model, analyst_fb = build_analyst_model()
baokuan_analyst = {
    "name": "baokuan-analyst",
    "description": ...,
    "system_prompt": ANALYST_SYSTEM_PROMPT,
    "model": analyst_model,                             # 单个合法 BaseChatModel
    "tools": [read_xhs_data],
    "middleware": ([analyst_fb] if analyst_fb else []), # 子智能体自挂 fallback(SubAgent spec 支持 middleware 字段)
}

# cli.py —— 删:裸 init_chat_model;改为与 agent.py 同款 build_main_agent_model()
#   rubric model 同样改 get_analyst_model_name();三入口零特例
```

**注**:`SubAgent` TypedDict 的 `middleware` 字段已由 deepagents 支持(`deepagents/middleware/subagents.py`),给子智能体挂 `ModelFallbackMiddleware` 是官方支持路径。

---

## 7. 配置(env)统一

**废弃**:`ANTHROPIC_BASE_URL` / `ANTHROPIC_API_KEY` 作为主路径(历史死路)。

**统一为单一路径**:
- `LLM_BASE_URL` — 模型网关(OneAPI / OpenAI 兼容中转)地址
- `LLM_API_KEY` — 网关 key
- `LLM_MODEL` — (可选)偏好主模型名;留空则从清单按偏好序自动选
- `DISCOVER_MODELS` — (可选)`false` 关闭探测,走降级单模型(测试/离线)

`.env.example` 重写这一节,明确文档化单一路径及各字段语义。**不保留旧 env 名的兼容读取** —— 配置 schema 以正确为准。

**迁移动作(实施时必做)**:当前 `.env` 实际用 `ANTHROPIC_BASE_URL=https://chat.aiprox.net` + `ANTHROPIC_API_KEY=...` 在跑。统一后这两个值需手工迁入新路径:`LLM_BASE_URL=https://chat.aiprox.net`、`LLM_API_KEY=<原 ANTHROPIC_API_KEY 值>`。`models.py` **只读 `LLM_*`**,不再读 `ANTHROPIC_*`;旧变量保留在 `.env` 也不会被新代码使用(可删)。这是一次性人工迁移,实施计划须含"更新本地 `.env`"一步并验证启动。

> ⚠️ 安全提醒(实施前):当前 `.env` 中 `ANTHROPIC_API_KEY`、`FEISHU_APP_SECRET` 等真实密钥已在本次对话中暴露,建议借这次改动一并轮换。

> 子智能体备用厂商 key(KIMI/DEEPSEEK/GEMINI/OPENAI 直连)在"发现式选型"下不再需要:fallback 候选一律走同一个 `LLM_BASE_URL` 网关的真实清单。直连厂商的多 key 探测逻辑随 `build_*_model` 旧实现一并删除。

---

## 8. 错误处理

- **探测健壮性**:超时 / 非 200 / 网关无 `/v1/models` / JSON 异常 → `discover_models` 返回 `None` → 降级单模型,`logger.warning` 记录原因,**不致命**。
- **降级语义**:清单不可用时,用偏好序首选单模型启动,不挂 fallback(§5 第三行)。系统继续可用。
- **retry × fallback 链路**:单模型瞬时错误由 `ModelRetryMiddleware`(2 次退避)兜底;模型彻底失败由 `ModelFallbackMiddleware` 切下一个;全部耗尽 → 抛错交上层(CLI try/except、前端错误提示)。

---

## 9. 测试策略

- **`test_agent_assembly.py`(现有)**:在 `sk-ant-test` 假环境下设 `DISCOVER_MODELS=false`,确保组装测试**不发真实网络请求**到网关。验证 agent 仍可组装(`hasattr invoke/astream`)。
- **`models.py` 新增单测**:
  - `select_models` 四分支(对齐 §5 决策表):清单可用+偏好命中 / 清单可用+LLM_MODEL 指定 / 清单 None+LLM_MODEL 已设(用指定值) / 清单 None+LLM_MODEL 未设(用 role DEFAULT)。
  - `discover_models`:mock HTTP 200 正常解析 / 非 200 返回 None / 超时返回 None / 缓存命中只请求一次 / `DISCOVER_MODELS=false` 跳过。
  - `build_*_model`:有 fallback 时第二返回值是 `ModelFallbackMiddleware`,无清单时为 `None`。

---

## 10. 改动清单

| 操作 | 文件 | 说明 |
|---|---|---|
| 🆕 新建 | `models.py` | 唯一模型出口(~120 行) |
| ➖ 删 monkey-patch ×35 行 | `agent.py`、`subagents.py` | 逐字重复的 patch |
| ➖ 删 `build_llm_model` / `build_analyst_model`(~200 行) | `agent.py`、`subagents.py` | 含直连多厂商 fallback 旧逻辑 |
| ➖ 删 `ANALYST_MODEL_NAME` 常量 | `subagents.py` | 改 `get_analyst_model_name()` 动态 |
| ✏️ 改入口装配 | `agent.py`、`subagents.py`、`cli.py` | 三入口共用 models.py |
| ✏️ rubric 模型名动态 | `agent.py`、`cli.py` | `get_analyst_model_name()` |
| ✏️ env 统一 + 重写文档 | `.env` / `.env.example` | 单一 `LLM_*` 路径 |
| ✏️ 测试补充 | `tests/test_agent_assembly.py` + 新 `tests/test_models.py` | 见 §9 |

**净效果**:删 ~270 行重复/脆弱代码,加 ~120 行集中可测代码。fallback 能力不减反增(从真实清单选,且 retry×fallback 双层)。100% 官方接口,零 monkey-patch,零自研包装类。

---

## 11. 显式非目标(本次不做)

- **配置界面联动**(让 web 前端拉取可用模型下拉选)—— 独立的更大工作,后续单独立项(方案 B)。本次只做后端模型层。
- **探测结果跨进程/磁盘缓存** —— 本次仅进程内缓存,够用。
- **fallback 候选的价格/延迟动态排序** —— 本次按偏好档位序,不做运行时性能感知调度。
