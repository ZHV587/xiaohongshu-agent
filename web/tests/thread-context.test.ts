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

test("Thread delegates draft autosave and AI draft parsing to useThreadDraftState", () => {
  const thread = src("components", "thread", "index.tsx");
  const hook = src("components", "thread", "useThreadDraftState.ts");

  assert.match(thread, /useThreadDraftState\(/);
  assert.doesNotMatch(thread, /xhs_autosave_draft_/);
  assert.doesNotMatch(thread, /setLastSavedContent\(/);
  assert.match(hook, /buildDraftAutosaveKey/);
  assert.match(hook, /parseAiDraft/);
});

test("thread-context 接口声明 deleteThread", () => {
  const ctx = readFileSync(
    join(process.cwd(), "src", "providers", "thread-context.ts"),
    "utf8",
  );
  assert.match(ctx, /deleteThread:\s*\(threadId:\s*string\)\s*=>\s*Promise<void>/);
});

test("Thread provider 实现 deleteThread:成功后才 filter,且经 client.threads.delete", () => {
  const provider = readFileSync(
    join(process.cwd(), "src", "providers", "Thread.tsx"),
    "utf8",
  );
  // 经 SDK 删除
  assert.match(provider, /client\.threads\.delete\(threadId\)/);
  // 成功后才 filter(delete 在 setThreads 之前,即先 await 再 filter)
  const deleteIdx = provider.indexOf("client.threads.delete(threadId)");
  const filterIdx = provider.indexOf("t.thread_id !== threadId");
  assert.ok(deleteIdx > -1 && filterIdx > -1 && deleteIdx < filterIdx,
    "必须先 await delete 再 filter 列表(非乐观)");
  // 注入 value
  assert.match(provider, /deleteThread,/);
});
