# 思考链 UI 第二层设计(模型原生 reasoning/thinking 块)

- 日期:2026-07-01
- 范围:前端 + 后端(横跨 models.py / config_center / internal_api / rubric_model / web)
- 状态:设计,全部技术前提已服务器只读实测坐实
- 前置:第一层(工具执行流思考链)已上线,见 `2026-07-01-thinking-trace-ui-design.md`

## 1. 背景

第一层把 agent 的**工具执行流**(检索/图谱/落库/委派)解析成思考链。第二层加**模型原生推理**(extended thinking / reasoning),即模型"想什么",与工具"做什么"互补。

第一层上线后生产实测发现:模型的英文思考混进了 ai 正文气泡。根因**已查清**(非网关不支持):`models.py:_build_chat_model` 构造 `ChatAnthropic` 时从没传 `thinking` 参数,Anthropic 默认不开 extended thinking,模型把思考写进了普通 text 块。开启 thinking 后思考走独立块,顺带根治"混进正文"。

## 2. 实证事实(全部服务器只读 docker compose exec 验证,不改磁盘源码)

生产:`LLM_PROVIDER=anthropic`,白名单 `claude-opus-4-8,claude-sonnet-4-6`,走 ChatAnthropic 原生 /v1/messages。

| 验证项 | 结论 |
|---|---|
| 网关透传 thinking(非流式) | ✅ `content=['thinking','text']`,thinking 块 len≈94 |
| 流式 thinking | ✅ `thinking_deltas=11, text_deltas=31`,增量正常到达 |
| temperature=1 硬约束 | ✅ payload 里 temperature 与 thinking 都无条件下发;Anthropic extended thinking 要求 temperature=1,传 0.7 会 400 |
| 池重建触发条件 | ✅ 由 `internal_api._MODEL_POOL_KEYS` 控制(`touches_model_pool`) |
| config 可编辑键 | ✅ 由 `config_center.EDITABLE_KEYS` 控制 |
| rubric 排除(方案B) | ✅ `model_copy(update={"thinking":None,"temperature":0.7})` → 不再返回 thinking 块、content 退回 str,且**原实例不被污染** |

thinking 参数值定为 `{"type":"adaptive","display":"summarized"}`(Opus 4.7+ 语法,返回摘要版思考,省 token 且适合展示)。

## 3. 目标与非目标

**目标**:支持 reasoning 的模型返回结构化 thinking 块,前端渲染为独立「推理」折叠区;可经 config-center 热切开关;rubric 评分不带 thinking;不支持的 provider/模型天然不显示、不报错。

**非目标**:openai/google provider 的 reasoning(形态不同:`additional_kwargs.reasoning`),本轮不做——生产是 anthropic,留待需要时扩展。前端解析层设计为"有块则渲染",未来这些 provider 的块接进来时前端可复用。

## 4. 后端设计

### 4.1 `_build_chat_model` 加 thinking 参数 + temperature 联动

`models.py:_build_chat_model` 签名加 `thinking: dict | None = None`。仅 **anthropic 分支**消费它(openai/google 分支忽略——它们不吃这参数,硬传会错):

```python
def _build_chat_model(model_id, base_url, api_key, *, provider=None, thinking=None):
    ...
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        anthropic_base = ...
        kwargs = dict(model=model_id, api_key=api_key, base_url=anthropic_base,
                      timeout=_TIMEOUT, max_retries=2)
        if thinking:
            # extended thinking 硬约束:temperature 必须为 1(否则 Anthropic 400)。
            kwargs["thinking"] = thinking
            kwargs["temperature"] = 1
        else:
            kwargs["temperature"] = 0.7
        return ChatAnthropic(**kwargs)
    elif provider == "google_genai":
        ...  # 不变
    else:
        ...  # openai,不变
```

**thinking 值显式传参,不在函数内读进程 env**(遵守 models.py 线程安全铁律:配置经参数流入,杜绝并发构池跨线程串值)。

### 4.2 thinking 配置的来源与解析

新增配置键 `LLM_THINKING`,值:`summarized`(开,默认)/ `off`(关)。解析为 thinking dict 的辅助:

```python
def _thinking_from_config(values: dict, provider: str) -> dict | None:
    """仅 anthropic 且 LLM_THINKING != off 时返回 thinking dict,否则 None。"""
    if provider != "anthropic":
        return None
    mode = (values.get("LLM_THINKING") or "summarized").strip().lower()
    if mode == "off":
        return None
    return {"type": "adaptive", "display": "summarized"}
```

两条构造路径都传入:
- `build_pool_from_config`:解析 `provider` 后 `thinking = _thinking_from_config(values, provider)`,`_build_chat_model(..., provider=provider, thinking=thinking)`。
- `build_initial_placeholder_model`:同样从 env 读 `LLM_THINKING` 解析后显式传入。

