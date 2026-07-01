# 前端旧 Thread() 生态死代码清除 + 后端 _repository 去重 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 彻底删除前端旧 `Thread()` 三栏 UI 的整片死代码生态(含 `PhoneSimulator` 假博主/假笔记、`usePreviewState` 假 Unsplash 配图),改造仍调用死 hook 的活 `ThreadStateProvider` 并瘦身 `ThreadContext`;后端把 `tools.py` 的 `_repository()` 收敛到 `studio_shared.repository()`。

**Architecture:** 前端按依赖倒序删除死文件(叶子→根),再改造活 provider 移除死状态、迁移唯一活字段 `isEditingText` 为本地 state,最后瘦身 `ThreadContext` interface。全程用 **knip(死文件检测)+ `tsc --noEmit`(消费方类型裁决)+ `npm run build`** 判定死活,不用 `grep 单词`(子串会误判)。后端纯去重,别名 import 使 14 处调用点零改名。

**Tech Stack:** Next.js / React / TypeScript / knip / Vitest(`node scripts/run-unit-tests.mjs`)/ Python 3.11 / LangChain `@tool` / deepagents / pytest。

## Global Constraints

- **真实数据铁律**:清除所有硬编码假业务数据(张潇潇假博主、露营假笔记、Unsplash 假配图);不新增任何 mock。
- **LangGraph SDK 官方接线不动**:`stream.submit({messages, context, ...patch})`、`context`/state patch、`stream.*`、`submitText`/`handleSubmit`/`handleRegenerate`、草稿自动保存、会话切换、错误处理、活 handler `handleExecuteCommand`(润色/瘦身/话题)、`handleSyncToFeishu`(调 `sync_copy_to_feishu` 工具)——一字不动其 `submitText`/`stream.submit` 调用链。
- **deepagents 拓展面零影响**:后端改动仅工具函数体内部 db helper 来源;`@tool`/`tools=`/`RunnableConfig` 不变。
- **判死活工具**:knip + `tsc --noEmit` + build,非子串 grep。
- **活消费边界(已核实)**:`useThread`/`useThreadOptional` 全项目活消费者仅 `StudioContext.tsx`(用 `messages`/`isLoading`/`draftTitle`/`draftContent`/`setDraftTitle`/`setDraftContent`/`submitText`/`setThreadId`/`handleExecuteCommand`/`handleSyncToFeishu`)+ `Shell.tsx`(用 `threadId`/`setThreadId`)。其余 context 字段无对外活消费方。
- **服务器命令绕代理**:本地 push 用 `git -c http.proxy= -c https.proxy= push origin master`(失败改默认代理 `git push`,见项目 memory)。

---

### Task 1: 后端 `tools.py` 复用 `studio_shared.repository`(P1 去重)

**Files:**
- Modify: `data_foundation/tools.py`(删 `_repository()` 定义 + 改 import + 清理 4 个孤立 import)
- Test: `tests/data_foundation`(现有全量回归,验证工具行为不变)

**Interfaces:**
- Consumes: `data_foundation.studio_shared.repository`(现有 `@contextmanager`,yield `ResourceRepository`,与被删的 `_repository()` 逐字等价)
- Produces: 无新增对外接口(内部去重);14 处 `with _repository() as repo` 经 `as _repository` 别名保持不变

- [ ] **Step 1: 跑基线回归(确认改动前全绿)**

Run: `uv run pytest tests/data_foundation -q`
Expected: PASS(记录通过数,作为改动后对比基线)

- [ ] **Step 2: 改 import——引入 studio_shared.repository 别名**

`data_foundation/tools.py:26`,把:
```python
from data_foundation.studio_shared import is_admin_open_id
```
改为:
```python
from data_foundation.studio_shared import is_admin_open_id, repository as _repository
```

- [ ] **Step 3: 删除本地 `_repository()` 定义**

删除 `data_foundation/tools.py:41-47`(含 `@contextmanager` 装饰行):
```python
@contextmanager
def _repository() -> Iterator[ResourceRepository]:
    conn = connect()
    try:
        yield ResourceRepository(conn)
    finally:
        conn.close()
```

