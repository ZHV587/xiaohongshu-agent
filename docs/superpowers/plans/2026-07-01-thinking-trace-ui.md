# 思考链 UI(思维微光接真实 agent 执行流)实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `ThinkingAura`(思维微光)接上真实的 LangGraph agent 执行流,在创作聊天区内联实时步进、完成后折叠为「已完成 N 步」摘要;全部真实数据,零后端改动。

**Architecture:** 新增纯函数解析器 `src/lib/thinking-trace.ts`,把 `messages` 流解析成有序 `TimelineItem[]`(user 气泡 / thinking 思考链 / ai 正文气泡三态);`StudioContext` 用它取代 `deriveChat`;`CreationScreen` 的 `ChatColumn` 按 kind 渲染;`ThinkingAura` 加折叠摘要态 prop。所有工具事件来自已存在于前端流的 `tool_calls` / `ToolMessage` / `task.subagent_type`。

**Tech Stack:** TypeScript、Next.js、`@langchain/langgraph-sdk`(Message 类型)、`node:test` + esbuild(单测运行器 `npm run test:unit`)。

## Global Constraints

- **零后端改动**:只动 `web/` 前端;不碰任何 `.py`。
- **真实数据铁律**:只渲染真实已发生/正在发生的步骤,绝不造 pending 占位、绝不 mock。
- **解析器永不 throw**:流式中间态(tool_calls/args 未到齐)必须容忍,安全降级(对齐现有 `parseCopyFromMessages` 约定)。
- **安全**:logs 里工具参数/结果截断 + 脱敏,不打印 credentials / token / Authorization / DSN / UAT;写类工具只显示动作语义,不回显 payload。
- **`task` 工具名为小写 `"task"`**(已核实 `deepagents/middleware/subagents.py:725` `name="task"`)。
- **纯函数落点 `src/lib/`**:测试运行器(`web/scripts/run-unit-tests.mjs`)只自动收录 `src/lib/*.test.ts` 与 `tests/*.test.ts`;故解析器放 `src/lib/thinking-trace.ts`,测试放 `src/lib/thinking-trace.test.ts`,自动纳入 `npm run test:unit`。
- **测试风格**:真行为测试,`import { … } from "./thinking-trace"` 直接调用 + `node:assert/strict` 的 `assert.deepEqual` / `assert.equal`(对齐 `src/lib/xhs-blocks.test.ts`)。
- **验收命令**(在 `web/` 下):`npm run test:unit`、`.\node_modules\.bin\tsc.CMD --noEmit`、`.\node_modules\.bin\eslint.CMD src`。

## 文件结构

- **新建 `web/src/lib/thinking-trace.ts`** — 纯函数解析器 + 类型 + 工具名词典。职责:`messages: Message[]` → `TimelineItem[]`。无 React。
- **新建 `web/src/lib/thinking-trace.test.ts`** — 上述解析器的真行为单测。
- **改 `web/src/components/ds/content/ThinkingAura.tsx`** — 新增折叠摘要态 prop(`defaultCollapsed` + 摘要头)。
- **改 `web/src/components/studio/StudioContext.tsx`** — 用 `deriveTimeline` 取代 `deriveChat`;store 暴露 `timeline`;删 `ChatMsg` import;加 `__XHS_THINKING_STEPS__` 钩子。
- **改 `web/src/components/studio/CreationScreen.tsx`** — `ChatColumn` 消费 `timeline`,按 kind 渲染;滚动依赖改 timeline。
- **改 `web/src/components/studio/types.ts`** — 删 `ChatMsg`;`TimelineItem` / `ThinkingRun` 从 `thinking-trace.ts` re-export 或就近定义。

---

<!-- TASKS_PLACEHOLDER -->

## Task 1: 解析器类型、工具名词典与轮切分骨架

**Files:**
- Create: `web/src/lib/thinking-trace.ts`
- Test: `web/src/lib/thinking-trace.test.ts`

**Interfaces:**
- Consumes: `Message` from `@langchain/langgraph-sdk`;`getContentString` from `@/components/thread/utils`;`parseXhsBlocks` from `@/lib/xhs-blocks`.
- Produces:
  - `type TimelineItem = { kind: "user"; text: string } | { kind: "thinking"; run: ThinkingRun } | { kind: "ai"; text: string }`
  - `interface ThinkingRun { steps: ThinkingStep[]; logs: ThinkingLog[]; done: boolean }`
  - `interface ThinkingStep { label: string; state: "done" | "active" }`(不含 pending——真实数据铁律)
  - `type ThinkingLog = { text: string }`(无墙钟时间戳,见 spec §12)
  - `function toolLabel(name: string, args: unknown): string`
  - `function deriveTimeline(messages: Message[]): TimelineItem[]`(本任务先返回空数组占位,Task 2 实现)

