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
