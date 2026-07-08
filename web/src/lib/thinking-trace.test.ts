import assert from "node:assert/strict";
import test from "node:test";

import { toolLabel, deriveTimeline, parseLatestAdoption, adoptedNoteResourceIds } from "./thinking-trace";

test("toolLabel maps known data_foundation tools to Chinese", () => {
  assert.equal(toolLabel("semantic_search_resources", {}), "按语义找相关素材");
  assert.equal(toolLabel("search_resources", {}), "按关键词补查素材");
  assert.equal(toolLabel("get_resource", {}), "打开原文细看");
  assert.equal(toolLabel("graph_expand", {}), "顺着图谱找关联");
  assert.equal(toolLabel("save_generated_topic", {}), "保存选题");
});

test("toolLabel maps feishu action tools", () => {
  assert.equal(toolLabel("sync_copy_to_feishu", {}), "同步文案到飞书");
  assert.equal(toolLabel("adopt_online_notes", {}), "采纳线上笔记");
});

test("toolLabel resolves task delegation via subagent_type", () => {
  assert.equal(toolLabel("task", { subagent_type: "knowledge-atom-retriever" }), "请知识检索助手查证据");
  assert.equal(toolLabel("task", { subagent_type: "persona-distiller" }), "请风格提炼助手看样本");
  assert.equal(toolLabel("task", { subagent_type: "benchmark-analyst" }), "请对标分析助手拆爆款");
  assert.equal(toolLabel("task", { subagent_type: "expert-panel-debater" }), "请专家会商助手给判断");
});

test("toolLabel task without subagent_type falls back to generic", () => {
  assert.equal(toolLabel("task", {}), "请子任务助手处理");
  assert.equal(toolLabel("task", undefined), "请子任务助手处理");
});

test("toolLabel unknown tool falls back to raw name", () => {
  assert.equal(toolLabel("some_new_tool", {}), "some_new_tool");
});

test("deriveTimeline is a stub returning empty array (Task 1)", () => {
  assert.deepEqual(deriveTimeline([]), []);
});

import type { Message } from "@langchain/langgraph-sdk";
import type { TracePresentation } from "./agent-trace";

const human = (text: string): Message => ({ id: "h", type: "human", content: text } as Message);
const aiText = (text: string): Message => ({ id: "a", type: "ai", content: text, tool_calls: [] } as unknown as Message);
const aiCall = (id: string, name: string, args: Record<string, unknown> = {}): Message =>
  ({ id, type: "ai", content: "", tool_calls: [{ id, name, args }] } as unknown as Message);
const aiCallWithText = (id: string, text: string, name: string, args: Record<string, unknown> = {}): Message =>
  ({ id, type: "ai", content: text, tool_calls: [{ id, name, args }] } as unknown as Message);
const toolMsg = (callId: string): Message =>
  ({ id: "t" + callId, type: "tool", tool_call_id: callId, content: "ok" } as unknown as Message);
// write_todos 规划调用:content 空,tool_calls 带 todos 数组(智能体写的工作流阶段计划)。
const aiTodos = (id: string, todos: Array<{ content: string; status: string }>): Message =>
  ({ id, type: "ai", content: "", tool_calls: [{ id, name: "write_todos", args: { todos } }] } as unknown as Message);
// 带命中结果的工具消息(results 数组用于工作流阶段结果行"命中 N 条")。
const toolMsgResults = (callId: string, n: number): Message =>
  ({ id: "t" + callId, type: "tool", tool_call_id: callId, content: JSON.stringify({ results: Array.from({ length: n }, (_, i) => ({ note_id: "n" + i, title: "t" + i })) }) } as unknown as Message);

