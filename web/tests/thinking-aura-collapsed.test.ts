import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = readFileSync(
  join(process.cwd(), "src", "components", "ds", "content", "ThinkingAura.tsx"),
  "utf8",
);
const globals = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

test("ThinkingAura presents a Codex-style work trace, not raw chain-of-thought", () => {
  for (const marker of [
    "工作轨迹",
    "steps",
    "logs",
    "defaultOpen",
    "defaultCollapsed",
    "xhs-ping",
    "收起记录",
    "查看做了什么",
    "done",
    "active",
    "pending",
    "✓",
    "◐",
    "○",
    "font-mono",
  ]) {
    assert.ok(src.includes(marker), `missing ThinkingAura marker: ${marker}`);
  }
  assert.ok(!src.includes("思考轨迹"), "ThinkingAura should not present raw chain-of-thought wording");
  assert.ok(!src.includes("Thinking Aura"), "ThinkingAura should not expose internal component naming");
});

test("ThinkingAura motion tokens exist in globals", () => {
  assert.ok(globals.includes("@keyframes xhs-ping"), "missing xhs-ping keyframes");
  assert.ok(src.includes("spin 1.4s linear infinite"), "missing active step spin motion");
});

test("ThinkingAura accepts defaultCollapsed prop", () => {
  assert.match(src, /defaultCollapsed\??:\s*boolean/);
});

test("ThinkingAura renders step purpose and result details", () => {
  assert.match(src, /description\??:\s*string/);
  assert.match(src, /result\??:\s*string/);
  assert.match(src, /s\.description/);
  assert.match(src, /s\.result/);
});

test("ThinkingAura renders a collapsed summary with step count", () => {
  // Claude Code / Codex 式折叠摘要:「✓ 思考了 Ns · 查了 N 处」,N 来自 steps.length。
  assert.match(src, /查了/);
  assert.match(src, /思考了/);
  assert.match(src, /steps\.length/);
});

test("ThinkingAura shows a live elapsed timer while running", () => {
  // 运行中走秒计时(Claude Code 式「正在思考 · Ns」),数据来自 setInterval 测得的真实秒数。
  assert.match(src, /正在思考/);
  assert.match(src, /setInterval/);
});

test("collapsed state is toggleable", () => {
  assert.match(src, /useState/);
  assert.match(src, /collapsed/);
});

test("ThinkingAura syncs collapsed state when defaultCollapsed prop changes", () => {
  assert.match(src, /source:\s*defaultCollapsed/);
  assert.match(src, /collapsedState\.source === defaultCollapsed/);
});
