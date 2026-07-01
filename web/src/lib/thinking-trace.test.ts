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
});