test("write_todos plan renders as the primary workflow-phase track (generic phases, not tool names)", () => {
  const tl = deriveTimeline([
    human("按职场穿搭出选题"),
    aiTodos("p1", [
      { content: "理解需求", status: "completed" },
      { content: "检索爆款素材依据", status: "in_progress" },
      { content: "拆解共性套路", status: "pending" },
      { content: "产出候选选题", status: "pending" },
    ]),
    toolMsg("p1"),
    aiCallWithText("c1", "我先从本地库检索能支撑这个方向的爆款素材。", "search_local_note_cards", { keyword: "职场穿搭" }),
    toolMsgResults("c1", 4),
    aiText("给你几个选题方向"),
  ], { loading: true });
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  // 思考链主轴是工作流阶段(智能体真实计划),不是工具名。
  assert.deepEqual(
    thinking.run.steps.map((s) => s.label),
    ["理解需求", "检索爆款素材依据"],
    "pending 阶段尚未执行，不提前预列",
  );
  assert.deepEqual(
    thinking.run.steps.map((s) => s.state),
    ["done", "active"],
  );
  assert.equal(thinking.run.steps[1].description, "我先从本地库检索能支撑这个方向的爆款素材。");
  // 命中数归到"命中它时正 in_progress 的阶段"作结果行。
  assert.equal(thinking.run.steps[1].result, "命中 4 条相关素材");
  assert.equal(thinking.run.currentStep, 2, "当前步 = 唯一 in_progress 的第 2 步");
  assert.ok(
    thinking.run.logs.some((log) => log.text.includes("检索本地笔记卡")),
    "真实工具调用保留在同一个轨迹框的可展开记录中",
  );
  assert.deepEqual(tl.map((item) => item.kind), ["user", "thinking", "ai"]);
});

test("workflow track suppresses the fallback tool track (only one thinking item, phases not tools)", () => {
  const tl = deriveTimeline([
    human("出选题"),
    aiTodos("p1", [{ content: "检索爆款素材依据", status: "in_progress" }]),
    toolMsg("p1"),
    aiCall("c1", "search_local_note_cards", { keyword: "x" }),
    toolMsg("c1"),
    aiText("答案"),
  ]);
  const thinkingItems = tl.filter((i) => i.kind === "thinking");
  assert.equal(thinkingItems.length, 1, "只有工作流一条,兜底工具轨道被压制");
  assert.deepEqual(thinkingItems[0].run.steps.map((s) => s.label), ["检索爆款素材依据"]);
});

test("no write_todos → falls back to the tool-name track (short tasks keep working)", () => {
  const tl = deriveTimeline([
    human("出选题"),
    aiCall("c1", "semantic_search_resources", { query: "x" }),
    toolMsg("c1"),
    aiText("答案"),
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.deepEqual(thinking.run.steps.map((s) => s.label), ["按语义找相关素材"]);
});

const officialPresentation: TracePresentation = {
  traceId: "trace-1",
  turnId: "h",
  status: "done",
  collapsedByDefault: true,
  userSummary: "查完 1 步",
  userStages: [
    {
      id: "retrieve",
      title: "查找相关素材",
      summary: "找到 12 条，采用 3 条",
      intent: "先确认有没有可用素材，避免凭空给建议。",
      action: "从数据底座检索与你需求相关的笔记和历史素材。",
      resultText: "找到 12 条相关素材，采用 3 条作为本次回答依据。",
      statusText: "已完成",
      state: "done",
      metricsText: "找到 12 条，采用 3 条",
      sourceEventIds: ["e1"],
    },
  ],
  adminDetails: [],
};

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
  // 兜底轨道现在给每步补一句意图说明(Claude Code/Codex 式,消除黑盒感),故断言含 description。
  assert.deepEqual(thinking.run.steps, [
    { label: "按语义找相关素材", state: "active", description: "从数据底座按语义相似度召回可用笔记和历史素材" },
  ]);
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
  assert.deepEqual(thinking.run.steps, [
    { label: "按语义找相关素材", state: "done", description: "从数据底座按语义相似度召回可用笔记和历史素材" },
  ]);
  assert.equal(thinking.run.done, true);
});

test("completed thinking run appears between the user message and the final AI output", () => {
  const tl = deriveTimeline([
    human("出选题"),
    aiCall("c1", "semantic_search_resources", { query: "露营" }),
    toolMsg("c1"),
    aiText("这是选题建议"),
  ]);
  assert.deepEqual(
    tl.map((item) => item.kind),
    ["user", "thinking", "ai"],
    "like Claude Code / Codex: the work trace streams above, the answer lands below it",
  );
});

test("official trace mounts right after its turn's user message (turn_id = human message id)", () => {
  const tl = deriveTimeline([human("按职场穿搭出 1 个选题"), aiText("这是最终回答")], {
    tracePresentationsByTurnId: { h: officialPresentation },
  });

  assert.deepEqual(tl.map((item) => item.kind), ["user", "thinking", "ai"]);
  const thinking = tl[1];
  assert.ok(thinking.kind === "thinking");
  assert.equal(thinking.run.presentation?.userSummary, "查完 1 步");
  assert.equal(thinking.run.steps[0].label, "查找相关素材");
  assert.equal(thinking.run.steps[0].description, "先确认有没有可用素材，避免凭空给建议。");
  assert.equal(thinking.run.steps[0].result, "找到 12 条相关素材，采用 3 条作为本次回答依据。");
  assert.equal(thinking.run.logs[0].text, "找到 12 条，采用 3 条");
});