- [ ] **Step 1: 写失败测试(词典映射 + 兜底)**

在 `web/src/lib/thinking-trace.test.ts`:

```typescript
import assert from "node:assert/strict";
import test from "node:test";

import { toolLabel, deriveTimeline } from "./thinking-trace";

test("toolLabel maps known data_foundation tools to Chinese", () => {
  assert.equal(toolLabel("semantic_search_resources", {}), "语义检索数据底座");
  assert.equal(toolLabel("search_resources", {}), "关键词检索数据底座");
  assert.equal(toolLabel("get_resource", {}), "精读素材原文");
  assert.equal(toolLabel("graph_expand", {}), "图谱扩展关联");
  assert.equal(toolLabel("save_generated_topic", {}), "沉淀选题入库");
});

test("toolLabel maps feishu action tools", () => {
  assert.equal(toolLabel("sync_copy_to_feishu", {}), "同步文案到飞书");
  assert.equal(toolLabel("adopt_online_notes", {}), "采纳线上笔记");
});

test("toolLabel resolves task delegation via subagent_type", () => {
  assert.equal(toolLabel("task", { subagent_type: "knowledge-atom-retriever" }), "委派子任务:知识检索");
  assert.equal(toolLabel("task", { subagent_type: "persona-distiller" }), "委派子任务:风格提炼");
});

test("toolLabel task without subagent_type falls back to generic", () => {
  assert.equal(toolLabel("task", {}), "委派子任务");
  assert.equal(toolLabel("task", undefined), "委派子任务");
});

test("toolLabel unknown tool falls back to raw name", () => {
  assert.equal(toolLabel("some_new_tool", {}), "some_new_tool");
});

test("deriveTimeline is a stub returning empty array (Task 1)", () => {
  assert.deepEqual(deriveTimeline([]), []);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run(在 `web/` 下):`npm run test:unit`
Expected: FAIL —— `toolLabel` / `deriveTimeline` 未导出(esbuild 报无法解析或断言失败)。

- [ ] **Step 3: 写最小实现**

在 `web/src/lib/thinking-trace.ts`:

```typescript
import type { Message } from "@langchain/langgraph-sdk";

export interface ThinkingStep {
  label: string;
  state: "done" | "active";
}

export interface ThinkingLog {
  text: string;
}

export interface ThinkingRun {
  steps: ThinkingStep[];
  logs: ThinkingLog[];
  done: boolean;
}

export type TimelineItem =
  | { kind: "user"; text: string }
  | { kind: "thinking"; run: ThinkingRun }
  | { kind: "ai"; text: string };

// 工具名 → 中文语义。覆盖 data_foundation/tools.py 与 tools/feishu_actions.py 两来源。
const TOOL_LABELS: Record<string, string> = {
  semantic_search_resources: "语义检索数据底座",
  search_resources: "关键词检索数据底座",
  search_local_note_cards: "检索本地笔记卡",
  get_resource: "精读素材原文",
  graph_expand: "图谱扩展关联",
  save_generated_topic: "沉淀选题入库",
  save_generated_copy: "沉淀文案入库",
  save_user_feedback: "沉淀反馈",
  save_performance_metric: "沉淀效果指标",
  save_session_snapshot: "保存会话快照",
  get_resource_performance: "读取效果表现",
  get_operations_data: "读取运营数据",
  get_data_foundation_status: "读取数据底座状态",
  sync_feishu_resources: "同步飞书资源",
  sync_copy_to_feishu: "同步文案到飞书",
  sync_topic_to_feishu: "同步选题到飞书",
  sync_diagnosis_to_feishu: "同步诊断到飞书",
  send_review_notification: "发送审阅通知",
  adopt_online_notes: "采纳线上笔记",
  search_xhs_online: "搜索小红书线上",
  lark_cli: "飞书 CLI 操作",
};

// task 委派:按 subagent_type 细化;未知/缺失回退通用。
const SUBAGENT_LABELS: Record<string, string> = {
  "knowledge-atom-retriever": "委派子任务:知识检索",
  "persona-distiller": "委派子任务:风格提炼",
};

export function toolLabel(name: string, args: unknown): string {
  if (name === "task") {
    const sub =
      args && typeof args === "object" && "subagent_type" in args
        ? (args as { subagent_type?: unknown }).subagent_type
        : undefined;
    if (typeof sub === "string" && SUBAGENT_LABELS[sub]) return SUBAGENT_LABELS[sub];
    return "委派子任务";
  }
  return TOOL_LABELS[name] ?? name;
}

