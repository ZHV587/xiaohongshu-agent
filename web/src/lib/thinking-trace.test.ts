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
  assert.equal(logText, "沉淀文案入库", "write tool log must equal label only, no payload");
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
        steps: [{ label: "正在思考并检索数据底座", state: "active" }],
        logs: [],
        done: false,
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
