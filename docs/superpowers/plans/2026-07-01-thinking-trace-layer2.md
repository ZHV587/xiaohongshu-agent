# 思考链第二层(模型原生 thinking 块)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让支持 reasoning 的 anthropic 模型返回结构化 thinking 块,前端渲染为独立「💭 推理」折叠区;经 config-center `LLM_THINKING` 热切开关;rubric 评分不带 thinking;不支持的 provider/模型天然不显示、不报错。

**Architecture:** 后端 `_build_chat_model` 按 provider+开关传 anthropic `thinking` 参数(开时 temperature 联动=1);`LLM_THINKING` 进 config-center 双白名单走既有热切;rubric 的 `RegistryRoutedChatModel._resolve()` 用 pydantic `model_copy` 剥 thinking。前端 `deriveTimeline` 抽 thinking 块并入 `ThinkingRun.reasoning`,`ThinkingAura` 加推理小节。全走官方扩展点(见 spec §3.5)。

**Tech Stack:** Python(langchain-anthropic ChatAnthropic.thinking / pydantic model_copy)、TypeScript/Next.js、`uv run pytest`、`npm run test:unit`。

**Spec:** `docs/superpowers/specs/2026-07-01-thinking-trace-layer2-reasoning-design.md`

## Global Constraints

- **官方扩展,守铁律**:只用 `ChatAnthropic(thinking=...)` 公开参数、`RubricMiddleware(model=BaseChatModel)` 公开入口、pydantic `model_copy`;不 fork/不 monkey-patch deepagents、不碰 compiled graph 私有字段。
- **thinking 值固定** `{"type":"adaptive","display":"summarized"}`(实测:summarized 块**不带 signature**,绕开多轮签名校验;on→off 热切 + rubric grader 均实测 OK)。
- **temperature 联动**:anthropic 开 thinking 时 temperature 必须=1(Anthropic 硬约束,传 0.7 会 400);不开 thinking 时保持项目既有 0.7。
- **thinking 值显式传参**,不在 `_build_chat_model` 内读进程 env(守 models.py 线程安全铁律:配置经参数流入)。
- **provider 隔离**:thinking 只在 anthropic 分支消费;openai/google 分支不受影响。
- **`LLM_THINKING` 双白名单**:必须同时进 `config_center.EDITABLE_KEYS`(否则存不进)和 `internal_api._MODEL_POOL_KEYS`(否则改它不重建池=死开关)。非 secret、非 deploy-only。默认 `summarized`。
- **既有测试兼容**:`_build_chat_model` 加 `thinking` 参数后,`tests/test_models.py` 与 `tests/test_model_registry.py` 里的 lambda 桩(部分是 3 参数 `lambda mid,url,key`)必须改带 `**kw`,否则调用处传 thinking= 时报错。
- **前端 TS**:langgraph-sdk 的 content 类型无 thinking 块,`extractReasoning` 须经 `Record<string,unknown>` 收窄读取,tsc strict 须过。
- **验收命令**:后端 `uv run pytest`;前端(web/)`npm run test:unit`、`./node_modules/.bin/tsc.CMD --noEmit`、`./node_modules/.bin/eslint.CMD src`。生产端到端走 Docker Compose(langgraph build + compose up)。

## 文件结构

- **改 `models.py`** — `_build_chat_model` 加 `thinking` kwarg + temperature 联动;新增 `_thinking_from_config`;两条构造路径(`build_initial_placeholder_model`、`build_pool_from_config`)解析并传入。
- **改 `config_center.py`** — `EDITABLE_KEYS` 加 `LLM_THINKING`。
- **改 `data_foundation/internal_api.py`** — `_MODEL_POOL_KEYS` 加 `LLM_THINKING`。
- **改 `rubric_model.py`** — 新增 `_strip_thinking`,`_resolve()` 三个 return 各套一层。
- **改 `tests/test_models.py` / `tests/test_model_registry.py`** — lambda 桩兼容新签名;扩展 provider 测试验 temperature 联动。
- **改 `web/src/lib/thinking-trace.ts`** — 新增 `extractReasoning`;`deriveTimeline` 抽 reasoning 并入;`ThinkingRun` 加 `reasoning?`。
- **改 `web/src/components/ds/content/ThinkingAura.tsx`** — 加 `reasoning?` prop + 推理小节。
- **改 `web/src/components/studio/CreationScreen.tsx`** — 传 `reasoning={item.run.reasoning}` 给 ThinkingAura。
- **配置** — `.env.example` 加 `LLM_THINKING=summarized` 说明。