### 4.3 config-center 热切接入(双白名单)

`LLM_THINKING` 必须同时加进两个白名单,否则开关失效:
- `config_center.py:EDITABLE_KEYS` —— 否则 admin 存不进 config-center。
- `data_foundation/internal_api.py:_MODEL_POOL_KEYS` —— 否则改它不触发 `touches_model_pool`,池不重建 = 死开关。

`LLM_THINKING` **不是** secret,不进 `SECRET_KEYS`;非 deploy-only,不进 `DEPLOY_ONLY_KEYS`。改它 → `touches_model_pool=True` → 若 `gateway_complete` → 重建池 → 下次调用生效(复用现有热切路径,零新机制)。

### 4.4 rubric 排除 thinking(方案 B:model_copy override)

rubric 评分是短判断/结构化输出,不需要 thinking(费 token 且 summarized 思考可能干扰输出格式)。池统一带 thinking,**rubric 专用的 `RegistryRoutedChatModel`(rubric_model.py)在其单一取模型出口 `_resolve()` 统一 override 掉 thinking**:

已核实真实结构——`RegistryRoutedChatModel._resolve()`(rubric_model.py:50-63)是**唯一**取候选出口(池首 `pool[0].model` / 分层 `cand.model` / 空池占位 `self._placeholder` 三个 return 都在此方法内)。故只需在该方法**返回前统一套一层剥离**,一处改动覆盖同步 `_generate` + 异步 `_agenerate` + 声明式 `_RegistryRoutedBound._resolved` 全部路径(它们都调 `_resolve()`):

```python
def _strip_thinking(model: BaseChatModel) -> BaseChatModel:
    """rubric 评分不带 thinking:剥掉 thinking 并恢复 temperature。
    实测 model_copy 不污染原池实例;非 ChatAnthropic(无 thinking 属性)原样返回。"""
    if getattr(model, "thinking", None) is not None:
        return model.model_copy(update={"thinking": None, "temperature": 0.7})
    return model

def _resolve(self) -> BaseChatModel:
    pool = self._registry.get_pool()
    if not pool:
        return _strip_thinking(self._placeholder)
    rubric_model_id = os.environ.get("XHS_RUBRIC_MODEL", "").strip()
    if rubric_model_id:
        for cand in pool:
            if getattr(cand, "model_id", None) == rubric_model_id:
                return _strip_thinking(cand.model)
    return _strip_thinking(pool[0].model)
```

- `model_copy` 是 pydantic 原生(非 hack),实测:override 后不返回 thinking 块、content 退回 str、**原池实例不受污染**(主/子 agent 仍用带 thinking 的同一实例)。
- `getattr(model, "thinking", None) is not None` 守卫:非 ChatAnthropic(openai/google)或未开 thinking 时原样返回,不报错、不多余 copy。
- 主 agent、子 agent 的 `ModelRouterMiddleware` 路径**不经过 `_resolve`**,保留 thinking。

## 5. 前端设计(能力探测:有块则渲染,无则隐藏)

### 5.1 现状与根治

`getContentString`(utils.ts)只提取 `type:"text"` 块——所以开 thinking 后,thinking 块**自动不进正文气泡**(第一层"混进正文"问题被彻底根治,无需额外清洗)。前端只需**新增**对 thinking 块的提取。

### 5.2 提取 thinking 块

在 `web/src/lib/thinking-trace.ts` 新增(与第一层解析器同文件,职责相关):

```typescript
/** 从一条 AI 消息的 content 提取模型原生 reasoning 文本。
 *  兼容:Anthropic thinking 块 {type:"thinking", thinking:"..."};
 *  未来可扩展 openai {type:"reasoning"} / additional_kwargs.reasoning。
 *  无 reasoning → 返回空串(能力探测:没有就不显示)。 */
export function extractReasoning(content: Message["content"]): string {
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const b of content) {
    if (b && typeof b === "object") {
      if (b.type === "thinking" && typeof b.thinking === "string") parts.push(b.thinking);
    }
  }
  return parts.join("").trim();
}
```

### 5.3 并入 TimelineItem

`ThinkingRun` 加可选字段 `reasoning?: string`:

```typescript
interface ThinkingRun {
  steps: ThinkingStep[];   // 工具步骤(第一层)
  logs: ThinkingLog[];
  reasoning?: string;      // 模型原生推理(第二层)累积,无则 undefined
  done: boolean;
}
```

**接入时序(关键,对齐第一层 deriveTimeline 结构)**:第一层里 `run` 在遇到 prose(最终文本)时 `flushRun()`,而 reasoning 与 prose 常在**同一条最终 AI 消息**里(实测 `content=['thinking','text']`)。故在遍历每条 AI 消息时,**先抽 reasoning 累积到轮级变量,再判断 prose/flush**——否则最终消息的 reasoning 会随 flush 丢失。