test("official trace maps each step's real state and points at the current step (Claude-Code style)", () => {
  // 三步:第1步 done、第2步 active(当前)、第3步也 active。run 未 done。
  const presentation: TracePresentation = {
    traceId: "t",
    turnId: "a",
    status: "active",
    collapsedByDefault: false,
    userSummary: "处理中",
    userStages: [
      { id: "s1", title: "核验素材依据", summary: "", intent: "i1", action: "a1", resultText: "r1", statusText: "已完成", state: "done", sourceEventIds: ["e1"] },
      { id: "s2", title: "筛选可用依据", summary: "", intent: "i2", action: "a2", resultText: "r2", statusText: "正在处理", state: "active", sourceEventIds: ["e2"] },
      { id: "s3", title: "组织回答结构", summary: "", intent: "i3", action: "a3", resultText: "r3", statusText: "正在处理", state: "active", sourceEventIds: ["e3"] },
    ],
    adminDetails: [],
  };
  const tl = deriveTimeline([human("出选题"), aiText("回答")], {
    loading: true,
    tracePresentationsByTurnId: { h: presentation },
  });
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  // 每步状态忠实映射,而非一刀切。
  assert.deepEqual(thinking.run.steps.map((s) => s.state), ["done", "active", "active"]);
  assert.equal(thinking.run.done, false);
  assert.equal(thinking.run.totalSteps, 3);
  // 当前步 = 最后一个 active(第3步)。
  assert.equal(thinking.run.currentStep, 3);
});

test("tool-call progress prose stays inside the trace; only the final answer becomes an ai bubble", () => {
  const tl = deriveTimeline([
    human("出选题"),
    {
      type: "ai",
      content: "我先检索相关素材作为选题依据。",
      tool_calls: [{ id: "c1", name: "semantic_search_resources", args: { query: "职场穿搭" } }],
    } as unknown as Message,
    toolMsg("c1"),
    aiText("这是最终选题建议"),
  ]);
  assert.deepEqual(
    tl.map((item) => item.kind),
    ["user", "thinking", "ai"],
    "过程旁白归入工作轨迹，正式答复才落普通气泡",
  );
  const thinking = tl[1];
  assert.ok(thinking.kind === "thinking");
  assert.equal(thinking.run.done, true);
  assert.equal(thinking.run.steps[0].label, "按语义找相关素材");
  assert.equal(thinking.run.steps[0].description, "我先检索相关素材作为选题依据。");
  assert.ok(thinking.run.logs.some((log) => log.text === "我先检索相关素材作为选题依据。"));
  const answer = tl[2];
  assert.ok(answer.kind === "ai" && answer.text === "这是最终选题建议");
});

test("standalone progress prose before a later tool call also stays inside the single trace", () => {
  const tl = deriveTimeline([
    human("出选题"),
    aiText("本地库暂时没有强相关内容，我再扩大关键词范围补一轮。"),
    aiCall("c1", "search_xhs_online", { keyword: "职场通勤" }),
    toolMsg("c1"),
    aiText("这是最终选题建议"),
  ]);
  assert.deepEqual(tl.map((item) => item.kind), ["user", "thinking", "ai"]);
  const thinking = tl[1];
  assert.ok(thinking.kind === "thinking");
  assert.equal(
    thinking.run.steps[0].description,
    "本地库暂时没有强相关内容，我再扩大关键词范围补一轮。",
  );
  assert.ok(
    thinking.run.logs.some((log) => log.text === "本地库暂时没有强相关内容，我再扩大关键词范围补一轮。"),
  );
});