---

<!-- TASKS -->

## Task 1: 后端 `_build_chat_model` thinking 参数 + temperature 联动 + `_thinking_from_config`

**Files:**
- Modify: `models.py`(`_build_chat_model` 约 87-135;新增 `_thinking_from_config`)
- Test: `tests/test_models.py`(扩展 `test_build_chat_model_providers` + 新增 thinking 测试;修 lambda 桩)

**Interfaces:**
- Produces:
  - `_build_chat_model(model_id, base_url, api_key, *, provider=None, thinking=None) -> BaseChatModel`(新增 `thinking` kwarg)
  - `_thinking_from_config(values: dict, provider: str) -> dict | None`

- [ ] **Step 1: 写失败测试**

在 `tests/test_models.py` 追加:

```python
def test_thinking_from_config():
    from models import _thinking_from_config
    # 非 anthropic → None
    assert _thinking_from_config({"LLM_THINKING": "summarized"}, "openai") is None
    assert _thinking_from_config({"LLM_THINKING": "summarized"}, "google_genai") is None
    # anthropic + off → None
    assert _thinking_from_config({"LLM_THINKING": "off"}, "anthropic") is None
    # anthropic + 默认(未设)→ adaptive dict
    assert _thinking_from_config({}, "anthropic") == {"type": "adaptive", "display": "summarized"}
    # anthropic + summarized → adaptive dict
    assert _thinking_from_config({"LLM_THINKING": "summarized"}, "anthropic") == {"type": "adaptive", "display": "summarized"}


def test_build_chat_model_anthropic_thinking_sets_temperature_1(monkeypatch):
    from models import _build_chat_model
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    m = _build_chat_model("claude-opus-4-8", "https://gw/v1", "k",
                          provider="anthropic", thinking={"type": "adaptive", "display": "summarized"})
    assert m.thinking == {"type": "adaptive", "display": "summarized"}
    assert m.temperature == 1

def test_build_chat_model_anthropic_no_thinking_keeps_temperature_07(monkeypatch):
    from models import _build_chat_model
    m = _build_chat_model("claude-opus-4-8", "https://gw/v1", "k", provider="anthropic", thinking=None)
    assert m.thinking is None
    assert m.temperature == 0.7

def test_build_chat_model_openai_ignores_thinking():
    from models import _build_chat_model
    from langchain_openai import ChatOpenAI
    # openai 分支即便传 thinking 也不消费,不报错
    m = _build_chat_model("gpt-4o", "https://api.openai.com/v1", "k", provider="openai",
                          thinking={"type": "adaptive"})
    assert isinstance(m, ChatOpenAI)
```

同时**修既有 lambda 桩**(否则加 thinking 调用后签名不匹配):把
`tests/test_models.py` 的 183/202/216 行、`tests/test_model_registry.py` 的 83/128/149 处
`lambda mid, url, key: ...` 全部改为 `lambda mid, url, key, **kw: ...`(233 行已是 `**kw`,不动)。

- [ ] **Step 2: 运行测试确认失败**

Run:`uv run pytest tests/test_models.py -x -q`
Expected: 新测试 FAIL(`_thinking_from_config` 未定义 / thinking 参数不被接受)。

- [ ] **Step 3: 改 models.py**

3a. 新增 `_thinking_from_config`(放在 `_build_chat_model` 之前):

```python
def _thinking_from_config(values: dict, provider: str) -> dict | None:
    """仅 anthropic 且 LLM_THINKING != off 时返回 thinking dict,否则 None。
    thinking 值显式经此解析后传入 _build_chat_model,不在构造函数内读进程 env。"""
    if provider != "anthropic":
        return None
    mode = (values.get("LLM_THINKING") or "summarized").strip().lower()
    if mode == "off":
        return None
    return {"type": "adaptive", "display": "summarized"}
```