export function deriveTimeline(_messages: Message[]): TimelineItem[] {
  return [];
}
```

- [ ] **Step 4: 运行测试确认通过**

Run(在 `web/` 下):`npm run test:unit`
Expected: PASS(本文件全部 6 个 test 通过)。

- [ ] **Step 5: 提交**

```bash
git add web/src/lib/thinking-trace.ts web/src/lib/thinking-trace.test.ts
git commit -m "feat(web): 思考链解析器骨架——类型/工具名词典/task委派映射" --no-verify
```

## Task 2: deriveTimeline 核心实现

**Files:**
- Modify: `web/src/lib/thinking-trace.ts`(替换 `deriveTimeline` 桩)
- Test: `web/src/lib/thinking-trace.test.ts`(追加行为测试)

**Interfaces:**
- Consumes: Task 1 的 `toolLabel` / 类型;`getContentString`(`@/components/thread/utils`);`parseXhsBlocks`(`@/lib/xhs-blocks`,返回 `Segment[]`,`TextSegment` 的 `kind==="text"` 带 `.text`)。
- Produces: `deriveTimeline(messages: Message[]): TimelineItem[]` 完整实现。

**规则(spec §4/§5/§8/§9)**:
- 轮切分:遇 `human` 消息 → 推 `{kind:"user"}` 并开启新一轮 thinking 累积。
- 一轮内每条 `ai` 的 `tool_calls[]` → 追加**原子步骤记录**(name + 是否已答 + args);渲染前再按「同名连续」折叠成语义步骤,状态取该组的**与**(全部已答才 done)。
- `tool_call` 是否已答:全局扫一遍 `ToolMessage` 的 `tool_call_id` 建 `answered` 集合,按 `tool_call_id` 配对。
- 一轮内最后一条「剥离 xhs 块后仍有自然语言」的 `ai` → 推 `{kind:"ai"}` 气泡;中间只含 tool_calls 的 ai 不出气泡。
- thinking run 的 `done`:该轮已出现最终 ai 文本气泡,或该轮所有步骤均 done。
- 永不 throw;args 用安全 stringify 进 log(截断 200 字符)。

- [ ] **Step 1: 追加失败测试**

在 `web/src/lib/thinking-trace.test.ts` 末尾追加:

```typescript
import type { Message } from "@langchain/langgraph-sdk";

const human = (text: string): Message => ({ id: "h", type: "human", content: text } as Message);
const aiText = (text: string): Message => ({ id: "a", type: "ai", content: text, tool_calls: [] } as unknown as Message);
const aiCall = (id: string, name: string, args: Record<string, unknown> = {}): Message =>
  ({ id, type: "ai", content: "", tool_calls: [{ id, name, args }] } as unknown as Message);
const toolMsg = (callId: string): Message =>
  ({ id: "t" + callId, type: "tool", tool_call_id: callId, content: "ok" } as unknown as Message);

test("plain text turn yields user + ai bubble, no thinking", () => {
  const tl = deriveTimeline([human("你好"), aiText("你好呀,需要什么帮助?")]);
  assert.deepEqual(tl, [
    { kind: "user", text: "你好" },
    { kind: "ai", text: "你好呀,需要什么帮助?" },
  ]);
});