- [ ] **Step 4: 删除因此不再使用的 4 个 import**

已核实 `connect`/`ResourceRepository`/`Iterator`/`contextmanager` 在 `tools.py` 内除被删定义外零他用。删除:
- `data_foundation/tools.py:5` `from collections.abc import Iterator`
- `data_foundation/tools.py:6` `from contextlib import contextmanager`
- `data_foundation/tools.py:21` `from data_foundation.db import connect`
- `data_foundation/tools.py:32` `from data_foundation.repositories.resource import ResourceRepository`

> 若 `Iterator`/`contextmanager` 的 import 行还合并了其他被使用的名字(如 `from contextlib import contextmanager, suppress`),只删 `contextmanager` 部分,保留其余。删前对每个名字 `grep -n "\bIterator\b\|\bcontextmanager\b\|\bconnect\b\|\bResourceRepository\b" data_foundation/tools.py` 复核仅剩 import 行自身。

- [ ] **Step 5: 跑回归验证行为不变**

Run: `uv run pytest tests/data_foundation -q`
Expected: PASS(通过数与 Step 1 一致)

- [ ] **Step 6: 运行时导入 smoke(确认无循环 import、工具计数不变)**

Run:
```bash
uv run python scripts/runtime_import_smoke.py
uv run python -c "import agent; print('tools:', len(agent.assembled_tools))"
```
Expected: `agent=OK` 等全 OK;工具计数与去重前一致(去重不改工具数量)。

- [ ] **Step 7: 提交**

```bash
git add data_foundation/tools.py
git commit -m "refactor(data_foundation): tools.py 复用 studio_shared.repository(消除 _repository 复制)"
```


### Task 2: 删除死叶子组件 + `messages/` + `agent-inbox/`(不被 provider 引用)

**Files(全部 Delete):**
- `web/src/components/thread/PhoneSimulator.tsx`(**假数据**:张潇潇/露营)
- `web/src/components/thread/RightInspector.tsx`
- `web/src/components/thread/ChatTimeline.tsx`
- `web/src/components/thread/ComposerPanel.tsx`
- `web/src/components/thread/CommandPalette.tsx`
- `web/src/components/thread/EvidenceInspector.tsx`
- `web/src/components/thread/MultimodalPreview.tsx`
- `web/src/components/thread/ContentBlocksPreview.tsx`
- `web/src/components/thread/messages/`(整个目录:ai.tsx / human.tsx / copy-card.tsx / topic-cards.tsx / search-cards.tsx / panel-card.tsx / evidence-time.tsx / generic-interrupt.tsx / shared.tsx)
- `web/src/components/thread/agent-inbox/`(整个目录)

**Interfaces:**
- Consumes: 无(这些文件仅被死根 `index.tsx` 或彼此引用;`index.tsx` 在 Task 4 删)
- Produces: 无

> 注意:此时 `thread/index.tsx` 尚未删(Task 4),它仍 import 上述文件——所以本任务后 `tsc` 会在 `index.tsx` 报 "cannot find module"。这是**预期的**,证明这些文件确实只被 `index.tsx` 引用。本任务的验证改用反向引用检查,不跑 tsc(tsc 留到 Task 4 删完 index.tsx 后)。

- [ ] **Step 1: 反向引用检查——确认这些文件无「死子树之外」的引用**

Run(对每个待删文件的 basename 精确查 import 语句,排除死子树内部):
```bash
cd web && for f in PhoneSimulator RightInspector ChatTimeline ComposerPanel CommandPalette EvidenceInspector MultimodalPreview ContentBlocksPreview; do
  echo "--- $f ---"
  grep -rn "import.*[\"'/]$f[\"']" src/ | grep -vE "thread/(index|ChatTimeline|ComposerPanel|RightInspector|PhoneSimulator|CommandPalette|EvidenceInspector|MultimodalPreview|ContentBlocksPreview|messages/)"
done
grep -rn "thread/messages/" src/ | grep -vE "thread/(index|ChatTimeline|ComposerPanel|messages/)"
grep -rn "thread/agent-inbox" src/ | grep -vE "thread/(index|agent-inbox/)"
```
Expected: 每项**无输出**(证明仅死子树内部引用;`studio/` 零引用)。若任何一项有 `studio/` 或 page.tsx 输出,停止并重新评估边界。