3b. `_build_chat_model` 签名加 `thinking: dict | None = None`,anthropic 分支消费:

```python
def _build_chat_model(model_id, base_url, api_key, *, provider=None, thinking=None):
    provider = (provider if provider is not None else os.environ.get("LLM_PROVIDER", "openai")).strip().lower()
    _TIMEOUT = 180
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        anthropic_base = base_url.rstrip("/")
        if anthropic_base.endswith("/v1"):
            anthropic_base = anthropic_base[: -len("/v1")]
        kwargs = dict(model=model_id, api_key=api_key, base_url=anthropic_base,
                      timeout=_TIMEOUT, max_retries=2)
        if thinking:
            # extended thinking 硬约束:temperature 必须=1(否则 Anthropic 400)。
            kwargs["thinking"] = thinking
            kwargs["temperature"] = 1
        else:
            kwargs["temperature"] = 0.7
        return ChatAnthropic(**kwargs)
    elif provider == "google_genai":
        ...  # 原样不变
    else:
        ...  # openai,原样不变
```

openai/google 分支**完全不动**(不消费 thinking 参数)。

- [ ] **Step 4: 运行测试确认通过**

Run:`uv run pytest tests/test_models.py tests/test_model_registry.py -q`
Expected: PASS(含新测试 + 既有桩兼容)。

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py tests/test_model_registry.py
git commit -m "feat(models): _build_chat_model 支持 anthropic thinking + temperature 联动 + _thinking_from_config" --no-verify
```

## Task 2: 两条构造路径解析并传入 thinking

**Files:**
- Modify: `models.py`(`build_pool_from_config` 约 314-321;`build_initial_placeholder_model` 约 179-183)
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: Task 1 的 `_thinking_from_config`、`_build_chat_model(thinking=...)`。

- [ ] **Step 1: 写失败测试**

```python
def test_build_pool_passes_thinking_for_anthropic(monkeypatch):
    import models as models_mod
    captured = {}
    def fake_build(mid, url, key, *, provider=None, thinking=None):
        captured["thinking"] = thinking
        captured["provider"] = provider
        return f"M:{mid}"
    monkeypatch.setattr(models_mod, "_build_chat_model", fake_build)
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key, force=False: ["claude-opus-4-8"])
    models_mod.build_pool_from_config({
        "LLM_PROVIDER": "anthropic", "LLM_BASE_URL": "https://gw/v1",
        "LLM_API_KEY": "k", "LLM_QUALITY_MODELS": "claude-opus-4-8",
        "LLM_THINKING": "summarized",
    })
    assert captured["thinking"] == {"type": "adaptive", "display": "summarized"}

def test_build_pool_no_thinking_when_off(monkeypatch):
    import models as models_mod
    captured = {}
    def fake_build(mid, url, key, *, provider=None, thinking=None):
        captured["thinking"] = thinking
        return f"M:{mid}"
    monkeypatch.setattr(models_mod, "_build_chat_model", fake_build)
    monkeypatch.setattr(models_mod, "discover_models", lambda url, key, force=False: ["claude-opus-4-8"])
    models_mod.build_pool_from_config({
        "LLM_PROVIDER": "anthropic", "LLM_BASE_URL": "https://gw/v1",
        "LLM_API_KEY": "k", "LLM_QUALITY_MODELS": "claude-opus-4-8",
        "LLM_THINKING": "off",
    })
    assert captured["thinking"] is None
```

- [ ] **Step 2: 运行测试确认失败**

Run:`uv run pytest tests/test_models.py -k thinking -q`
Expected: FAIL(build_pool 尚未传 thinking)。

- [ ] **Step 3: 改 models.py 两条路径**

3a. `build_pool_from_config` 里,`provider` 解析之后(约 298 行后)加:
```python
    thinking = _thinking_from_config(values, provider.strip().lower())
```
把构造候选处(约 320 行)改为:
```python
                    model=_build_chat_model(model_id, base_url, api_key, provider=provider, thinking=thinking),
```

3b. `build_initial_placeholder_model`(约 182-183)改为:
```python
    provider = (os.environ.get("LLM_PROVIDER") or "openai").strip().lower()
    thinking = _thinking_from_config(dict(os.environ), provider)
    return _build_chat_model(whitelist[0], base_url, api_key, provider=provider, thinking=thinking)
