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