- [ ] **Step 2: 删除文件**

```bash
cd web && git rm src/components/thread/PhoneSimulator.tsx \
  src/components/thread/RightInspector.tsx \
  src/components/thread/ChatTimeline.tsx \
  src/components/thread/ComposerPanel.tsx \
  src/components/thread/CommandPalette.tsx \
  src/components/thread/EvidenceInspector.tsx \
  src/components/thread/MultimodalPreview.tsx \
  src/components/thread/ContentBlocksPreview.tsx
git rm -r src/components/thread/messages src/components/thread/agent-inbox
```

- [ ] **Step 3: 提交(中间态,index.tsx 待 Task 4 删)**

```bash
git commit -m "chore(web): 删除旧 Thread() 死叶子组件 + messages/ + agent-inbox/(含 PhoneSimulator 假数据)"
```


### Task 3: 删除死辅助文件 + `history/index.tsx` + `mockup.html`

**Files(全部 Delete):**
- `web/src/components/thread/markdown-text.tsx`
- `web/src/components/thread/syntax-highlighter.tsx`
- `web/src/components/thread/markdown-styles.css`
- `web/src/components/thread/artifact-hooks.tsx`
- `web/src/components/thread/artifact-slot.tsx`
- `web/src/components/thread/history/index.tsx`(`ThreadHistory`,仅死根引用)
- `web/src/lib/tool-render.tsx`
- `web/src/lib/evidence-rank.ts`
- `web/src/lib/agent-inbox-interrupt.ts`
- `web/src/hooks/useMediaQuery.tsx`
- `web/mockup.html`(设计原型,含假数据)

**保留(边界,勿删):** `thread/artifact.tsx`、`thread/artifact-context.ts`(page.tsx `ArtifactProvider` 活用);`thread/history/FeishuConfigPage.tsx`、`LlmConfigPage.tsx`、`RuntimeFactsPage.tsx`、`runtime-facts-format.ts`(`AdminConfigPanel`/`RuntimeFactsPage` 活用)。

**Interfaces:**
- Consumes: 无(仅死子树引用)
- Produces: 无

- [ ] **Step 1: 反向引用检查——确认无活引用**

Run:
```bash
cd web && for f in markdown-text syntax-highlighter artifact-hooks artifact-slot tool-render evidence-rank agent-inbox-interrupt useMediaQuery; do
  echo "--- $f ---"
  grep -rn "import.*[\"'/]$f[\"']" src/ | grep -vE "thread/(index|messages/|agent-inbox/|artifact-hooks|artifact-slot|markdown-text)|lib/(tool-render|evidence-rank|agent-inbox-interrupt)"
done
echo "--- ThreadHistory (history/index) ---"
grep -rn "import.*thread/history[\"']|from [\"']\./history[\"']|from [\"']\.\./history[\"']" src/ | grep -v "thread/index.tsx"
echo "--- history/index 具名/默认引用 ---"
grep -rn "ThreadHistory" src/ | grep -v "history/index.tsx"
echo "--- mockup.html 引用 ---"
grep -rn "mockup.html" src/ next.config.mjs playwright.config.ts package.json 2>/dev/null
```
Expected: 每项**无输出**(`markdown-styles.css` 随 markdown-text 删,其 import 在已删的 messages/ 内)。若有 `studio/`/page.tsx/config 输出,停止重新评估。

> 特别核对 `artifact-hooks`/`artifact-slot`:确认引用它们的只有已删的 `messages/ai.tsx` 与彼此/`artifact-context.ts`,而**活的** `artifact.tsx` 只 import `artifact-context`(不 import hooks/slot)。若 `artifact.tsx` 出现在输出中,停止——它是活文件。