具体:在 deriveTimeline 处理 AI 消息的分支里,tool_calls 累积之后、prose 判断之前,加:
```typescript
const r = extractReasoning(m.content);
if (r) reasoningParts.push(r);   // reasoningParts 是轮级数组,flushRun 时 join 赋给 run.reasoning
```
`flushRun` 里:`reasoning: reasoningParts.length ? reasoningParts.join("\n") : undefined`,并在 flush 后清空 `reasoningParts`(与现有 atoms/logs 清空同处)。一轮多条 AI 的多段 reasoning 按序拼接。

- 空 reasoning 轮:`reasoning` 为 undefined,渲染层不显示推理小节。
- 纯 reasoning 无工具轮:即便 steps 为空,只要 reasoning 非空也应 flush 出 thinking item(第一层 flushRun 条件是 `steps.length>0`,**第二层需放宽为 `steps.length>0 || reasoning 非空`**)。

### 5.4 渲染

`ThinkingAura` 加可选 `reasoning?: string` prop:非空时在步骤器上方渲染一个「💭 推理」小节(与「展开分析详情」同款折叠样式,复用现有 log 折叠区的视觉)。为空/undefined 时整个推理小节不渲染——**能力探测天然生效**:不支持 thinking 的模型 → `reasoning` 为空 → 不显示,零错误、零占位。

## 6. 安全

- thinking 块经 stream 到前端。虽是模型自身思考,但 summarized 摘要理论上可能复述检索到的敏感值。**表态**:thinking 与第一层工具 log 同级审视——不额外脱敏(summarized 是模型对推理的高层概括,不是工具原始 payload;且已开的 `display:"summarized"` 本身就是摘要而非全量 CoT)。但前端渲染 reasoning 时**不做 HTML 注入**(纯文本渲染,与现有气泡一致),防注入。
- config-center 侧:`LLM_THINKING` 非 secret,可明文存/显(与其它 LLM_* 模型配置同级,不涉及凭证)。

## 7. 测试与验收

**后端**:
- `_thinking_from_config`:provider≠anthropic → None;LLM_THINKING=off → None;默认/summarized → adaptive dict。
- `_build_chat_model` anthropic + thinking → temperature=1;anthropic 无 thinking → 0.7;openai/google 分支不受 thinking 参数影响。
- rubric `_strip_thinking`:带 thinking 的 ChatAnthropic → 返回无 thinking 的 copy 且 temperature=0.7;非 anthropic 原样返回;原实例不被污染。
- `LLM_THINKING` 在 `EDITABLE_KEYS` ∩ `_MODEL_POOL_KEYS`(否则热切失效)。
- 运行:`uv run pytest`。

**前端**:
- `extractReasoning`:thinking 块 → 提取文本;无块 → 空串;非数组 content → 空串。
- `deriveTimeline`:AI 消息带 thinking 块 → run.reasoning 非空;无 → undefined;reasoning 与 prose 同条最终消息时 reasoning **不随 flush 丢失**;纯 reasoning 无工具轮(steps 空)也 flush 出 thinking item;一轮多段 reasoning 按序拼接。
- 运行:`npm run test:unit` + tsc + eslint。

**端到端(Docker Compose 生产)**:
- 开 `LLM_THINKING=summarized`:发一轮出选题,思考链显示「💭 推理」小节(模型思考)+ 工具步骤,且 ai 正文气泡**不再混英文思考**。
- config-center 改 `LLM_THINKING=off` 保存 → 下一轮无推理小节(热切生效)。
- 观察 rubric 评分正常(结构化输出未被 thinking 干扰)。

## 8. 影响面

- 后端改:`models.py`(_build_chat_model 签名 + thinking/temperature 联动 + _thinking_from_config + 两条构造路径传入)、`config_center.py`(EDITABLE_KEYS 加 LLM_THINKING)、`data_foundation/internal_api.py`(_MODEL_POOL_KEYS 加 LLM_THINKING)、`rubric_model.py`(_resolve 套 _strip_thinking)。
- 前端改:`thinking-trace.ts`(extractReasoning + deriveTimeline 并入 reasoning + ThinkingRun.reasoning)、`ThinkingAura.tsx`(reasoning prop + 推理小节)。
- 配置:`.env` / config-center 新增 `LLM_THINKING`(默认 summarized)。
- 部署:改后端,需 `langgraph build` 重新出镜像 + `docker compose up -d`。
- provider 兼容:openai/google 全程不受影响(thinking 只在 anthropic 分支消费,前端无块则不显示)。
