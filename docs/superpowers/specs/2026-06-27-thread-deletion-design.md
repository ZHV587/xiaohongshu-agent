# 设计:前端会话删除功能

- 日期:2026-06-27
- 范围:Web 前端(`web/`),纯前端接线,不动后端/鉴权
- 状态:待用户复审

## 1. 背景与问题

会话历史侧栏目前**没有删除入口**:每个会话项只是一个 `<button>`,点击只切换到该会话([history/index.tsx:62-84](../../../web/src/components/thread/history/index.tsx))。全前端无任何删除 UI。这不是 bug 而是**功能未实现**——后端能力齐全:

- 后端鉴权 handler `on_thread_delete` 已存在且限本人会话([auth.py:190](../../../auth.py))。
- SDK `client.threads.delete(threadId)` 现成([client.d.ts:399])。
- BFF passthrough([api/[..._path]/route.ts])自动转发并在服务端注入身份。

因此本功能是**纯前端接线**:加删除入口 + 调 SDK + 更新列表状态。

## 2. 目标 / 非目标

**目标**
- 会话列表项可删除,带二次确认防误删。
- 删当前正在查看的会话后,进入空白新会话态。
- 删除失败有明确反馈,列表不被破坏。

**非目标(YAGNI)**
- 不做撤销(undo)、不做批量删除、不做归档、不做重命名。
- 不新增弹窗/下拉菜单 UI 原语(项目 `components/ui/` 无此类原语,刻意不引入)。
- 不改后端、不改鉴权、不改 BFF。

## 3. 交互设计(已与用户确认)

- **删除入口**:鼠标 hover 会话项时,右侧露出垃圾桶图标(`Trash2`),复用项目已有的 `opacity-0 group-hover:opacity-100` hover 显隐写法。平时不占视觉。
- **二次确认**:行内二次点击确认(**不引入弹窗原语**)。点垃圾桶 → 该项就地切换为"确认删除? [取消][删除]";点[删除]执行,点[取消]或 3 秒超时自动复原。
- **删当前会话后**:跳新空白会话(`setThreadId(null)`,复用现有"新对话"行为)。
- **删非当前会话**:仅从列表移除,当前查看不变。

### 确认态边界(自审补全)
- 全局同时只有一项处于确认态:一项在确认态时点另一项垃圾桶,`confirmingId` 切换到新项。
- 确认态下点会话项主体(切换会话):正常切换,并清掉确认态。
- 确认态 3 秒无操作自动复原(`setTimeout`,组件卸载 `clearTimeout`)。

## 4. 架构与数据流

```
hover 会话项 → 露出垃圾桶 → 点击 → 项内变 "确认删除? [取消][删除]"
  → 点[删除] → ThreadProvider.deleteThread(id)
      → await client.threads.delete(id)
      → 成功:setThreads(prev => prev.filter(t => t.thread_id !== id))   ← 成功后才 filter,非乐观
              + 若 id === 当前 threadId 则 setThreadId(null)
      → 失败:抛出 → 调用方 sonner toast 报错,列表 state 不变
```

**关键事实(已读源码验证,非假设)**:`threadId` 是 `nuqs` URL query 参数,侧栏与 StreamProvider 共享同一来源。StreamProvider 用 `useTypedStream({ threadId: threadId ?? null })`([Stream.tsx:69](../../../web/src/providers/Stream.tsx)),`setThreadId(null)` 即让 stream 进空白新会话态——这正是"新对话"的现有行为,无需额外重置逻辑。

## 5. 组件与改动点(3 个文件)

### 5.1 `web/src/providers/thread-context.ts`
接口 `ThreadContextType` 新增一个方法:
```ts
deleteThread: (threadId: string) => Promise<void>;
```

### 5.2 `web/src/providers/Thread.tsx`
- 把 `getThreads` 内构造 client 的逻辑(resolve apiUrl / `toBrowserApiUrl` / `createClient`)抽成一个本地 helper `makeClient(): Client | null`,供 `getThreads` 与 `deleteThread` 共用,避免重复。
- 实现 `deleteThread(threadId)`:
  ```
  const client = makeClient(); if (!client) throw new Error(...);
  await client.threads.delete(threadId);
  setThreads(prev => prev.filter(t => t.thread_id !== threadId));  // 成功后才删,非乐观
  ```
- 失败时不捕获,向上抛由调用方 toast。
- `value` 加入 `deleteThread`。

### 5.3 `web/src/components/thread/history/index.tsx`(`ThreadList`)
- 每个会话项外层加 `group` 容器;主体仍是切换会话的可点区域。
- 右侧 `Trash2` 图标按钮:`opacity-0 group-hover:opacity-100`,`aria-label="删除会话"`。
- 本地 state:`confirmingId: string | null`(哪一项在确认态)、`deletingId: string | null`(哪一项删除在途,同时只一个)。
- 点垃圾桶(`stopPropagation`,避免触发切换)→ `setConfirmingId(t.thread_id)`,启动 3 秒复原定时器。
- 确认态该项渲染为"确认删除? [取消][删除]":
  - [删除]:`setDeletingId(id)` → `await deleteThread(id)` → 成功后若 `id === threadId` 则 `setThreadId(null)`;`finally` 清 `confirmingId`/`deletingId`。删除中按钮 disable。失败 `toast.error("删除失败,请重试")`。
  - [取消]:清 `confirmingId`。
- 点会话主体(切换)时一并 `setConfirmingId(null)`。
- 从 `useThreads()` 取 `deleteThread`;`toast` 用项目已有的 `sonner`。

## 6. 错误处理与边界

| 情形 | 行为 |
|---|---|
| 删除失败(网络/403/500) | sonner toast "删除失败,请重试";列表 state 不变(成功后才 filter) |
| 删当前会话 | 成功后 `setThreadId(null)` → 空白新会话态 |
| 删非当前会话 | 仅从列表移除,当前查看不变 |
| 越权删他人会话 | 后端 `on_thread_delete` 拒绝 → 走 toast 报错路径,前端不额外校验 |
| 与 getThreads 刷新并发 | 仅 filter 本地数组;下次 search 以最新为准,无状态冲突 |
| 确认态未操作 | 3 秒自动复原;组件卸载清定时器 |

## 7. 测试

项目 web 测试栈:`node --test` + esbuild(`web/tests/`),逻辑/契约风格,不做重型 DOM 渲染测试。

- **provider 单测**:patch `./client` 模块的 `createClient` 注入 mock SDK client,验证:
  - `deleteThread` 成功后 `setThreads` 正确 filter 掉该 `thread_id`;
  - SDK 抛错时 `deleteThread` 向上抛且不修改列表。
- **逻辑断言**:删当前会话(`id === threadId`)时触发 `setThreadId(null)`;删非当前不触发。
- `tsc --noEmit` + `eslint src` 通过。

## 8. 部署

Web 容器改动,生产生效需 rebuild:`docker compose up -d --build`(web 现场 build)。不需 `langgraph build`(后端无改动)。

## 9. 并行改动注意

`web/src/components/thread/messages/search-cards.tsx` 当前有另一进程的未提交改动(与本功能无关,不在本设计触及的 3 个文件内)。实现时只动本设计列出的文件,避免冲突。