- [ ] **Step 2: 删除文件**

```bash
cd web && git rm src/components/thread/markdown-text.tsx \
  src/components/thread/syntax-highlighter.tsx \
  src/components/thread/markdown-styles.css \
  src/components/thread/artifact-hooks.tsx \
  src/components/thread/artifact-slot.tsx \
  src/components/thread/history/index.tsx \
  src/lib/tool-render.tsx \
  src/lib/evidence-rank.ts \
  src/lib/agent-inbox-interrupt.ts \
  src/hooks/useMediaQuery.tsx
git rm mockup.html
```

- [ ] **Step 3: 提交(中间态)**

```bash
git commit -m "chore(web): 删除旧 Thread() 死辅助文件 + ThreadHistory + mockup.html 假数据原型"
```


### Task 4: 改造 `ThreadStateProvider` + 删死 hook + 删死根 `index.tsx`

**Files:**
- Modify: `web/src/components/thread/ThreadStateProvider.tsx`(删死 hook 调用/死状态/死 handler,保留活接线)
- Delete: `web/src/components/thread/index.tsx`(死根 `Thread()`)
- Delete: `web/src/components/thread/usePreviewState.ts`、`useCommandPaletteState.ts`、`useWorkbenchTabsState.ts`、`useFeishuWorkspaceState.ts`
- Delete(死 hook 的单测):`web/tests/preview-state.test.ts`、`web/tests/command-palette-state.test.ts`、`web/tests/feishu-workspace-state.test.ts`

**Interfaces:**
- Consumes: `useStreamContext`(SDK)、`useThreadDraftState`(保留)、`useFileUpload`(保留)、`ThreadActionsProvider`(保留)
- Produces: `ThreadStateProvider` 组件契约不变(仍 render `ThreadContext.Provider` + `ThreadActionsProvider`);对外暴露的活字段见 Task 5 瘦身后的 interface。**活 handler `handleExecuteCommand(cmd)`、`handleSyncToFeishu()`、`submitText(text, stateUpdate?)` 签名与行为不变。**

- [ ] **Step 1: 改造 ThreadStateProvider.tsx——删除死 hook import 与调用**

删除以下 import([:21-24](web/src/components/thread/ThreadStateProvider.tsx)):
```typescript
import { useCommandPaletteState } from "./useCommandPaletteState";
import { useWorkbenchTabsState } from "./useWorkbenchTabsState";
import { usePreviewState } from "./usePreviewState";
import { useFeishuWorkspaceState } from "./useFeishuWorkspaceState";
```

删除对应的解构调用块:
- [:53-54](web/src/components/thread/ThreadStateProvider.tsx) `const { rightTab, setRightTab, selectedEvidence, setSelectedEvidence } = useWorkbenchTabsState();`
- [:55-63](web/src/components/thread/ThreadStateProvider.tsx) `const { viewMode, ..., carouselImages } = usePreviewState();` 整块
- [:65-76](web/src/components/thread/ThreadStateProvider.tsx) `const { feishuChats, ..., setIsFeishuActionPending } = useFeishuWorkspaceState(rightTab);` 整块
- [:124-125](web/src/components/thread/ThreadStateProvider.tsx) `const { showCommandPalette, setShowCommandPalette, cmdSearch, setCmdSearch } = useCommandPaletteState();`

- [ ] **Step 2: 删除死本地状态、死 ref、死 effect**

删除:
- `textareaRef` ref([:91](web/src/components/thread/ThreadStateProvider.tsx))
- 自适应高度 `useEffect`([:128-133](web/src/components/thread/ThreadStateProvider.tsx),`if (isEditingText && textareaRef.current)`——`isEditingText` 已随 usePreviewState 删除,此 effect 死)
- bitable/wiki 本地状态 `bitableUrl`/`wikiUrl`([:87-88](web/src/components/thread/ThreadStateProvider.tsx))与其拉取 `useEffect`([:93-111](web/src/components/thread/ThreadStateProvider.tsx),仅喂死 context 字段)
- 死同步 UI 状态:`syncStepsVisible`/`setSyncStepsVisible`([:79](web/src/components/thread/ThreadStateProvider.tsx))、`syncStep`/`setSyncStep`([:80](web/src/components/thread/ThreadStateProvider.tsx))、`isFlying`/`setIsFlying`([:84](web/src/components/thread/ThreadStateProvider.tsx))