test("completed todo workflow reveals every stage and keeps all process prose inside one trace", () => {
  const tl = deriveTimeline([
    human("出选题"),
    aiTodos("p1", [
      { content: "理解需求", status: "completed" },
      { content: "检索爆款素材依据", status: "in_progress" },
      { content: "产出候选选题", status: "pending" },
    ]),
    toolMsg("p1"),
    aiCallWithText("c1", "正在检索高互动素材。", "search_local_note_cards", { keyword: "职场穿搭" }),
    toolMsgResults("c1", 3),
    aiTodos("p2", [
      { content: "理解需求", status: "completed" },
      { content: "检索爆款素材依据", status: "completed" },
      { content: "产出候选选题", status: "completed" },
    ]),
    toolMsg("p2"),
    aiText("最终给你三个方向"),
  ]);
  assert.deepEqual(tl.map((item) => item.kind), ["user", "thinking", "ai"]);
  const thinking = tl[1];
  assert.ok(thinking.kind === "thinking");
  assert.deepEqual(
    thinking.run.steps.map((step) => step.label),
    ["理解需求", "检索爆款素材依据", "产出候选选题"],
  );
  assert.ok(thinking.run.steps.every((step) => step.state === "done"));
  assert.equal(thinking.run.done, true);
});

// ── live 路径回归(此前的"黑盒"根因):trace 事件到达 store 时,官方轨道必须当场流式可见 ──

const liveStage = (id: string, title: string, state: "active" | "done" | "error") => ({
  id, title, summary: "", intent: "i-" + id, action: "a-" + id, resultText: "r-" + id,
  statusText: state === "done" ? "已完成" : "正在处理", state, sourceEventIds: ["e-" + id],
});

test("LIVE: official trace streams step-by-step while the run is still loading", () => {
  // 运行中(loading=true),还没有任何 AI 消息 —— 官方轨道已能逐步展示,不再整体压制。
  const presentation: TracePresentation = {
    traceId: "t", turnId: "h", status: "active", collapsedByDefault: false, userSummary: "处理中",
    userStages: [liveStage("s1", "核验素材依据", "done"), liveStage("s2", "筛选可用依据", "active")],
    adminDetails: [],
  };
  const tl = deriveTimeline([human("找露营爆款")], {
    loading: true,
    tracePresentationsByTurnId: { h: presentation },
  });
  assert.deepEqual(tl.map((i) => i.kind), ["user", "thinking"]);
  const thinking = tl[1];
  assert.ok(thinking.kind === "thinking");
  assert.deepEqual(thinking.run.steps.map((s) => s.label), ["核验素材依据", "筛选可用依据"]);
  assert.deepEqual(thinking.run.steps.map((s) => s.state), ["done", "active"]);
  assert.equal(thinking.run.done, false, "live turn must stay visibly in-progress");
  assert.equal(thinking.run.currentStep, 2);
});

test("LIVE→DONE: trace does not vanish when the stream ends on the same page", () => {
  // 此前的重大纰漏:流结束(loading=false)后思考链整段消失。现在必须保留并折叠为完成态。
  const presentation: TracePresentation = {
    traceId: "t", turnId: "h", status: "active", collapsedByDefault: false, userSummary: "处理中",
    userStages: [liveStage("s1", "核验素材依据", "done")],
    adminDetails: [],
  };
  const tl = deriveTimeline([human("找露营爆款"), aiText("给你找到了这些素材")], {
    loading: false,
    tracePresentationsByTurnId: { h: presentation },
  });
  assert.deepEqual(tl.map((i) => i.kind), ["user", "thinking", "ai"]);
  const thinking = tl[1];
  assert.ok(thinking.kind === "thinking");
  assert.equal(thinking.run.done, true, "stream ended → the turn's trace folds as done");
});

test("multi-turn: an older turn's official trace stays done while a new turn is streaming", () => {
  const h2: Message = { id: "h2", type: "human", content: "再来一轮" } as Message;
  const oldPresentation: TracePresentation = {
    traceId: "t1", turnId: "h", status: "active", collapsedByDefault: false, userSummary: "s",
    userStages: [liveStage("s1", "核验素材依据", "done")],
    adminDetails: [],
  };
  const tl = deriveTimeline([human("第一轮"), aiText("第一轮回答"), h2], {
    loading: true,
    tracePresentationsByTurnId: { h: oldPresentation },
  });
  const thinkingItems = tl.filter((i) => i.kind === "thinking");
  assert.ok(thinkingItems.length >= 1);
  assert.equal(thinkingItems[0].run.done, true, "旧回合不因新一轮开跑而倒退回进行中");
});

