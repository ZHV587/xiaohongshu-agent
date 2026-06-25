import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = (...parts: string[]) =>
  readFileSync(join(process.cwd(), "src", ...parts), "utf8");

test("ThreadContext exposes required new states and actions for split components", () => {
  const context = src("components", "thread", "ThreadContext.tsx");

  // Check state properties
  assert.match(context, /lastSavedTitle:\s*string/);
  assert.match(context, /lastSavedContent:\s*string/);
  assert.match(context, /isDirty:\s*boolean/);

  // Check action handlers
  assert.match(context, /handleExecuteCommand:\s*\(cmd:\s*string\)\s*=>\s*void/);

  // Check guardrails in useThread hook
  assert.match(context, /if\s*\(!ctx\)/);
  assert.match(context, /throw\s+new\s+Error\("useThread must be used within a ThreadProvider"\)/);
});

test("index.tsx provider correctly injects new states and actions", () => {
  const thread = src("components", "thread", "index.tsx");

  assert.match(thread, /lastSavedTitle,/);
  assert.match(thread, /lastSavedContent,/);
  assert.match(thread, /isDirty,/);
  assert.match(thread, /handleExecuteCommand,/);
});
