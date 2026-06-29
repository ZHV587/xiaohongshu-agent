import test from "node:test";
import assert from "node:assert/strict";

import { resolveToolRender } from "../src/lib/tool-render";

// 守护"思考链通用化"的核心派生逻辑(发现 B:此前无回归覆盖)。

test("读取 SKILL.md 渲染为通用方法步骤,且不暴露技能 slug", () => {
  const spec = resolveToolRender("read_file", {
    file_path: "/skills/xhs-copywriting/SKILL.md",
  });
  assert.notEqual(spec.aura, "hidden");
  if (spec.aura === "hidden") throw new Error("unreachable");
  assert.equal(spec.aura.running, "正在整理方法…");
  assert.equal(spec.aura.done({ name: "read_file" }), "已整理好方法");
  assert.doesNotMatch(spec.aura.running, /xhs-|copywriting|topic-content|技能|skill/i);
  assert.doesNotMatch(spec.aura.done({ name: "read_file" }), /xhs-|copywriting|topic-content|技能|skill/i);
});

test("非 xhs 前缀的 skill 也渲染为通用方法步骤", () => {
  const spec = resolveToolRender("read_file", {
    file_path: "/skills/topic-content/SKILL.md",
  });
  assert.notEqual(spec.aura, "hidden");
  if (spec.aura === "hidden") throw new Error("unreachable");
  assert.equal(spec.aura.running, "正在整理方法…");
  assert.equal(spec.aura.done({ name: "read_file" }), "已整理好方法");
  assert.doesNotMatch(spec.aura.running, /xhs-|copywriting|topic-content|技能|skill/i);
  assert.doesNotMatch(spec.aura.done({ name: "read_file" }), /xhs-|copywriting|topic-content|技能|skill/i);
});

test("非 skill 的 read_file 保持隐藏(噪音不入思考链)", () => {
  const spec = resolveToolRender("read_file", {
    file_path: "/memories/team/AGENTS.md",
  });
  assert.equal(spec.aura, "hidden");
});

test("检索类工具把真实检索词作为入参摘要", () => {
  const spec = resolveToolRender("semantic_search_resources", { query: "健身" });
  assert.equal(spec.argsSummary?.({ query: "健身" }), "健身");
});

test("保存选题把真实方向作为入参摘要", () => {
  const spec = resolveToolRender("save_generated_topic", { direction: "露营" });
  assert.equal(spec.argsSummary?.({ direction: "露营" }), "露营");
});

test("空白入参不产生摘要", () => {
  const spec = resolveToolRender("semantic_search_resources", { query: "  " });
  assert.equal(spec.argsSummary?.({ query: "  " }), undefined);
});

test("未注册工具回退到可见的默认步骤(不隐藏)", () => {
  const spec = resolveToolRender("some_unknown_tool", {});
  assert.notEqual(spec.aura, "hidden");
  if (spec.aura === "hidden") throw new Error("unreachable");
  assert.equal(typeof spec.aura.running, "string");
});