test("per-turn fallback: a turn without official trace still shows its fallback track", () => {
  // 逐轮判断(不再全局一刀切):turn1 有官方轨道,turn2 匹配不到 → turn2 用兜底轨道。
  const presentation: TracePresentation = {
    traceId: "t1", turnId: "h", status: "done", collapsedByDefault: true, userSummary: "s",
    userStages: [liveStage("s1", "核验素材依据", "done")],
    adminDetails: [],
  };
  const h2: Message = { id: "h2", type: "human", content: "第二轮" } as Message;
  const tl = deriveTimeline(
    [
      human("第一轮"),
      aiText("第一轮回答"),
      h2,
      aiCall("c9", "semantic_search_resources", { query: "x" }),
      toolMsg("c9"),
      { id: "a2", type: "ai", content: "第二轮回答", tool_calls: [] } as unknown as Message,
    ],
    { loading: false, tracePresentationsByTurnId: { h: presentation } },
  );
  const thinkingItems = tl.filter((i) => i.kind === "thinking");
  assert.equal(thinkingItems.length, 2, "官方轨道一条 + 第二轮兜底轨道一条");
  assert.equal(thinkingItems[1].run.steps[0].label, "按语义找相关素材");
});

test("fallback track marks a failed tool step as error, not done", () => {
  const failedTool: Message = {
    id: "tE", type: "tool", tool_call_id: "cE", content: "boom", status: "error",
  } as unknown as Message;
  const tl = deriveTimeline([
    human("同步"),
    aiCall("cE", "sync_copy_to_feishu", {}),
    failedTool,
    aiText("同步失败了"),
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.equal(thinking.run.steps[0].state, "error", "真实失败要如实标 ✕,不能装作 done");
  assert.equal(thinking.run.done, true, "步骤已出终态(失败也是终态),run 不再悬置");
});

test("empty official presentation falls back to the richer fallback track", () => {
  const empty: TracePresentation = {
    traceId: "t", turnId: "h", status: "active", collapsedByDefault: false, userSummary: "",
    userStages: [], adminDetails: [],
  };
  const tl = deriveTimeline(
    [human("出选题"), aiCall("c1", "semantic_search_resources", { query: "x" })],
    { loading: true, tracePresentationsByTurnId: { h: empty } },
  );
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.equal(thinking.run.steps[0].label, "按语义找相关素材", "空 presentation 不压制兜底轨道");
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
  assert.equal(thinking.run.steps[0].label, "打开原文细看");
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

test("pure-English scaffolding prose never surfaces as an ai bubble", () => {
  // 细节2 复现:子代理起手的英文旁白 "I'll start by reading the reference material."
  // 曾被当成最终答案渲染成 🍠 气泡。它是过程噪声,不含任何中文 → 必须丢弃,不进对话流。
  const tl = deriveTimeline([
    human("照《健身包推荐》的套路仿写"),
    aiText("I'll start by reading the reference material."),
  ]);
  assert.equal(tl.filter((i) => i.kind === "ai").length, 0, "英文脚手架旁白不得成为答案气泡");
});

test("English scaffolding between tool calls is dropped but the trace keeps flowing", () => {
  // 英文旁白夹在工具调用之间:不切断思考链,后续步骤继续累积到同一条轨迹;英文本身不出气泡。
  const tl = deriveTimeline([
    human("仿写这篇"),
    {
      type: "ai",
      content: "Let me read the reference first.",
      tool_calls: [{ id: "c1", name: "get_resource", args: { resource_id: "n1" } }],
    } as unknown as Message,
    toolMsg("c1"),
    aiText("读完了,这是仿写成品。"),
  ]);
  assert.deepEqual(
    tl.map((i) => i.kind),
    ["user", "thinking", "ai"],
    "英文旁白不产气泡,只有最终中文答案落地",
  );
  const ai = tl.find((i) => i.kind === "ai");
  assert.ok(ai && ai.kind === "ai" && ai.text === "读完了,这是仿写成品。");
});

test("mixed Chinese+English prose is kept (contains CJK)", () => {
  const tl = deriveTimeline([human("出选题"), aiText("已用 A/B test 思路给你两个方向。")]);
  const ai = tl.find((i) => i.kind === "ai");
  assert.ok(ai && ai.kind === "ai" && ai.text.includes("A/B test"), "中英混排的正常回答照常保留");
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

test("ai bubble strips literal <thinking> tags leaked into prose", () => {
  // 结构化输出失败时,子代理把扩展思考当字面 <thinking> 标签写进正文;必须剥掉。
  const content = "<thinking>Now let me output the A version.</thinking>好的,这是文案。";
  const tl = deriveTimeline([human("写文案"), aiText(content)]);
  const ai = tl.find((i) => i.kind === "ai");
  assert.ok(ai && ai.kind === "ai");
  assert.ok(!ai.text.includes("<thinking>"), "must strip opening tag");
  assert.ok(!ai.text.includes("Now let me output"), "must strip thinking content");
  assert.ok(ai.text.includes("好的,这是文案"), "keeps real prose");
});

test("ai message that is only a <thinking> block produces no ai bubble", () => {
  const content = "<thinking>internal reasoning only</thinking>";
  const tl = deriveTimeline([human("写文案"), aiText(content)]);
  assert.equal(tl.filter((i) => i.kind === "ai").length, 0);
});

test("consecutive identical AI prose is de-duplicated (repeated-summary guard)", () => {
  // 结构化输出失败时观察到同一份汇总被吐 4 遍;相邻完全相同的 ai 段应只保留一条。
  const dup = "全部流程已完成,以下是本次交付的完整摘要。";
  const tl = deriveTimeline([
    human("写文案"),
    aiText(dup),
    aiText(dup),
    aiText(dup),
    aiText(dup),
  ]);
  assert.equal(tl.filter((i) => i.kind === "ai").length, 1, "4 identical summaries collapse to 1");
});

test("distinct AI prose is NOT de-duplicated", () => {
  const tl = deriveTimeline([human("写文案"), aiText("第一段"), aiText("第二段")]);
  assert.equal(tl.filter((i) => i.kind === "ai").length, 2);
});

test("never throws on malformed / partial messages", () => {
  const weird = [
    { type: "ai", content: null, tool_calls: [{ id: "x", name: "task", args: undefined }] },
    { type: "tool", tool_call_id: "x", content: "" },
  ] as unknown as Message[];
  assert.doesNotThrow(() => deriveTimeline(weird));
  // Fix 3: structural assertions on malformed input
  const result = deriveTimeline(weird);
  assert.ok(Array.isArray(result), "output should be an array");
  assert.equal(
    result.filter((i) => i.kind === "ai").length,
    0,
    "malformed ai with content=null should not produce an ai bubble",
  );
});

// Fix 1: safeArgsLog security — write tools must not leak payload in logs

test("write tool log contains only Chinese label, not payload value", () => {
  // save_generated_copy is a write tool; its args may contain sensitive copy payload
  const tl = deriveTimeline([
    human("出文案"),
    aiCall("w1", "save_generated_copy", { copy: "这是私密文案内容_SECRET" }),
    toolMsg("w1"),
    aiText("已沉淀"),
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.equal(thinking.run.logs.length, 1);
  const logText = thinking.run.logs[0].text;
  // should only be the Chinese label
  assert.equal(logText, "保存文案", "write tool log must equal label only, no payload");
  assert.ok(!logText.includes("SECRET"), "write tool log must not contain payload value");
});

test("read tool log still includes truncated args detail", () => {
  const tl = deriveTimeline([
    human("搜索"),
    aiCall("r1", "semantic_search_resources", { query: "露营攻略" }),
    toolMsg("r1"),
    aiText("结果"),
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  const logText = thinking.run.logs[0].text;
  assert.ok(logText.includes("露营攻略"), "read tool log should contain query value");
});

test("read tool log strips sensitive key fields (token/credential etc) before stringify", () => {
  const tl = deriveTimeline([
    human("搜索"),
    aiCall("r1", "semantic_search_resources", { query: "露营", token: "SECRET_TOKEN_VALUE" }),
    toolMsg("r1"),
    aiText("结果"),
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  const logText = thinking.run.logs[0].text;
  assert.ok(!logText.includes("SECRET_TOKEN_VALUE"), "log must not contain token value");
  assert.ok(logText.includes("露营"), "log should still contain non-sensitive query");
});

// Fix 2: runDone OR branch — all-done tools with no final prose → run.done = true

test("thinking run with all tools done but no prose text has done=true", () => {
  const tl = deriveTimeline([
    human("执行"),
    aiCall("t1", "semantic_search_resources", { query: "x" }),
    toolMsg("t1"),
    // No final aiText — run ends with all tools answered but no prose
  ]);
  const thinking = tl.find((i) => i.kind === "thinking");
  assert.ok(thinking && thinking.kind === "thinking");
  assert.equal(thinking.run.steps[0].state, "done", "step should be done");
  assert.equal(thinking.run.done, true, "run.done should be true when all steps done, even without prose");
  // No ai bubble
  assert.equal(tl.filter((i) => i.kind === "ai").length, 0);
});

test("loading context appends an active thinking item when no tool call has started", () => {
  const tl = deriveTimeline([human("帮我出选题")], { loading: true });
  assert.deepEqual(tl, [
    { kind: "user", text: "帮我出选题" },
    {
      kind: "thinking",
      run: {
        steps: [{ label: "正在查素材和历史数据", state: "active" }],
        logs: [],
        done: false,
        currentStep: 1,
        totalSteps: 1,
      },
    },
  ]);
});

test("error context appends a sanitized response error item", () => {
  const tl = deriveTimeline([human("帮我出选题")], {
    error: new Error("backend exploded with token=SECRET_TOKEN_VALUE"),
  });
  assert.equal(tl.length, 2);
  assert.deepEqual(tl[0], { kind: "user", text: "帮我出选题" });
  assert.equal(tl[1].kind, "error");
  assert.ok("text" in tl[1]);
  assert.ok(tl[1].text.includes("backend exploded"));
  assert.ok(!tl[1].text.includes("SECRET_TOKEN_VALUE"));
});

test("error context never renders raw object placeholders", () => {
  const tl = deriveTimeline([human("帮我出选题")], {
    error: { code: "UPSTREAM_ERROR", detail: { retry: false } },
  });
  assert.equal(tl[1].kind, "error");
  assert.ok("text" in tl[1]);
  assert.notEqual(tl[1].text, "[object Object]");
  assert.ok(!tl[1].text.includes("[object Object]"));
});

test("xhs_panel block surfaces as a panel timeline item (intent disambiguation)", () => {
  const content = [
    "你是想让我出选题,还是找爆款来仿写?",
    "```xhs_panel",
    '{ "actions": [ { "label": "让 AI 出选题", "text": "让 AI 出选题" }, { "label": "找爆款来仿写", "text": "找爆款仿写" } ] }',
    "```",
  ].join("\n");
  const tl = deriveTimeline([human("给我出选题"), { id: "a", type: "ai", content, tool_calls: [] } as unknown as Message]);
  const panel = tl.find((i) => i.kind === "panel");
  assert.ok(panel && panel.kind === "panel");
  assert.equal(panel.actions.length, 2);
  assert.deepEqual(panel.actions.map((a) => a.label), ["让 AI 出选题", "找爆款来仿写"]);
  // prose(问句)仍作为 ai 气泡保留,panel 紧随其后。
  assert.ok(tl.some((i) => i.kind === "ai" && i.text.includes("出选题")));
});

test("discovery tool results become a discovery timeline item (materials, not chat)", () => {
  const tl = deriveTimeline([
    human("找露营爆款"),
    aiCall("c1", "search_xhs_online", { keyword: "露营" }),
    {
      id: "t1", type: "tool", tool_call_id: "c1",
      content: JSON.stringify({ ok: true, results: [
        { note_id: "n1", title: "露营装备清单", source: "online", likes: 3000 },
      ] }),
    } as unknown as Message,
  ]);
  const disc = tl.find((i) => i.kind === "discovery");
  assert.ok(disc && disc.kind === "discovery");
  assert.equal(disc.notes.length, 1);
  assert.equal(disc.notes[0].note_id, "n1");
});

test("streaming (unclosed) rich xhs_topics does NOT leak flattened field garbage into prose", () => {
  // 富选题对象流式未闭合时,局部解析器会把 title/hotRate/angle/evidence/resource_id 等
  // key+value 打散;此处确认这些字段名不会作为正文糊屏(仍被当 topics 段从 prose 剥离)。
  const midstream = '整理了几个方向\n```xhs_topics\n{"topics":[{"title":"5个杠铃动作","hotRate":88,"angle":"动作纠错","evidence":[{"resource_id":"b799225a"';
  const tl = deriveTimeline([human("出选题"), { id: "a", type: "ai", content: midstream, tool_calls: [] } as unknown as Message]);
  const ai = tl.find((i) => i.kind === "ai");
  if (ai && ai.kind === "ai") {
    assert.ok(!ai.text.includes("hotRate"), "字段名不应出现在正文");
    assert.ok(!ai.text.includes("resource_id"), "resource_id 不应出现在正文");
    assert.ok(!ai.text.includes("b799225a"), "evidence id 不应出现在正文");
  }
});

// ── adopt_online_notes 结果解析(收录结果弹窗数据源) ──────────────────────────
const adoptResult = (callId: string, payload: unknown): Message =>
  ({ id: "t" + callId, type: "tool", tool_call_id: callId, content: JSON.stringify(payload) } as unknown as Message);

test("parseLatestAdoption splits results into success / skipped / failed", () => {
  const messages = [
    human("收录这些笔记"),
    aiCall("c1", "adopt_online_notes", {}),
    adoptResult("c1", {
      ok: true,
      results: [
        { note_id: "n1", title: "露营装备清单", adopted: true, already_adopted: false, resource_id: "res-1" },
        { note_id: "n2", title: "平价好物", adopted: true, already_adopted: true, resource_id: "res-2" },
      ],
      errors: [{ note_id: "n3", error: "DB_ADOPT_FAILED: boom" }],
    }),
  ];
  const outcome = parseLatestAdoption(messages);
  assert.ok(outcome);
  assert.equal(outcome!.callId, "c1");
  assert.equal(outcome!.successCount, 1);
  assert.equal(outcome!.skippedCount, 1);
  assert.equal(outcome!.failedCount, 1);
  assert.deepEqual(outcome!.failedNoteIds, ["n3"]);
  const failed = outcome!.rows.find((r) => r.outcome === "failed");
  assert.ok(failed && failed.error!.includes("boom"));
});

test("parseLatestAdoption treats feishu/association warnings on adopted notes as NOT failures", () => {
  // n1 已入库(adopted:true)但飞书同步失败 → errors 里有它,但不算收录失败(库记录仍在)。
  const messages = [
    human("收录"),
    aiCall("c1", "adopt_online_notes", {}),
    adoptResult("c1", {
      ok: true,
      results: [{ note_id: "n1", title: "笔记一", adopted: true, already_adopted: false, resource_id: "res-1" }],
      errors: [{ note_id: "n1", error: "FEISHU_SYNC_FAILED: perm denied" }],
    }),
  ];
  const outcome = parseLatestAdoption(messages);
  assert.ok(outcome);
  assert.equal(outcome!.successCount, 1);
  assert.equal(outcome!.failedCount, 0);
  assert.deepEqual(outcome!.failedNoteIds, []);
});

test("parseLatestAdoption returns the most recent adoption (retry supersedes prior)", () => {
  const messages = [
    human("收录"),
    aiCall("c1", "adopt_online_notes", {}),
    adoptResult("c1", { ok: true, results: [], errors: [{ note_id: "n1", error: "DB_ADOPT_FAILED: x" }] }),
    human("重试失败的"),
    aiCall("c2", "adopt_online_notes", {}),
    adoptResult("c2", { ok: true, results: [{ note_id: "n1", title: "笔记一", adopted: true, already_adopted: false, resource_id: "res-1" }], errors: [] }),
  ];
  const outcome = parseLatestAdoption(messages);
  assert.ok(outcome);
  assert.equal(outcome!.callId, "c2");
  assert.equal(outcome!.successCount, 1);
  assert.equal(outcome!.failedCount, 0);
});

test("parseLatestAdoption returns null for empty/failed-shape payloads", () => {
  assert.equal(parseLatestAdoption([human("hi"), aiText("no tools")]), null);
  const emptyBatch = [
    human("收录"),
    aiCall("c1", "adopt_online_notes", {}),
    adoptResult("c1", { ok: false, error: "no selected notes", results: [], errors: [] }),
  ];
  assert.equal(parseLatestAdoption(emptyBatch), null);
});

test("adoptedNoteResourceIds accumulates note_id → resource_id across all adopt results", () => {
  const messages = [
    aiCall("c1", "adopt_online_notes", {}),
    adoptResult("c1", { ok: true, results: [{ note_id: "n1", adopted: true, resource_id: "res-1" }], errors: [] }),
    aiCall("c2", "adopt_online_notes", {}),
    adoptResult("c2", { ok: true, results: [{ note_id: "n2", adopted: true, resource_id: "res-2" }], errors: [] }),
  ];
  const map = adoptedNoteResourceIds(messages);
  assert.equal(map.get("n1"), "res-1");
  assert.equal(map.get("n2"), "res-2");
  assert.equal(map.size, 2);
});