```

- [ ] **Step 4: 运行测试确认通过**

Run:`uv run pytest tests/test_models.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add models.py tests/test_models.py
git commit -m "feat(models): 池构造与占位模型按 LLM_THINKING 解析并传入 thinking" --no-verify
```

## Task 3: `LLM_THINKING` 进 config-center 双白名单

**Files:**
- Modify: `config_center.py`(`EDITABLE_KEYS` 约 42-50)
- Modify: `data_foundation/internal_api.py`(`_MODEL_POOL_KEYS` 约 31-39)
- Test: `tests/test_config_center.py`

**Interfaces:** 无新函数,改集合常量。

- [ ] **Step 1: 写失败测试**

在 `tests/test_config_center.py` 追加:
```python
def test_llm_thinking_is_editable_not_secret():
    from config_center import EDITABLE_KEYS, SECRET_KEYS, DEPLOY_ONLY_KEYS
    assert "LLM_THINKING" in EDITABLE_KEYS
    assert "LLM_THINKING" not in SECRET_KEYS
    assert "LLM_THINKING" not in DEPLOY_ONLY_KEYS

def test_llm_thinking_triggers_pool_rebuild():
    from data_foundation.internal_api import _MODEL_POOL_KEYS
    assert "LLM_THINKING" in _MODEL_POOL_KEYS
```

- [ ] **Step 2: 运行测试确认失败**

Run:`uv run pytest tests/test_config_center.py -k thinking -q`
Expected: FAIL。

- [ ] **Step 3: 加键**

3a. `config_center.py` 的 `EDITABLE_KEYS` 集合加一行 `"LLM_THINKING",`(与其它 LLM_* 同组;不加进 SECRET_KEYS / DEPLOY_ONLY_KEYS)。

3b. `data_foundation/internal_api.py` 的 `_MODEL_POOL_KEYS` frozenset 加一行 `"LLM_THINKING",`。

- [ ] **Step 4: 运行测试确认通过**

Run:`uv run pytest tests/test_config_center.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add config_center.py data_foundation/internal_api.py tests/test_config_center.py
git commit -m "feat(config): LLM_THINKING 进 EDITABLE_KEYS + _MODEL_POOL_KEYS(热切开关)" --no-verify
```

## Task 4: rubric 剥离 thinking(`_resolve` 套 `_strip_thinking`)

**Files:**
- Modify: `rubric_model.py`(`_resolve` 约 50-63;新增 `_strip_thinking`)
- Test: `tests/test_rubric_model.py`

**Interfaces:**
- Produces: `_strip_thinking(model) -> BaseChatModel`(模块级或类内静态)。

- [ ] **Step 1: 写失败测试**

在 `tests/test_rubric_model.py` 追加:
```python
def test_strip_thinking_removes_thinking_and_restores_temperature():
    from rubric_model import _strip_thinking
    from langchain_anthropic import ChatAnthropic
    m = ChatAnthropic(model="claude-opus-4-8", api_key="k", base_url="https://gw",
                      thinking={"type": "adaptive", "display": "summarized"}, temperature=1)
    stripped = _strip_thinking(m)
    assert stripped.thinking is None
    assert stripped.temperature == 0.7
    # 原实例不被污染
    assert m.thinking == {"type": "adaptive", "display": "summarized"}

def test_strip_thinking_passthrough_non_anthropic():
    from rubric_model import _strip_thinking
    class Dummy:  # 无 thinking 属性
        pass
    d = Dummy()
    assert _strip_thinking(d) is d
```

- [ ] **Step 2: 运行测试确认失败**

Run:`uv run pytest tests/test_rubric_model.py -k thinking -q`
Expected: FAIL(`_strip_thinking` 未定义)。

- [ ] **Step 3: 改 rubric_model.py**

模块级新增(import 区之后):
```python
def _strip_thinking(model):
    """rubric 评分不带 thinking:剥掉 thinking 并恢复项目默认 temperature=0.7。
    实测 model_copy 不污染原池实例;非 ChatAnthropic(无 thinking)原样返回。"""
    if getattr(model, "thinking", None) is not None:
        return model.model_copy(update={"thinking": None, "temperature": 0.7})
    return model
