import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = readFileSync(
  join(process.cwd(), "src", "components", "ds", "content", "ThinkingAura.tsx"),
  "utf8",
);
const globals = readFileSync(join(process.cwd(), "src", "app", "globals.css"), "utf8");

test("ThinkingAura mirrors the DS source contract", () => {
  for (const marker of [
    "思考轨迹 (Thinking Aura)",
    "steps",
    "logs",
    "defaultOpen",
    "defaultCollapsed",
    "xhs-ping",
    "收起分析详情",
    "展开分析详情",
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
});

test("ThinkingAura motion tokens exist in globals", () => {
  assert.ok(globals.includes("@keyframes xhs-ping"), "missing xhs-ping keyframes");
  assert.ok(src.includes("spin 1.4s linear infinite"), "missing active step spin motion");
});

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

test("ThinkingAura syncs collapsed state when defaultCollapsed prop changes via useEffect", () => {
  // 确认组件内有 useEffect 监听 defaultCollapsed 并调用 setCollapsed
  assert.match(src, /useEffect/);
  // useEffect 和 setCollapsed 同时出现（effect 体内含 setCollapsed）
  const effectIdx = src.indexOf("useEffect");
  const setCollapsedIdx = src.indexOf("setCollapsed", effectIdx);
  assert.ok(effectIdx !== -1 && setCollapsedIdx !== -1 && setCollapsedIdx > effectIdx,
    "setCollapsed should appear after useEffect in source");
});
