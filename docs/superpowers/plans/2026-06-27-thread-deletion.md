# 前端会话删除功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给会话历史侧栏加删除能力:hover 露垃圾桶 → 行内二次点击确认 → 调 SDK 删除 → 成功后从列表移除;删当前会话则进空白新会话态。

**Architecture:** 纯前端接线,后端 `on_thread_delete` 与 SDK `client.threads.delete` 已现成。`ThreadProvider` 新增 `deleteThread`(成功后才 filter 本地列表,非乐观),`ThreadList` 加 hover 垃圾桶 + 行内确认态 + 3 秒复原定时器,删当前会话复用现有 `onThreadClick(null) ?? setThreadId(null)` 切换路径。

**Tech Stack:** Next.js + React + TypeScript,`@langchain/langgraph-sdk`(Client.threads.delete)、`nuqs`(threadId URL query)、`sonner`(toast)、`lucide-react`(Trash2 图标)。测试:`node --test` + esbuild bundle,**源码文本断言风格**(`readFileSync` + `assert.match`,与 `web/tests/*.test.ts` 现有测试一致;该 harness 不跑 React/DOM,故不做运行时 mock)。

## Global Constraints

- 只动本计划列出的 3 个源文件 + 1 个测试文件;**不碰** `web/src/components/thread/messages/search-cards.tsx`(并行进程有未提交改动)。
- 不新增弹窗/下拉菜单 UI 原语(`components/ui/` 无此类,刻意不引入);确认走行内二次点击。
- 删除成功后才 `filter` 列表(非乐观更新);失败 `toast.error` 且列表 state 不变。
- 删当前会话走现有切换路径 `onThreadClick ? onThreadClick(null) : setThreadId(null)`,不硬调 `setThreadId`。
- `toast` 从 `"sonner"` 导入,签名 `toast.error(title, { description? })`(对齐项目现有用法 `auth-gate.tsx`)。
- web 测试是源码文本断言(读文件 + 正则),不是运行时测试;新测试沿用此风格。
- 生效需 rebuild web 容器(`docker compose up -d --build`),后端无改动。
- 验证三件套:`.\node_modules\.bin\tsc.CMD --noEmit`、`.\node_modules\.bin\eslint.CMD src`、`node scripts/run-unit-tests.mjs`。

---

### Task 1: ThreadProvider 暴露 deleteThread

**Files:**
- Modify: `web/src/providers/thread-context.ts`(接口加方法)
- Modify: `web/src/providers/Thread.tsx`(抽 `makeClient` helper + 实现 `deleteThread`)
- Test: `web/tests/thread-context.test.ts`(追加断言)

**Interfaces:**
- Consumes: 现有 `getThreads` 内的 client 构造逻辑(`toBrowserApiUrl`/`createClient`/`getApiKey`)、`setThreads`。
- Produces: `ThreadContextType.deleteThread: (threadId: string) => Promise<void>`;`useThreads()` 返回值含 `deleteThread`。

- [ ] **Step 1: 追加失败测试(源码断言)**

在 `web/tests/thread-context.test.ts` 末尾追加:

```typescript
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
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `cd web && node scripts/run-unit-tests.mjs`
Expected: FAIL —— 新增的两个 test 断言不匹配(deleteThread 尚未定义)。

- [ ] **Step 3: thread-context.ts 接口加方法**

修改 `web/src/providers/thread-context.ts` 的 `ThreadContextType`,在 `getThreads` 行下方加一行:

```typescript
export interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  deleteThread: (threadId: string) => Promise<void>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
}
```

- [ ] **Step 4: Thread.tsx 抽 makeClient + 实现 deleteThread**

修改 `web/src/providers/Thread.tsx`。先在 `getThreads` 上方加一个 `makeClient` helper(把现有构造逻辑抽出),再让 `getThreads` 复用它,并新增 `deleteThread`。替换 `getThreads` 定义到 `value` 之间的代码为:

```typescript
  const makeClient = useCallback(() => {
    const resolvedAssistantId = assistantId || envAssistantId;
    if (!finalApiUrl || !resolvedAssistantId) return null;
    const browserApiUrl = toBrowserApiUrl(finalApiUrl);
    if (!browserApiUrl) return null;
    return createClient(
      browserApiUrl,
      getApiKey() ?? undefined,
      authScheme || undefined,
    );
  }, [finalApiUrl, assistantId, authScheme, envAssistantId]);

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    const resolvedAssistantId = assistantId || envAssistantId;
    const client = makeClient();
    if (!client || !resolvedAssistantId) return [];

    const threads = await client.threads.search({
      metadata: {
        ...getThreadSearchMetadata(resolvedAssistantId),
      },
      limit: 100,
    });

    return threads;
  }, [makeClient, assistantId, envAssistantId]);

  const deleteThread = useCallback(
    async (threadId: string): Promise<void> => {
      const client = makeClient();
      if (!client) throw new Error("无法连接服务,删除失败");
      // 成功后才从本地列表移除(非乐观):delete 抛错则不动 state,由调用方 toast。
      await client.threads.delete(threadId);
      setThreads((prev) => prev.filter((t) => t.thread_id !== threadId));
    },
    [makeClient],
  );

  const value = {
    getThreads,
    deleteThread,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
  };
```

- [ ] **Step 5: 运行测试 + 类型 + lint**

Run: `cd web && node scripts/run-unit-tests.mjs && .\node_modules\.bin\tsc.CMD --noEmit && .\node_modules\.bin\eslint.CMD src/providers`
Expected: 测试 PASS;tsc 无报错;eslint 无报错。

- [ ] **Step 6: Commit**

```bash
git add web/src/providers/thread-context.ts web/src/providers/Thread.tsx web/tests/thread-context.test.ts
git commit -m "feat(web): ThreadProvider 暴露 deleteThread(成功后才 filter 列表)"
```

---

### Task 2: ThreadList hover 垃圾桶 + 行内二次确认 + 删除接线

**Files:**
- Modify: `web/src/components/thread/history/index.tsx`(`ThreadList` 组件)
- Test: `web/tests/thread-ui-guardrails.test.ts`(追加断言)

**Interfaces:**
- Consumes: `useThreads().deleteThread`(Task 1)、`threadId`/`setThreadId`(`useQueryState`)、`onThreadClick?`、`toast`(sonner)、`Trash2`(lucide-react)。
- Produces: 无下游(终端 UI)。

- [ ] **Step 1: 追加失败测试(源码断言)**

在 `web/tests/thread-ui-guardrails.test.ts` 末尾追加:

```typescript
test("会话列表项支持删除:hover 垃圾桶 + 行内确认 + SDK 删除接线", () => {
  const history = src("components", "thread", "history", "index.tsx");

  // hover 显隐的垃圾桶图标
  assert.match(history, /Trash2/);
  assert.match(history, /opacity-0 group-hover:opacity-100/);
  assert.match(history, /aria-label="删除会话"/);

  // 行内二次确认态(不引入弹窗原语)
  assert.match(history, /confirmingId/);
  assert.match(history, /确认删除/);

  // 接 provider 的 deleteThread + 失败 toast
  assert.match(history, /deleteThread/);
  assert.match(history, /toast\.error/);

  // 删当前会话走现有切换路径(不硬调 setThreadId)
  assert.match(history, /onThreadClick\s*\?\s*onThreadClick\(null\)\s*:\s*setThreadId\(null\)/);

  // 3 秒复原定时器 + 清理
  assert.match(history, /setTimeout/);
  assert.match(history, /clearTimeout/);
});
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `cd web && node scripts/run-unit-tests.mjs`
Expected: FAIL —— history/index.tsx 尚无 Trash2/confirmingId 等。

- [ ] **Step 3: 改 imports**