保留(活):`isSyncing`/`setIsSyncing`([:81](web/src/components/thread/ThreadStateProvider.tsx),防重复提交守卫)、`isDirty`(会话切换守卫)、所有草稿/stream/文件上传状态。

- [ ] **Step 3: 清理 setThreadId 与会话切换 effect 里的死 setter 引用**

- [:144](web/src/components/thread/ThreadStateProvider.tsx) `setThreadId` 内删 `setIsEditingText(false);`,并从其 deps 数组([:148](web/src/components/thread/ThreadStateProvider.tsx))移除 `setIsEditingText`。
- [:344](web/src/components/thread/ThreadStateProvider.tsx) 会话切换 effect 内删 `setIsEditingText(false);`。

- [ ] **Step 4: 改造活 handler——剔除死副作用(保留 SDK 接线)**

`handleExecuteCommand`([:183-201](web/src/components/thread/ThreadStateProvider.tsx)):删首行 `setShowCommandPalette(false);`,保留其余 `submitText(...)` 分支不动。

`handleSyncToFeishu`([:203-226](web/src/components/thread/ThreadStateProvider.tsx)):改造为(移除 `setIsFlying`/`setSyncStepsVisible`/`setSyncStep`/`setIsFeishuActionPending` 死状态写,保留 `isSyncing` 守卫 + `submitText` 调 `sync_copy_to_feishu` + toast):
```typescript
const handleSyncToFeishu = () => {
  if (isSyncing || isLoading) return;
  setIsSyncing(true);
  setTimeout(() => {
    submitText(
      [
        "请调用 sync_copy_to_feishu 工具，把当前右侧文案保存为飞书多维表格草稿。",
        "这是一个写入动作，请先向我确认写入风险和目标表，再继续。",
        "",
        `标题：${draftTitle}`,
        "",
        `正文：${draftContent}`,
      ].join("\n"),
    );
    setIsSyncing(false);
    toast.success("已交给智能体，等待确认/执行。");
  }, 800);
};
```

- [ ] **Step 5: 删除死 handler**

删除 `handleSendNotification`([:228-246](web/src/components/thread/ThreadStateProvider.tsx))、`handleInsertEmoji`([:248-261](web/src/components/thread/ThreadStateProvider.tsx))、`handleAppendTag`([:263-265](web/src/components/thread/ThreadStateProvider.tsx))、`handleEditBodyPaste`([:267-287](web/src/components/thread/ThreadStateProvider.tsx))——四者在活代码零引用。

- [ ] **Step 6: 从 ThreadContext.Provider value 移除所有死字段**

在 provider 的 `value={{...}}`([:398-473](web/src/components/thread/ThreadStateProvider.tsx))中删除以下键:`rightTab`/`setRightTab`/`selectedEvidence`/`setSelectedEvidence`/`viewMode`/`setViewMode`/`isEditingText`/`setIsEditingText`/`carouselIndex`/`setCarouselIndex`/`carouselImages`/`feishuChats`/`setFeishuChats`/`selectedChatId`/`setSelectedChatId`/`isFetchingChats`/`setIsFetchingChats`/`isSendingNotification`/`setIsSendingNotification`/`isFeishuActionPending`/`setIsFeishuActionPending`/`syncStepsVisible`/`setSyncStepsVisible`/`syncStep`/`setSyncStep`/`isFlying`/`setIsFlying`/`showCommandPalette`/`setShowCommandPalette`/`cmdSearch`/`setCmdSearch`/`bitableUrl`/`wikiUrl`/`handleSendNotification`/`handleInsertEmoji`/`handleAppendTag`/`handleEditBodyPaste`/`textareaRef`。

