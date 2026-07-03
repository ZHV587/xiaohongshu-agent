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

test("StudioContext passes loading and error context into deriveTimeline", () => {
  const ctx = src("components", "studio", "StudioContext.tsx");
  assert.match(ctx, /deriveTimeline\(t\.messages,\s*\{/);
  assert.match(ctx, /loading:\s*t\.isLoading/);
  assert.match(ctx, /error:\s*t\.error/);
});