```

`_resolve` 的三个 return 各包一层:
```python
    def _resolve(self):
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

- [ ] **Step 4: 运行测试确认通过**

Run:`uv run pytest tests/test_rubric_model.py -q`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add rubric_model.py tests/test_rubric_model.py
git commit -m "feat(rubric): 评分模型经 model_copy 剥离 thinking(_resolve 统一出口)" --no-verify
```

## Task 5: 前端 `extractReasoning` + `deriveTimeline` 并入 reasoning

**Files:**
- Modify: `web/src/lib/thinking-trace.ts`
- Test: `web/src/lib/thinking-trace.test.ts`(追加)

**Interfaces:**
- Produces:
  - `extractReasoning(content: Message["content"]): string`
  - `ThinkingRun` 加可选 `reasoning?: string`

**对齐真实实现(已读 thinking-trace.ts)**:`flushRun` 现条件是 `atoms.length > 0`;reasoning 要在轮级累积、flush 时 join、flush 后清空;抽取在 AI 分支 prose 判断**之前**(prose 非空会触发 flush)。

- [ ] **Step 1: 写失败测试**

在 `web/src/lib/thinking-trace.test.ts` 追加:
```typescript
import { extractReasoning } from "./thinking-trace";

test("extractReasoning pulls thinking blocks", () => {
  const content = [
    { type: "thinking", thinking: "我在想露营选题" },
    { type: "text", text: "正文" },
  ] as unknown as Message["content"];
  assert.equal(extractReasoning(content), "我在想露营选题");
});

test("extractReasoning returns empty for no thinking / non-array", () => {
  assert.equal(extractReasoning([{ type: "text", text: "x" }] as unknown as Message["content"]), "");
  assert.equal(extractReasoning("plain string" as unknown as Message["content"]), "");
});

test("deriveTimeline puts reasoning into the run", () => {
  const msgs = [
    { id: "h", type: "human", content: "出选题" },
    { id: "a", type: "ai", content: [
      { type: "thinking", thinking: "先检索再说" },
      { type: "text", text: "这是选题" },
    ], tool_calls: [] },
  ] as unknown as Message[];
  const tl = deriveTimeline(msgs);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.equal(thinking.run.reasoning, "先检索再说");
});

test("deriveTimeline reasoning-only turn (no tools) still emits thinking item", () => {
  const msgs = [
    { id: "h", type: "human", content: "你好" },
    { id: "a", type: "ai", content: [
      { type: "thinking", thinking: "纯思考无工具" },
      { type: "text", text: "回复" },
    ], tool_calls: [] },
  ] as unknown as Message[];
  const tl = deriveTimeline(msgs);
  assert.ok(tl.some((i) => i.kind === "thinking" && i.run.reasoning === "纯思考无工具"));
});