在 `web/src/components/thread/history/index.tsx` 顶部:
- `import { useEffect, useState } from "react";` 改为 `import { useEffect, useRef, useState } from "react";`
- lucide-react 的 import 加 `Trash2`:把 `SlidersHorizontal,` 那行后补 `  Trash2,`(在 `} from "lucide-react";` 之前)。
- 在 `import { cn } from "@/lib/utils";` 下方加一行:`import { toast } from "sonner";`

- [ ] **Step 4: 重写 ThreadList 组件**

把 `web/src/components/thread/history/index.tsx` 中整个 `ThreadList` 函数(从 `function ThreadList({` 到其闭合 `}`,即当前第 34-88 行)替换为:

```typescript
function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string | null) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const [, setView] = useQueryState("view");
  const { deleteThread } = useThreads();
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const confirmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearConfirmTimer = () => {
    if (confirmTimer.current) {
      clearTimeout(confirmTimer.current);
      confirmTimer.current = null;
    }
  };

  useEffect(() => clearConfirmTimer, []);

  const switchTo = (id: string | null) => {
    if (onThreadClick) onThreadClick(id);
    else setThreadId(id);
  };

  const startConfirm = (id: string) => {
    clearConfirmTimer();
    setConfirmingId(id);
    confirmTimer.current = setTimeout(() => setConfirmingId(null), 3000);
  };

  const cancelConfirm = () => {
    clearConfirmTimer();
    setConfirmingId(null);
  };

  const confirmDelete = async (id: string) => {
    clearConfirmTimer();
    setIsDeleting(true);
    try {
      await deleteThread(id);
      if (id === threadId) switchTo(null);
      setConfirmingId(null);
    } catch {
      toast.error("删除失败,请重试");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="[&::-webkit-scrollbar-thumb]:bg-border flex h-full w-full flex-col items-start gap-1 overflow-y-auto px-2 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full">
      {threads.map((t) => {
        // 优先用首条用户消息作标题;取不到(如失败/空会话)显示友好占位,
        // 不暴露 thread_id 这种 UUID(此前会显示成一长串乱码似的 ID)。
        let itemText = "未命名对话";
        if (
          typeof t.values === "object" &&
          t.values &&
          "messages" in t.values &&
          Array.isArray(t.values.messages) &&
          t.values.messages?.length > 0
        ) {
          const first = getContentString(t.values.messages[0].content).trim();
          if (first) itemText = first;
        }
        const active = t.thread_id === threadId;
        const confirming = t.thread_id === confirmingId;

        if (confirming) {
          return (
            <div
              key={t.thread_id}
              className="bg-oats/60 flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm"
            >
              <span className="text-charcoal truncate">确认删除?</span>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  disabled={isDeleting}
                  onClick={(e) => {
                    e.stopPropagation();
                    cancelConfirm();
                  }}
                >
                  取消
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-coral hover:text-coral h-7 px-2 text-xs"
                  disabled={isDeleting}
                  onClick={(e) => {
                    e.stopPropagation();
                    void confirmDelete(t.thread_id);
                  }}
                >
                  删除
                </Button>
              </div>
            </div>
          );
        }

        return (
          <div
            key={t.thread_id}
            className={cn(
              "group flex min-h-11 w-full items-center rounded-lg transition-all",
              active
                ? "bg-oats text-coral border-coral rounded-l-none rounded-r-lg border-l-2"
                : "text-charcoal hover:bg-oats/50",
            )}
          >
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                setView(null);
                cancelConfirm();
                if (t.thread_id === threadId) return;
                switchTo(t.thread_id);
              }}
              className={cn(
                "min-w-0 flex-1 truncate px-3 py-2.5 text-left text-sm",
                active ? "pl-2 font-semibold" : "",
              )}
            >
              {itemText}
            </button>
            <button
              type="button"
              aria-label="删除会话"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                startConfirm(t.thread_id);
              }}
              className="text-charcoal-light hover:text-coral mr-2 flex size-7 shrink-0 items-center justify-center rounded opacity-0 transition-opacity group-hover:opacity-100"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 5: 运行测试 + 类型 + lint**

Run: `cd web && node scripts/run-unit-tests.mjs && .\node_modules\.bin\tsc.CMD --noEmit && .\node_modules\.bin\eslint.CMD src/components/thread/history`
Expected: 测试 PASS;tsc 无报错;eslint 无报错(注意 `void confirmDelete(...)` 是为满足 no-floating-promises;若 eslint 报未使用的 `parseAsBoolean` 等既有 import 不属本次改动,不动)。

- [ ] **Step 6: Commit**

```bash
git add web/src/components/thread/history/index.tsx web/tests/thread-ui-guardrails.test.ts
git commit -m "feat(web): 会话列表项支持删除(hover 垃圾桶 + 行内二次确认)"
```

---

### Task 3: 端到端人工验证 + 收尾

**Files:** 无代码改动(验证任务)

- [ ] **Step 1: 全量前端校验**

Run: `cd web && .\node_modules\.bin\tsc.CMD --noEmit && .\node_modules\.bin\eslint.CMD src && node scripts/run-unit-tests.mjs`
Expected: 三者全过。

- [ ] **Step 2: 本地起前端,浏览器人工验证**

用浏览器工具(已登录态)验证四条路径:
1. hover 某会话项 → 垃圾桶出现;移开 → 消失。
2. 点垃圾桶 → 该项变"确认删除? [取消][删除]";点[取消]或等 3 秒 → 复原。
3. 点[删除]一个**非当前**会话 → 该项从列表消失,当前查看不变。
4. 点[删除]**当前正在查看**的会话 → 列表移除 + 进入空白新会话态(右侧聊天区清空)。
5. (可选)断网点删除 → 出现"删除失败,请重试" toast,列表不变。

- [ ] **Step 3: 确认未触碰并行文件**

Run: `git status --short web/src/components/thread/messages/search-cards.tsx`
Expected: 仍是并行进程那条未提交改动(`M`),本次未叠加我的改动。

- [ ] **Step 4: 部署说明(交付给用户决定)**

本功能改 web 前端,生产生效需 rebuild web 容器:`docker compose up -d --build`(不需 `langgraph build`)。是否部署由用户决定。

---

## Self-Review

**1. Spec coverage:**
- 删除入口 hover 垃圾桶 → Task 2 Step 4 ✓
- 行内二次确认 + 3 秒复原 → Task 2(confirmingId + setTimeout/clearTimeout)✓
- 删当前会话走现有切换路径 → Task 2 `switchTo` 复用 `onThreadClick ?? setThreadId` ✓
- 删非当前仅移除 → Task 1 filter + Task 2 不调 switchTo ✓
- 成功后才 filter(非乐观)→ Task 1 Step 4 await 后 filter + Step 1 顺序断言 ✓
- 删除失败 toast + 列表不变 → Task 2 `catch → toast.error` ✓
- deleteThread 接口/实现 → Task 1 ✓
- 测试 → Task 1/2 源码断言(已对齐 harness 实际风格)✓
- 部署说明 → Task 3 Step 4 ✓
- 不碰 search-cards.tsx → Global Constraints + Task 3 Step 3 ✓

**2. Placeholder scan:** 无 TBD/TODO;所有代码步骤含完整代码;测试含具体断言。✓

**3. Type consistency:** `deleteThread: (threadId: string) => Promise<void>` 在 thread-context.ts(Task 1 Step 3)、Thread.tsx(Step 4)、history/index.tsx(Task 2 解构使用)三处签名一致;`switchTo`/`confirmingId`/`isDeleting`/`confirmTimer` 命名贯穿 Task 2 一致。✓

**偏离 spec 的一处(已对齐实际):** spec §7 写"mock SDK client 单测",但 web 测试 harness 是源码文本断言(esbuild bundle,无 React/DOM 运行时),无法运行时 mock。计划改为**源码断言测试**(验证 `client.threads.delete` 调用、await-then-filter 顺序、切换路径、toast、定时器等接线存在),与 `web/tests/` 现有全部测试风格一致。这是更忠实于代码库的做法。