> 保留键:`threadId`/`setThreadId`/`chatHistoryOpen`/`setChatHistoryOpen`/`view`/`setView`/`input`/`setInput`/`contentBlocks`/`setContentBlocks`/`isLoading`/`isStreaming`/`setFirstTokenReceived`/`submitText`/`handleSubmit`/`handleRegenerate`/`handleFileUpload`/`dropRef`/`removeBlock`/`dragOver`/`handlePaste`/`messages`/`draftTitle`/`setDraftTitle`/`draftContent`/`setDraftContent`/`isDirty`/`isSyncing`/`setIsSyncing`/`lastSavedTitle`/`lastSavedContent`/`handleExecuteCommand`/`handleSyncToFeishu`。

- [ ] **Step 7: 删除死根 index.tsx 与 4 个死 hook 文件 + 死 hook 单测**

```bash
cd web && git rm src/components/thread/index.tsx \
  src/components/thread/usePreviewState.ts \
  src/components/thread/useCommandPaletteState.ts \
  src/components/thread/useWorkbenchTabsState.ts \
  src/components/thread/useFeishuWorkspaceState.ts \
  tests/preview-state.test.ts \
  tests/command-palette-state.test.ts \
  tests/feishu-workspace-state.test.ts
```

- [ ] **Step 8: knip 复跑——确认 thread/ 死文件清零**

Run: `cd web && npx knip --include files 2>&1 | grep "thread/" || echo "无 thread/ 死文件"`
Expected: 输出 `无 thread/ 死文件`(或仅剩本计划明确保留的活文件,不应再有 index/messages/agent-inbox/死 hook)。

- [ ] **Step 9: 提交(此步 tsc 仍会因 ThreadContext interface 未瘦身而在 value 缺字段处报错——留待 Task 5 一并过 tsc)**

```bash
git add -A && git commit -m "refactor(web): 改造 ThreadStateProvider 移除死状态/死 handler + 删死根 index.tsx 与 4 个死 hook"
```


### Task 5: 瘦身 `ThreadContext` interface + 清理死类型 import

**Files:**
- Modify: `web/src/components/thread/ThreadContext.tsx`(从 `ThreadContextProps` 删死字段 + 清理只被死字段用的 type import)

**Interfaces:**
- Consumes: 无(纯类型收敛)
- Produces: 瘦身后的 `ThreadContextProps`,仅含 Task 4 Step 6 的「保留键」;`useThread()`/`useThreadOptional()` 返回类型随之收窄。活消费方(`StudioContext` 10 字段 + `Shell` 2 字段)全在保留集内。

- [ ] **Step 1: 从 ThreadContextProps interface 删除死字段声明**