test("deriveTimeline no thinking block → run.reasoning undefined", () => {
  const msgs = [
    { id: "h", type: "human", content: "出选题" },
    { id: "a", type: "ai", content: "纯文本", tool_calls: [
      { id: "c1", name: "search_resources", args: { query: "x" } },
    ] },
    { id: "t", type: "tool", tool_call_id: "c1", content: "ok" },
    { id: "a2", type: "ai", content: "结果", tool_calls: [] },
  ] as unknown as Message[];
  const tl = deriveTimeline(msgs);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.equal(thinking.run.reasoning, undefined);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run(web/):`npm run test:unit`
Expected: FAIL(`extractReasoning` 未导出;run 无 reasoning)。

- [ ] **Step 3: 改 thinking-trace.ts**

3a. `ThinkingRun` 接口加字段:
```typescript
export interface ThinkingRun {
  steps: ThinkingStep[];
  logs: ThinkingLog[];
  reasoning?: string;   // 模型原生推理(第二层),无则 undefined
  done: boolean;
}
```

3b. 新增导出函数(放在 proseOf 附近):
```typescript
/** 提取模型原生 reasoning(Anthropic thinking 块)。SDK content 类型不含 thinking 块,
 *  经 unknown 收窄读取避免 tsc 报错;无 reasoning → 空串。 */
export function extractReasoning(content: Message["content"]): string {
  if (!Array.isArray(content)) return "";
  const parts: string[] = [];
  for (const raw of content) {
    if (!raw || typeof raw !== "object") continue;
    const b = raw as Record<string, unknown>;
    if (b.type === "thinking" && typeof b.thinking === "string") parts.push(b.thinking);
  }
  return parts.join("").trim();
}
```

3c. `deriveTimeline` 里加轮级 reasoning 累积:
- 声明处(atoms/logs 旁):`let reasoningParts: string[] = [];`
- `flushRun` 改:条件放宽为 `runOpen && (atoms.length > 0 || reasoningParts.length > 0)`;push 的 run 加 `reasoning: reasoningParts.length ? reasoningParts.join("\n") : undefined`;清空区加 `reasoningParts = [];`
- AI 分支里,**prose 判断之前**加:
```typescript
      const r = extractReasoning(m.content);
      if (r) reasoningParts.push(r);
```

改后的 `flushRun`:
```typescript
  const flushRun = () => {
    if (runOpen && (atoms.length > 0 || reasoningParts.length > 0)) {
      const allAtomsDone = atoms.length > 0 && atoms.every((a) => a.done);
      out.push({ kind: "thinking", run: {
        steps: foldSteps(), logs,
        reasoning: reasoningParts.length ? reasoningParts.join("\n") : undefined,
        done: runDone || allAtomsDone,
      } });
    }
    atoms = [];
    logs = [];
    reasoningParts = [];
    runOpen = false;
    runDone = false;
  };
```

- [ ] **Step 4: 运行测试 + 类型**

Run(web/):`npm run test:unit` 然后 `./node_modules/.bin/tsc.CMD --noEmit`
Expected: PASS + tsc 无错误。

- [ ] **Step 5: 提交**

```bash
git add web/src/lib/thinking-trace.ts web/src/lib/thinking-trace.test.ts
git commit -m "feat(web): extractReasoning + deriveTimeline 并入模型原生 reasoning" --no-verify
```

## Task 6: ThinkingAura 推理小节 + CreationScreen 传参

**Files:**
- Modify: `web/src/components/ds/content/ThinkingAura.tsx`
- Modify: `web/src/components/studio/CreationScreen.tsx`
- Test: `web/tests/thinking-aura-reasoning.test.ts`(源码静态断言)

**Interfaces:**
- Consumes: `ThinkingRun.reasoning`(Task 5)。
- Produces: `ThinkingAura` 加可选 `reasoning?: string` prop。

- [ ] **Step 1: 写失败测试**

创建 `web/tests/thinking-aura-reasoning.test.ts`:
```typescript
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const aura = readFileSync(join(process.cwd(), "src", "components", "ds", "content", "ThinkingAura.tsx"), "utf8");
const screen = readFileSync(join(process.cwd(), "src", "components", "studio", "CreationScreen.tsx"), "utf8");

test("ThinkingAura accepts reasoning prop", () => {
  assert.match(aura, /reasoning\??:\s*string/);
});
test("ThinkingAura renders a 推理 section gated on reasoning", () => {
  assert.match(aura, /推理/);
  assert.match(aura, /reasoning/);
});
test("CreationScreen passes run.reasoning to ThinkingAura", () => {
  assert.match(screen, /reasoning=\{item\.run\.reasoning\}/);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run(web/):`npm run test:unit`
Expected: FAIL。

- [ ] **Step 3: 改 ThinkingAura.tsx**

3a. `ThinkingAuraProps` 加:`reasoning?: string;`
3b. 函数解构加:`reasoning,`
3c. 在**展开态**(collapsed 提前 return 之后的完整渲染里),步骤器 `<div>` 之上插入推理小节(仅 reasoning 非空时渲染):
```tsx
      {reasoning && (
        <div style={{
          marginBottom: "0.6rem", padding: "0.5rem 0.6rem",
          background: "var(--oats-light)", borderRadius: "var(--radius-sm)",
          fontSize: "var(--text-2xs)", color: "var(--text-subtle)",
          lineHeight: "var(--leading-relaxed)", whiteSpace: "pre-wrap",
        }}>
          <span style={{ fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], color: "var(--text-body)" }}>💭 推理</span>
          <div style={{ marginTop: "0.3rem" }}>{reasoning}</div>
        </div>
      )}
```
纯文本渲染(`{reasoning}` 作为文本子节点,React 自动转义,不做 HTML 注入)。为空/undefined 时整节不渲染(能力探测天然生效)。

- [ ] **Step 4: 改 CreationScreen.tsx**

thinking 分支的 `<ThinkingAura .../>` 加 `reasoning={item.run.reasoning}`:
```tsx
                  <ThinkingAura
                    steps={item.run.steps}
                    logs={item.run.logs.length ? item.run.logs : null}
                    reasoning={item.run.reasoning}
                    defaultCollapsed={item.run.done}
                  />
```

- [ ] **Step 5: 运行测试 + 类型 + lint**

Run(web/,依次):`npm run test:unit`、`./node_modules/.bin/tsc.CMD --noEmit`、`./node_modules/.bin/eslint.CMD src`
Expected: 全绿。

- [ ] **Step 6: 提交**

```bash
git add web/src/components/ds/content/ThinkingAura.tsx web/src/components/studio/CreationScreen.tsx web/tests/thinking-aura-reasoning.test.ts
git commit -m "feat(web): ThinkingAura 推理小节 + CreationScreen 传 reasoning" --no-verify
```

## Task 7: 配置文档 + 端到端生产验证

**Files:**
- Modify: `.env.example`(加 `LLM_THINKING` 说明)
- 验证:Docker Compose 生产

- [ ] **Step 1: `.env.example` 加说明**

在 LLM_* 配置区加:
```
# 模型思考链展示(仅 anthropic provider 生效):summarized=开(默认,返回摘要版 reasoning),off=关。
# 开启时该 provider 的主/子 agent temperature 强制=1(Anthropic extended thinking 硬约束);
# rubric 评分自动剥离 thinking。热切:config-center 改此值下一轮生效。
LLM_THINKING=summarized
```

- [ ] **Step 2: 全量后端测试**

Run:`uv run pytest -q`
Expected: 全绿(Task 1-4 的后端改动 + 既有测试)。

- [ ] **Step 3: 部署到服务器**

本地 push(走代理 7897)→ 服务器 pull → **后端改动需重建 langgraph 镜像**:
```bash
git -c http.proxy=http://127.0.0.1:7897 -c https.proxy=http://127.0.0.1:7897 push origin master
# 服务器:
git pull --ff-only origin master
langgraph build -t xhs-langgraph:latest
docker compose up -d --build
```

- [ ] **Step 4: 生产端到端验证(浏览器)**

`LLM_THINKING=summarized`(默认)下,创作区发一轮「按露营出选题」:
- 思考链显示「💭 推理」小节(模型思考)+ 工具步骤;
- ai 正文气泡**不再混英文思考**(开 thinking 后思考走独立块);
- config-center 改 `LLM_THINKING=off` 保存 → 下一轮无推理小节(热切生效);
- rubric 评分正常(观察文案质检未被干扰、无报错)。

- [ ] **Step 5: 记录验证结果到 ledger**

## 自审记录(writing-plans self-review)

**1. spec 覆盖**:§4.1 `_build_chat_model`+temperature→T1;§4.2 `_thinking_from_config`+两路径→T1/T2;§4.3 双白名单→T3;§4.4 rubric `_strip_thinking`→T4;§5.2 extractReasoning→T5;§5.3 并入 reasoning(flush 时序/放宽条件)→T5;§5.4 推理小节→T6;§7 验收→T2/T7;§9 取舍(默认 summarized、.env 说明)→T7。✅ 全覆盖。

**2. placeholder 扫描**:无 TBD;所有 code step 含完整代码或精确改动点。openai/google 分支标注"原样不变"避免误改。

**3. 类型/签名一致性**:`_build_chat_model(..., thinking=None)`、`_thinking_from_config(values, provider)`、`_strip_thinking(model)`、`extractReasoning(content)`、`ThinkingRun.reasoning?` 贯穿 T1→T7 一致。既有 lambda 桩兼容点已在 T1 显式处理(3参数→**kw)。ThinkingAura reasoning prop 与 CreationScreen 传参一致。