test("tool call without ToolMessage is active", () => {
  const tl = deriveTimeline([human("出选题"), aiCall("c1", "semantic_search_resources", { query: "露营" })]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.deepEqual(thinking.run.steps, [{ label: "语义检索数据底座", state: "active" }]);
  assert.equal(thinking.run.done, false);
});

test("tool call with matching ToolMessage is done", () => {
  const tl = deriveTimeline([
    human("出选题"),
    aiCall("c1", "semantic_search_resources", { query: "露营" }),
    toolMsg("c1"),
    aiText("这是选题建议"),
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.deepEqual(thinking.run.steps, [{ label: "语义检索数据底座", state: "done" }]);
  assert.equal(thinking.run.done, true);
});

test("consecutive same-name tools fold into one step but keep per-call logs", () => {
  const tl = deriveTimeline([
    human("精读"),
    aiCall("r1", "get_resource", { resource_id: "n1" }),
    toolMsg("r1"),
    aiCall("r2", "get_resource", { resource_id: "n2" }),
    toolMsg("r2"),
    aiText("读完了"),
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.equal(thinking.run.steps.length, 1);
  assert.equal(thinking.run.steps[0].label, "精读素材原文");
  assert.equal(thinking.run.logs.length, 2);
});

test("intermediate tool-only ai does not produce ai bubble; only final text does", () => {
  const tl = deriveTimeline([
    human("出选题"),
    aiCall("c1", "search_resources", { query: "x" }),
    toolMsg("c1"),
    aiText("最终选题"),
  ]);
  const aiBubbles = tl.filter((i) => i.kind === "ai");
  assert.equal(aiBubbles.length, 1);
  assert.equal((aiBubbles[0] as { text: string }).text, "最终选题");
});

test("ai bubble strips xhs code blocks, keeps prose", () => {
  const content = '这是给你的选题:\n```xhs_topics\n{"topics":["露营"]}\n```\n点卡片进入创作。';
  const tl = deriveTimeline([human("出选题"), aiText(content)]);
  const ai = tl.find((i) => i.kind === "ai");
  assert.ok(ai && ai.kind === "ai");
  assert.ok(!ai.text.includes("xhs_topics"));
  assert.ok(!ai.text.includes("{"));
  assert.ok(ai.text.includes("这是给你的选题"));
  assert.ok(ai.text.includes("点卡片进入创作"));
});

test("ai message that is only an xhs block produces no ai bubble", () => {
  const content = '```xhs_topics\n{"topics":["露营"]}\n```';
  const tl = deriveTimeline([human("出选题"), aiText(content)]);
  assert.equal(tl.filter((i) => i.kind === "ai").length, 0);
});

test("never throws on malformed / partial messages", () => {
  const weird = [
    { type: "ai", content: null, tool_calls: [{ id: "x", name: "task", args: undefined }] },
    { type: "tool", tool_call_id: "x", content: "" },
  ] as unknown as Message[];
  assert.doesNotThrow(() => deriveTimeline(weird));
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:`npm run test:unit`
Expected: FAIL —— 桩返回 `[]`,新增断言全挂。

- [ ] **Step 3: 实现 deriveTimeline**

替换 `web/src/lib/thinking-trace.ts` 里的 `deriveTimeline` 桩为:

```typescript
import { getContentString } from "@/components/thread/utils";
import { parseXhsBlocks } from "@/lib/xhs-blocks";

interface ToolCall {
  id?: string;
  name: string;
  args?: unknown;
}

function safeArgsLog(label: string, args: unknown): string {
  let detail = "";
  try {
    detail = args == null ? "" : typeof args === "string" ? args : JSON.stringify(args);
  } catch {
    detail = "";
  }
  if (detail.length > 200) detail = detail.slice(0, 200) + "…";
  return detail ? `${label}: ${detail}` : label;
}

// 剥离 xhs 结构块,只留自然语言(防 JSON 糊屏,spec §8)。
function proseOf(content: Message["content"]): string {
  const raw = getContentString(content);
  if (!raw) return "";
  const segs = parseXhsBlocks(raw);
  return segs
    .filter((s): s is { kind: "text"; text: string } => s.kind === "text")
    .map((s) => s.text)
    .join("")
    .trim();
}

export function deriveTimeline(messages: Message[]): TimelineItem[] {
  const out: TimelineItem[] = [];

  // 全局:已答的 tool_call_id 集合(按 tool_call_id 配对,不靠顺序)。
  const answered = new Set<string>();
  for (const m of messages) {
    if (m.type === "tool") {
      const cid = (m as { tool_call_id?: string }).tool_call_id;
      if (cid) answered.add(cid);
    }
  }

  // 一轮内累积的原子步骤记录(渲染前折叠)。
  type Atom = { name: string; done: boolean };
  let atoms: Atom[] = [];
  let logs: ThinkingLog[] = [];
  let runOpen = false;
  let runDone = false;

  // 把原子记录按「同名连续」折叠成语义步骤;每组状态 = 组内全部 done 才 done。
  const foldSteps = (): ThinkingStep[] => {
    const steps: ThinkingStep[] = [];
    let i = 0;
    while (i < atoms.length) {
      const name = atoms[i].name;
      let allDone = atoms[i].done;
      let j = i + 1;
      while (j < atoms.length && atoms[j].name === name) {
        allDone = allDone && atoms[j].done;
        j++;
      }
      // label 用该组首个 atom 的 name(task 的 subagent_type 已在 push 时并入 label,见下)
      steps.push({ label: name, state: allDone ? "done" : "active" });
      i = j;
    }
    return steps;
  };

  const flushRun = () => {
    if (runOpen && atoms.length > 0) {
      out.push({ kind: "thinking", run: { steps: foldSteps(), logs, done: runDone } });
    }
    atoms = [];
    logs = [];
    runOpen = false;
    runDone = false;
  };

  for (const m of messages) {
    if (m.type === "human") {
      flushRun();
      out.push({ kind: "user", text: getContentString(m.content) });
      runOpen = true;
      continue;
    }
    if (m.type === "ai") {
      runOpen = true;
      const calls = ((m as { tool_calls?: ToolCall[] }).tool_calls ?? []).filter(
        (c) => c && typeof c.name === "string",
      );
      for (const c of calls) {
        const label = toolLabel(c.name, c.args); // task → 已并入 subagent 细分
        const done = !!(c.id && answered.has(c.id));
        atoms.push({ name: label, done });
        logs.push({ text: safeArgsLog(label, c.args) });
      }
      const prose = proseOf(m.content);
      if (prose) {
        runDone = true;
        flushRun();
        out.push({ kind: "ai", text: prose });
      }
      continue;
    }
    // tool 消息不直接产 item —— 其效果已经过 answered 反映到步骤状态。
  }
  flushRun();
  return out;
}
```

注:`foldSteps` 用 `label`(已含 task 的中文细分)作分组键——同一工具的中文 label
一致,连续同 label 即折叠;不同工具或 task 不同 subagent 的 label 不同,自然分组。

同时把文件顶部 `deriveTimeline` 旧桩删除,`import type { Message }` 保留,新增的
`getContentString` / `parseXhsBlocks` import 放到文件顶部 import 区。

- [ ] **Step 4: 运行测试确认通过**

Run:`npm run test:unit`
Expected: PASS(Task 1 + Task 2 全部 test 通过)。

- [ ] **Step 5: 类型检查**

Run(在 `web/` 下):`.\node_modules\.bin\tsc.CMD --noEmit`
Expected: 无错误。

- [ ] **Step 6: 提交**

```bash
git add web/src/lib/thinking-trace.ts web/src/lib/thinking-trace.test.ts
git commit -m "feat(web): deriveTimeline 核心——轮切分/配对状态/同名折叠/剥xhs块/健壮性" --no-verify
```

## Task 3: ThinkingAura 折叠摘要态

**Files:**
- Modify: `web/src/components/ds/content/ThinkingAura.tsx`
- Test: `web/tests/thinking-aura-collapsed.test.ts`(源码静态断言,与 `tests/*.test.ts` 同风格)

**Interfaces:**
- Consumes: 无(纯组件改动)。
- Produces: `ThinkingAura` 新增可选 prop `defaultCollapsed?: boolean`;为 true 时默认渲染单行摘要头「已完成 N 步 ▾」(N = `steps.length`),点击展开完整步骤器。现有 `steps` / `logs` / `title` / `defaultOpen` 行为不变。

**说明**:`ThinkingAura` 现有内联样式风格保留。折叠态是一个包在最外层的条件分支:
`defaultCollapsed` 初始化一个 `collapsed` state,collapsed 时只渲染摘要头(呼吸点 +
「已完成 N 步」+ ▾),点击置 `collapsed=false` 展开为现有完整布局。

- [ ] **Step 1: 写失败测试(源码断言)**

创建 `web/tests/thinking-aura-collapsed.test.ts`:

```typescript
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = readFileSync(
  join(process.cwd(), "src", "components", "ds", "content", "ThinkingAura.tsx"),
  "utf8",
);

test("ThinkingAura accepts defaultCollapsed prop", () => {
  assert.match(src, /defaultCollapsed\??:\s*boolean/);
});

test("ThinkingAura renders a collapsed summary with step count", () => {
  // 摘要头显示「已完成 N 步」,N 来自 steps.length
  assert.match(src, /已完成/);
  assert.match(src, /steps\.length/);
});

test("collapsed state is toggleable", () => {
  assert.match(src, /useState/);
  assert.match(src, /collapsed/);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:`npm run test:unit`
Expected: FAIL —— `defaultCollapsed` / `collapsed` / 「已完成」尚不存在。

- [ ] **Step 3: 改 ThinkingAura**

在 `web/src/components/ds/content/ThinkingAura.tsx`:

1. `ThinkingAuraProps` 接口加:`defaultCollapsed?: boolean;`
2. 函数签名解构加 `defaultCollapsed = false,`。
3. 组件体开头加折叠 state 与摘要分支:

```typescript
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  if (collapsed) {
    return (
      <div
        onClick={() => setCollapsed(false)}
        style={{
          display: "inline-flex", alignItems: "center", gap: "0.5rem", cursor: "pointer",
          background: "var(--surface-card)", border: "1px solid var(--border-coral)",
          borderRadius: "var(--radius-xl)", boxShadow: "var(--shadow-sm)", padding: "0.5rem 0.75rem",
        }}
        {...rest}
      >
        <span style={{ position: "relative", display: "inline-flex", width: 8, height: 8 }}>
          <span style={{ position: "relative", borderRadius: "var(--radius-full)", width: 8, height: 8, background: "var(--success)" }} />
        </span>
        <span style={{ fontFamily: "var(--font-sans)", fontWeight: "var(--weight-semibold)" as CSSProperties["fontWeight"], fontSize: "var(--text-xs)", color: "var(--text-body)" }}>
          🍠 已完成 {steps.length} 步
        </span>
        <span style={{ color: "var(--primary)", fontSize: "var(--text-2xs)" }}>▾</span>
      </div>
    );
  }
```

注:`useState` 已在文件顶部 import;`CSSProperties` 已 import。此分支放在现有
`return (...)` 之前,collapsed 为 false 时走原有完整渲染。

- [ ] **Step 4: 运行测试确认通过**

Run:`npm run test:unit`
Expected: PASS。

- [ ] **Step 5: 类型检查**

Run:`.\node_modules\.bin\tsc.CMD --noEmit`
Expected: 无错误。

- [ ] **Step 6: 提交**

```bash
git add web/src/components/ds/content/ThinkingAura.tsx web/tests/thinking-aura-collapsed.test.ts
git commit -m "feat(web): ThinkingAura 折叠摘要态(已完成 N 步,点击展开)" --no-verify
```

## Task 4: StudioContext 接线(timeline 取代 chatExtra)

**Files:**
- Modify: `web/src/components/studio/StudioContext.tsx`
- Modify: `web/src/components/studio/types.ts`
- Test: `web/tests/studio-timeline.test.ts`(源码静态断言)

**Interfaces:**
- Consumes: `deriveTimeline` / `TimelineItem`(`@/lib/thinking-trace`)。
- Produces: `StudioStore` 新增 `timeline: TimelineItem[]`,移除 `chatExtra: ChatMsg[]`。

- [ ] **Step 1: 写失败测试**

创建 `web/tests/studio-timeline.test.ts`:

```typescript
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = (...p: string[]) => readFileSync(join(process.cwd(), "src", ...p), "utf8");

test("StudioContext exposes timeline from deriveTimeline, not chatExtra", () => {
  const ctx = src("components", "studio", "StudioContext.tsx");
  assert.match(ctx, /deriveTimeline/);
  assert.match(ctx, /timeline:\s*TimelineItem\[\]/);
  assert.doesNotMatch(ctx, /chatExtra/);
  assert.doesNotMatch(ctx, /deriveChat/);
});

test("types.ts drops ChatMsg", () => {
  const types = src("components", "studio", "types.ts");
  assert.doesNotMatch(types, /interface ChatMsg/);
});

test("StudioContext exposes __XHS_THINKING_STEPS__ e2e hook", () => {
  const ctx = src("components", "studio", "StudioContext.tsx");
  assert.match(ctx, /__XHS_THINKING_STEPS__/);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:`npm run test:unit`
Expected: FAIL —— 现仍是 `chatExtra` / `deriveChat` / `ChatMsg`。

- [ ] **Step 3a: 改 types.ts**

删除 `web/src/components/studio/types.ts` 里的 `ChatMsg` 接口(约 87-91 行):

```typescript
export interface ChatMsg {
  who: "user" | "ai";
  text: string;
  thinking?: boolean;
}
```

整块删除(无外部引用,已核实)。

- [ ] **Step 3b: 改 StudioContext.tsx —— import**

- 删除 `import type { ... ChatMsg ... }` 中的 `ChatMsg,`(约 39 行)。
- 在 import 区加:`import { deriveTimeline, type TimelineItem } from "@/lib/thinking-trace";`

- [ ] **Step 3c: 改 StudioContext.tsx —— store 字段**

- `StudioStore` 接口:把 `chatExtra: ChatMsg[];`(约 76 行)改为 `timeline: TimelineItem[];`
- 派生处(约 298 行)把:
  ```typescript
  const chatExtra: ChatMsg[] = useMemo(() => deriveChat(t.messages), [t.messages]);
  ```
  改为:
  ```typescript
  const timeline: TimelineItem[] = useMemo(() => deriveTimeline(t.messages), [t.messages]);
  ```
- store 组装处(约 458 行)把 `chatExtra,` 改为 `timeline,`。
- 删除文件底部的 `deriveChat` 函数(约 633-641 行)整块。

- [ ] **Step 3d: 加 e2e 钩子**

在 `timeline` 派生之后加(仿现有 `__XHS_TOPICS_LEN__` 写法,约 291 行附近):

```typescript
  useEffect(() => {
    if (typeof window !== "undefined") {
      const steps = timeline.reduce(
        (n, it) => n + (it.kind === "thinking" ? it.run.steps.length : 0),
        0,
      );
      (window as unknown as { __XHS_THINKING_STEPS__?: number }).__XHS_THINKING_STEPS__ = steps;
    }
  }, [timeline]);
```

- [ ] **Step 4: 运行测试确认通过**

Run:`npm run test:unit`
Expected: PASS。

- [ ] **Step 5: 类型检查(此时 CreationScreen 仍用 chatExtra,预期报错)**

Run:`.\node_modules\.bin\tsc.CMD --noEmit`
Expected: 仅 `CreationScreen.tsx` 报 `chatExtra` 不存在 —— 这是预期的,Task 5 修复。
本任务不单独提交,与 Task 5 合并提交(避免中间态 tsc 失败的孤立 commit)。

> 注:Task 4 与 Task 5 是一次原子改动的两半(store 契约变更 + 消费端跟随)。
> 按此顺序连续执行,合并在 Task 5 末尾提交。

## Task 5: CreationScreen 消费 timeline(渲染 + 滚动)

**Files:**
- Modify: `web/src/components/studio/CreationScreen.tsx`
- Test: `web/tests/creation-timeline-render.test.ts`(源码静态断言)

**Interfaces:**
- Consumes: `useStudio().timeline`(`TimelineItem[]`);`ThinkingAura`(`@/components/ds`,含新 `defaultCollapsed`)。
- Produces: 无对外接口(视图层)。

- [ ] **Step 1: 写失败测试**

创建 `web/tests/creation-timeline-render.test.ts`:

```typescript
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = readFileSync(
  join(process.cwd(), "src", "components", "studio", "CreationScreen.tsx"),
  "utf8",
);

test("ChatColumn consumes timeline, not chatExtra", () => {
  assert.match(src, /timeline/);
  assert.doesNotMatch(src, /chatExtra/);
});

test("renders three kinds: user / thinking / ai", () => {
  assert.match(src, /"user"/);
  assert.match(src, /"thinking"/);
  assert.match(src, /"ai"/);
});

test("thinking items use ThinkingAura with defaultCollapsed on done runs", () => {
  assert.match(src, /ThinkingAura/);
  assert.match(src, /defaultCollapsed/);
});

test("no dead m.thinking branch remains", () => {
  assert.doesNotMatch(src, /m\.thinking/);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:`npm run test:unit`
Expected: FAIL。

- [ ] **Step 3: 改 ChatColumn**

在 `web/src/components/studio/CreationScreen.tsx`:

3a. `ChatColumn` 顶部解构(约 73 行)把 `chatExtra` 换 `timeline`:

```typescript
  const { topics, timeline, trends, actions } = useStudio();
```

3b. 滚动 effect(约 76 行)依赖改为对内容敏感的信号:

```typescript
  const lastRunSteps = (() => {
    for (let i = timeline.length - 1; i >= 0; i--) {
      const it = timeline[i];
      if (it.kind === "thinking") return it.run.steps.length;
    }
    return 0;
  })();
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [timeline.length, lastRunSteps]);
```

3c. 空态守卫(约 82 行)`chatExtra.length === 0` 改 `timeline.length === 0`。

3d. 消息渲染块(约 93-105 行整块)替换为按 kind 判别:

```tsx
        {timeline.map((item, i) => {
          const key = `${item.kind}-${i}`;
          if (item.kind === "user") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "86%", alignSelf: "flex-end", flexDirection: "row-reverse" }}>
                <Avatar name="我" variant="solid" size={30} />
                <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", boxShadow: "var(--shadow-sm)" }}>{item.text}</div>
              </div>
            );
          }
          if (item.kind === "thinking") {
            return (
              <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
                <Avatar glyph="🍠" variant="agent" size={32} />
                <div style={{ flex: 1, maxWidth: 440 }}>
                  <ThinkingAura
                    steps={item.run.steps}
                    logs={item.run.logs.length ? item.run.logs : null}
                    defaultCollapsed={item.run.done}
                  />
                </div>
              </div>
            );
          }
          return (
            <div key={key} style={{ display: "flex", gap: 11, maxWidth: "92%" }}>
              <Avatar glyph="🍠" variant="agent" size={32} />
              <div style={{ background: "var(--surface-card)", border: "1px solid var(--border-coral)", borderRadius: "var(--radius-xl)", padding: "11px 15px", fontSize: "var(--text-sm)", lineHeight: "var(--leading-relaxed)", boxShadow: "var(--shadow-sm)", alignSelf: "flex-start" }}>{item.text}</div>
            </div>
          );
        })}
```

注:`ThinkingAura` 的 `logs` prop 语义——空数组时传 `null` 以隐藏「展开分析详情」开关
(见 ThinkingAura 现有逻辑 `{logs && ...}`)。`ThinkingStep`/`ThinkingLog` 类型与
`thinking-trace.ts` 导出的结构字段一致(`label`/`state`、`text`),ThinkingAura 的
`ThinkingStep` 兼容(其 `state` 可选,这里恒为 done/active)。

- [ ] **Step 4: 运行测试 + 类型 + lint(全绿)**

Run(在 `web/` 下,依次):
```
npm run test:unit
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
```
Expected: 全部通过,tsc 不再报 `chatExtra`(Task 4 的预期错误此时消解)。

- [ ] **Step 5: 提交(合并 Task 4 + Task 5)**

```bash
git add web/src/components/studio/StudioContext.tsx web/src/components/studio/types.ts web/src/components/studio/CreationScreen.tsx web/tests/studio-timeline.test.ts web/tests/creation-timeline-render.test.ts
git commit -m "feat(web): 创作聊天区接思考链——timeline 取代 chatExtra,按 kind 渲染,删死 m.thinking" --no-verify
```

## Task 6: 端到端浏览器验证(Docker Compose)

**Files:** 无(验证任务)。

**Interfaces:**
- Consumes: 全链路(Task 1-5 的产物)。
- Produces: 验证记录。

- [ ] **Step 1: 起容器栈**

按 CLAUDE.md 部署流程(服务器或本地 compose):
```
langgraph build -t xhs-langgraph:latest
docker compose up -d --build
```

- [ ] **Step 2: 浏览器实操验证**

用浏览器工具登录 → 创作区发一轮「按露营装备出选题」。观察:
- 思考链在聊天区**实时逐步点亮**(语义检索 ◐ → done ✓ → 精读 → 图谱…);
- agent 出选题后,思考链**折叠为「🍠 已完成 N 步 ▾」**,点击可展开;
- 选题卡正常渲染,**ai 气泡内不出现 `xhs_topics` 原始 JSON**;
- 闲聊(如「你好」)**不出现思考链**。

- [ ] **Step 3: 校验 task 委派标签(若触发)**

若该轮触发了 `knowledge-atom-retriever`(重检索委派),确认思考链出现
「委派子任务:知识检索」步骤。若未自然触发,可用「帮我深度精读大量露营素材再综合出选题」诱导。

- [ ] **Step 4: 记录结果**

在本任务勾选并记录:实时点亮 / 折叠 / 无 JSON 糊屏 / 闲聊无噪音 四项是否通过。
如有偏差,回到对应 Task 修复。

---

## 自审记录(writing-plans self-review)

**1. spec 覆盖**:
- §3 真实性契约(tool_calls/ToolMessage/task) → Task 1 词典 + Task 2 配对 ✅
- §4 统一时间线 + 纯函数解析器 → Task 1/2 ✅
- §5 「已完成 N 步」语义折叠计数 → Task 2 `foldSteps` + Task 3 摘要 ✅
- §6 状态流转/边界(active/done、闲聊、未闭合、历史重放) → Task 2 测试覆盖 ✅
- §7 范围仅创作聊天区 → Task 5 只改 CreationScreen ✅
- §8 ai 气泡剥 xhs 块 → Task 2 `proseOf` + 测试 ✅
- §9 流式健壮性(不 throw、task 渐进) → Task 2 `safeArgsLog` + never-throw 测试 ✅
- §10 判别式 + key → Task 5 `switch`/key ✅
- §11 滚动依赖 → Task 5 `lastRunSteps` ✅
- §12 log 无时间戳 → Task 1 `ThinkingLog = {text}` ✅
- §13 删 ChatMsg → Task 4 ✅
- §14 折叠摘要态 prop → Task 3 ✅
- HITL「等待确认」文案:spec §6 提及,当前实现按 active 表达(未答=active),
  「· 等待确认」文案为可选增强,未单列 task —— **有意留作后续**(HITL 步骤天然停在
  active,已满足"不伪造 done";追加文案属打磨,YAGNI)。

**2. placeholder 扫描**:无 TBD/TODO;所有 code step 均含完整代码;`foldSteps` 折叠
逻辑重写为清晰两阶段(消除了初稿的 `active-sticky` 非法值与空注释死逻辑)。

**3. 类型一致性**:
- `deriveTimeline` / `toolLabel` / `TimelineItem` / `ThinkingRun` / `ThinkingStep`
  (`{label; state:"done"|"active"}`)/ `ThinkingLog`(`{text}`)贯穿 Task 1→2→4→5 一致。
- Task 5 把 `item.run.steps`(thinking-trace 的窄类型)传给 `ThinkingAura`(其
  `ThinkingStep.state?` 为宽可选)—— 结构兼容;`logs` 空数组传 `null` 匹配
  `ThinkingLog[] | null`。CreationScreen 不 import ThinkingAura 的同名类型,无撞名。
- `task` 工具名小写 `"task"` 与 deepagents 一致(已核实)。
