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
  // 摘要头显示「查完 N 步」,N 来自 steps.length
  assert.match(src, /查完/);
  assert.match(src, /steps\.length/);
});

test("collapsed state is toggleable", () => {
  assert.match(src, /useState/);
  assert.match(src, /collapsed/);
});

test("ThinkingAura syncs collapsed state when defaultCollapsed prop changes", () => {
  assert.match(src, /source:\s*defaultCollapsed/);
  assert.match(src, /collapsedState\.source === defaultCollapsed/);
});