在 `web/src/components/thread/ThreadContext.tsx` 的 `ThreadContextProps` 中删除这些行(与 Task 4 Step 6 的 value 删除键一一对应):
`rightTab`([:30](web/src/components/thread/ThreadContext.tsx))、`setRightTab`([:31](web/src/components/thread/ThreadContext.tsx))、`selectedEvidence`([:32](web/src/components/thread/ThreadContext.tsx))、`setSelectedEvidence`([:33](web/src/components/thread/ThreadContext.tsx))、`viewMode`([:34](web/src/components/thread/ThreadContext.tsx))、`setViewMode`([:35](web/src/components/thread/ThreadContext.tsx))、`isEditingText`([:36](web/src/components/thread/ThreadContext.tsx))、`setIsEditingText`([:37](web/src/components/thread/ThreadContext.tsx))、`carouselIndex`([:42](web/src/components/thread/ThreadContext.tsx))、`setCarouselIndex`([:43](web/src/components/thread/ThreadContext.tsx))、`carouselImages`([:44](web/src/components/thread/ThreadContext.tsx))、`feishuChats`([:45](web/src/components/thread/ThreadContext.tsx))、`setFeishuChats`([:46](web/src/components/thread/ThreadContext.tsx))、`selectedChatId`([:47](web/src/components/thread/ThreadContext.tsx))、`setSelectedChatId`([:48](web/src/components/thread/ThreadContext.tsx))、`isFetchingChats`([:49](web/src/components/thread/ThreadContext.tsx))、`setIsFetchingChats`([:50](web/src/components/thread/ThreadContext.tsx))、`isSendingNotification`([:51](web/src/components/thread/ThreadContext.tsx))、`setIsSendingNotification`([:52](web/src/components/thread/ThreadContext.tsx))、`isFeishuActionPending`([:53](web/src/components/thread/ThreadContext.tsx))、`setIsFeishuActionPending`([:54](web/src/components/thread/ThreadContext.tsx))、`syncStepsVisible`([:55](web/src/components/thread/ThreadContext.tsx))、`setSyncStepsVisible`([:56](web/src/components/thread/ThreadContext.tsx))、`syncStep`([:57](web/src/components/thread/ThreadContext.tsx))、`setSyncStep`([:58](web/src/components/thread/ThreadContext.tsx))、`isFlying`([:61](web/src/components/thread/ThreadContext.tsx))、`setIsFlying`([:62](web/src/components/thread/ThreadContext.tsx))、`showCommandPalette`([:64](web/src/components/thread/ThreadContext.tsx))、`setShowCommandPalette`([:65](web/src/components/thread/ThreadContext.tsx))、`cmdSearch`([:66](web/src/components/thread/ThreadContext.tsx))、`setCmdSearch`([:67](web/src/components/thread/ThreadContext.tsx))、`bitableUrl`([:70](web/src/components/thread/ThreadContext.tsx))、`wikiUrl`([:71](web/src/components/thread/ThreadContext.tsx))、`handleSendNotification`([:76](web/src/components/thread/ThreadContext.tsx))、`handleInsertEmoji`([:77](web/src/components/thread/ThreadContext.tsx))、`handleAppendTag`([:78](web/src/components/thread/ThreadContext.tsx))、`handleEditBodyPaste`([:79](web/src/components/thread/ThreadContext.tsx))、`textareaRef`([:80](web/src/components/thread/ThreadContext.tsx))。

> 保留 `isSyncing`([:59](web/src/components/thread/ThreadContext.tsx))/`setIsSyncing`([:60](web/src/components/thread/ThreadContext.tsx))(活:同步守卫)与 Task 4 Step 6 保留键。`setViewMode`/`setCarouselIndex` 等的 setter 声明随其字段删除。

- [ ] **Step 2: 清理只被死字段用的 type import**

检查 `ThreadContext.tsx` 顶部 import 的类型(如 `SourceEvidence`):删死字段后若某 type 零引用,`grep -n "SourceEvidence" web/src/components/thread/ThreadContext.tsx` 确认仅剩 import 行后删除该 import。有他用则保留。

- [ ] **Step 3: 全量类型检查(裁决无活消费方遗漏)**

Run: `cd web && npx tsc --noEmit`
Expected: 零错误。若报 "Property 'xxx' does not exist on type ThreadContextProps",说明该字段仍有活消费方——回查是误删还是该消费方也属死代码,据实修正(优先相信 tsc:活消费方存在则该字段不该删)。

- [ ] **Step 4: lint**

Run: `cd web && npx eslint src`
Expected: 无 no-unused-vars / no-undef 错误。

- [ ] **Step 5: 提交**

```bash
git add web/src/components/thread/ThreadContext.tsx
git commit -m "refactor(web): ThreadContext 瘦身——移除死 UI 状态字段"
```


### Task 6: 全量验证 + 假数据零残留确认 + 部署

**Files:** 无改动(纯验证 + 部署)

**Interfaces:**
- Consumes: Task 1-5 的全部产出
- Produces: 生产环境运行最新代码,假数据清零

- [ ] **Step 1: 前端全量发布前门**

Run:
```bash
cd web
npx tsc --noEmit
npx eslint src
node scripts/run-unit-tests.mjs
npm run build
npx knip --include files 2>&1 | grep "components/thread/" || echo "thread/ 无死文件"
```
Expected: tsc 零错误;eslint 无错;单测全绿(3 个死 hook 测试已随删除消失);build 成功;knip 对 `components/thread/` 仅列本计划保留的活文件(index/messages/agent-inbox/死 hook 应已全部消失)。

