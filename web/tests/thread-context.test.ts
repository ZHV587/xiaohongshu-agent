import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = (...parts: string[]) =>
  readFileSync(join(process.cwd(), "src", ...parts), "utf8");

test("ThreadContext exposes required states and actions + useThread guardrail", () => {
  const context = src("components", "thread", "ThreadContext.tsx");

  // 状态字段
  assert.match(context, /lastSavedTitle:\s*string/);
  assert.match(context, /lastSavedContent:\s*string/);
  assert.match(context, /isDirty:\s*boolean/);

  // 动作 handler
  assert.match(context, /handleExecuteCommand:\s*\(cmd:\s*string\)\s*=>\s*void/);

  // useThread hook 守卫
  assert.match(context, /if\s*\(!ctx\)/);
  assert.match(context, /throw\s+new\s+Error\("useThread must be used within a ThreadProvider"\)/);
});

test("ThreadStateProvider injects draft states + delegates autosave to useThreadDraftState", () => {
  const provider = src("components", "thread", "ThreadStateProvider.tsx");
  const hook = src("components", "thread", "useThreadDraftState.ts");

  // provider 注入草稿状态
  assert.match(provider, /lastSavedTitle,/);
  assert.match(provider, /lastSavedContent,/);
  assert.match(provider, /isDirty,/);
  assert.match(provider, /handleExecuteCommand,/);

  // 委托给 useThreadDraftState,provider 自身不再直接持久化
  assert.match(provider, /useThreadDraftState\(/);
  assert.doesNotMatch(provider, /xhs_autosave_draft_/);
  assert.doesNotMatch(provider, /setLastSavedContent\(/);
  assert.match(hook, /buildDraftAutosaveKey/);
  assert.match(hook, /parseAiDraft/);
});

test("useThreadDraftState keeps applying streaming content updates for the same AI message", () => {
  const hook = src("components", "thread", "useThreadDraftState.ts");

  assert.doesNotMatch(hook, /lastAiMessageId/);
  assert.match(hook, /lastMsg\.content/);
  assert.match(hook, /setDraftContent\(next\.content\)/);
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