- [ ] **Step 2: 假数据零残留确认**

Run:
```bash
cd web && grep -rn "张潇潇\|unsplash\|photo-1504280390\|露营分享\|户外美学" src/ && echo "!!! 仍有假数据残留" || echo "假数据清零"
```
Expected: `假数据清零`(生产 src/ 路径无任何假博主/假配图/假标签)。

- [ ] **Step 3: 后端全量回归 + 运行时 smoke**

Run:
```bash
uv run pytest tests/data_foundation -q
uv run python scripts/runtime_import_smoke.py
git diff --check
```
Expected: pytest 全绿;`agent=OK` 等全 OK;`git diff --check` 无空白错误。

- [ ] **Step 4: 运行时验证(preview 工具)**

起 dev server,验证活功能未被破坏:
1. `StudioShell` 正常渲染(preview_snapshot 见工作室界面,无白屏/报错)。
2. preview_console_logs 无 error(无 `undefined is not a function` 等 context 字段缺失错)。
3. 触发润色/瘦身/话题按钮 → preview_network 见 LangGraph stream 提交(`handleExecuteCommand` → `submitText` 活)。
4. 触发飞书同步按钮 → 见 `sync_copy_to_feishu` 相关提交(`handleSyncToFeishu` 活)。

若发现 context 字段缺失致运行时错,回 Task 5 核对该字段是否被误删。

- [ ] **Step 5: 推送**

Run: `git -c http.proxy= -c https.proxy= push origin master`
(失败改默认代理:`git push origin master`,见项目 memory)
Expected: 推送成功,远端 master 更新。

- [ ] **Step 6: 部署到服务器**

Run: `uv run python scripts/deploy.py`
Expected: pull → langgraph build → compose up → 健康检查 + smoke 全通过。

- [ ] **Step 7: 生产验证**

```bash
ssh -i ~/.ssh/xhs_deploy ubuntu@124.221.173.80 'cd /home/ubuntu/xiaohongshu-agent && git rev-parse HEAD && docker compose exec -T langgraph python scripts/runtime_import_smoke.py && python3 scripts/deploy_health_check.py --public-url http://127.0.0.1:9091/'
```
Expected: 服务器 HEAD == 本地 HEAD;`agent=OK`;`ok=True` + `public_http_status=200`。登录后 `StudioShell` 正常、三个活按钮 + 飞书同步触发对话、页面无假数据。

---

## Self-Review

**1. Spec 覆盖**:
- 硬约束(SDK 接线不动)→ Task 4 Step 4 保留 `handleExecuteCommand`/`handleSyncToFeishu` 的 `submitText`/`stream.submit` 链 ✅
- A 删除死文件 → Task 2(叶子+messages+agent-inbox)+ Task 3(辅助+history/index+mockup)+ Task 4 Step 7(index.tsx+4死hook)✅
- B 死 hook 整删无迁移 → Task 4 Step 1/7 ✅
- C provider 改造 → Task 4 ✅
- D ThreadContext 瘦身 → Task 5 ✅
- 后端 P1 → Task 1 ✅
- 测试策略(knip/tsc/eslint/unit/build + 后端 pytest/smoke)→ Task 6 ✅
- 部署与验证 → Task 6 Step 5-7 ✅

**2. 占位符扫描**:无 TBD/TODO;每个删除有精确文件列表 + 反向引用检查命令;provider 改造给出保留/删除键的完整清单 + 改造后 handler 完整代码;验证步骤有确切命令 + 预期。

**3. 类型/命名一致性**:
- Task 4 Step 6 的 value 删除键 == Task 5 Step 1 的 interface 删除字段(逐一对应)✅
- 活消费字段(10+2)在 Task 4/5 保留集内一致 ✅
- 后端 `repository as _repository` 别名使 14 处调用点不改名,与 spec 一致 ✅
- `isSyncing`/`isDirty` 全程标为活、保留,前后一致 ✅


