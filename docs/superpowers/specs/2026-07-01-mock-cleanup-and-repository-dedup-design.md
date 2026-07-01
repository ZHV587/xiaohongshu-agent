# 前端旧 Thread() 生态死代码清除(含假数据)+ 后端 `_repository` 去重 设计

> 状态:待评审 · 日期:2026-07-01 · 范围:前端旧 UI 死代码彻底清除(方案 C)+ 后端 P1 去重
> 权威依据:knip(死文件检测)+ 精确 import 追踪。**不用 `grep 单词` 判死活**(子串会误判,本轮自审已两次被骗)。

## 目标

1. **真实数据铁律**:清除前端仅存的硬编码假业务数据——`PhoneSimulator` 的「张潇潇/露营」假博主假笔记、`usePreviewState` 的 3 张 Unsplash 假配图。
2. **彻底删死代码(方案 C)**:删除旧 `Thread()` 三栏 UI 的整片死代码生态(~30 文件),并改造仍在调用死 hook 的活 `ThreadStateProvider`、瘦身 `ThreadContext`,使死 hook 可被彻底移除。
3. **后端 P1 去重**:`data_foundation/tools.py` 的 `_repository()` 收敛到 `studio_shared.repository()`。

## 硬约束:保留全部 LangGraph SDK 官方接线

前端↔agent 的官方契约是 **LangGraph SDK streaming client**(非 deepagents,deepagents 只管后端)。以下一字不动:
- `stream.submit({ messages, context, ...patch })`、`context`/state patch(后端 `InjectedState` 接)、`stream.*`
- `submitText`/`handleSubmit`/`handleRegenerate`、草稿自动保存、会话切换、错误处理
- 活 handler `handleExecuteCommand`(润色/瘦身/话题按钮)、`handleSyncToFeishu`(飞书同步,调 `sync_copy_to_feishu` 工具)

改造 provider 时,只摘除**死 UI 状态**(永不被任何活组件读取的字段),活 handler 的 `submitText`/`stream.submit` 调用链完整保留。

---

## 前端:活消费边界(已核实,决定去留)

`studio/` 活 UI 经 `useThread()` 实际消费的字段(**保留**):
`messages`、`isLoading`、`submitText`、`threadId`/`setThreadId`、`draftTitle`/`draftContent`/`setDraftTitle`/`setDraftContent`、`handleExecuteCommand`、`handleSyncToFeishu`。

> **注:`selectedEvidence` 不在此列。** studio 的 `selectedEvidence`(`CreationScreen`/`StudioShell`)来自 **`useStudio()`**(StudioContext 独立 state),与 `ThreadContext` 版是两个不同的东西;`ThreadContext.t.selectedEvidence` 无任何活消费方 → 死。故 `useWorkbenchTabsState` 整个死,不涉及迁移。

### 陷阱:混住活字段的死 hook

四个「死 hook」并非全死,逐字段甄别(已用精确 import 追踪核实来源):

| hook | 死字段(删) | 活字段(留,需迁移) |
|---|---|---|
| `usePreviewState` | `viewMode`/`setViewMode`、`carouselIndex`/`setCarouselIndex`、`carouselImages`(**假数据**) | `isEditingText`/`setIsEditingText`(provider 原位编辑器自适应高度用,[:129](../../web/src/components/thread/ThreadStateProvider.tsx)/[:133](../../web/src/components/thread/ThreadStateProvider.tsx)) |
| `useWorkbenchTabsState` | **全死**:`rightTab`/`setRightTab` + `selectedEvidence`/`setSelectedEvidence`(ThreadContext 版无活消费方) | 无 → **可整删,无需迁移** |
| `useCommandPaletteState` | `showCommandPalette`/`setShowCommandPalette`、`cmdSearch`/`setCmdSearch` | 无(但 `handleExecuteCommand` 内部调 `setShowCommandPalette`——见改造) |
| `useFeishuWorkspaceState` | `feishuChats`/`selectedChatId`/`isFetchingChats`/`isSendingNotification` 及其 setter | 无(但 `handleSyncToFeishu` 内部调 `setIsFeishuActionPending`——见改造) |

唯一需迁移的活字段是 `usePreviewState` 的 `isEditingText`;其余三个 hook 无活字段,整删。因活 handler(`handleExecuteCommand`/`handleSyncToFeishu`)内部仍调死 setter,需按下述改造剔除死副作用。

---

## 前端改动

### A. 删除的死文件(knip 确认 + 精确 import 复核)

旧 `Thread()` 生态,`studio/` 零 import:

- 组件:`index.tsx`(死根)、`ChatTimeline.tsx`、`ComposerPanel.tsx`、`RightInspector.tsx`、`PhoneSimulator.tsx`(**假数据**)、`CommandPalette.tsx`、`EvidenceInspector.tsx`、`MultimodalPreview.tsx`、`ContentBlocksPreview.tsx`
- `messages/` 整个目录(9 文件:ai/human/copy-card/topic-cards/search-cards/panel-card/evidence-time/generic-interrupt/shared)
- `agent-inbox/` 整个目录
- `history/index.tsx`(`ThreadHistory`,仅死根引用;⚠️ 目录内**只删这一个**)
- 辅助:`markdown-text.tsx`、`syntax-highlighter.tsx`、`markdown-styles.css`、`artifact-hooks.tsx`、`artifact-slot.tsx`
- lib/hooks:`lib/tool-render.tsx`、`lib/evidence-rank.ts`、`lib/agent-inbox-interrupt.ts`、`hooks/useMediaQuery.tsx`
- 根目录:`web/mockup.html`(设计原型,含假数据)

**保留(边界):** `artifact.tsx` + `artifact-context.ts`(page.tsx 的 `ArtifactProvider` 活用)、`ThreadContext.tsx`、`ThreadStateProvider.tsx`、`useThreadDraftState.ts`、`utils.ts`、`types.ts`;`history/` 下的 `FeishuConfigPage.tsx`/`LlmConfigPage.tsx`/`RuntimeFactsPage.tsx`(`AdminConfigPanel` 活用)+ `runtime-facts-format.ts`(被 `RuntimeFactsPage` 活用)。

> 每个删除文件先 `grep "import.*<名>"` 精确复核活引用为零;最终以 knip 复跑 + `tsc --noEmit` 零错误为准。测试文件(`preview-state.test.ts`/`command-palette-state.test.ts`/`feishu-workspace-state.test.ts` 等)随被测死代码一并删除。

### B. 死 hook 的活字段迁移 + 文件删除

1. **`usePreviewState.ts` → 删文件**;`isEditingText` 活逻辑迁入 `ThreadStateProvider` 本地 `useState`(一行 `const [isEditingText, setIsEditingText] = useState(false)`)。假数据(`carouselImages`)随文件删除消失。
2. **`useWorkbenchTabsState.ts` → 删文件**(整死:`rightTab` + `selectedEvidence` 均无活消费方,`selectedEvidence` 活消费来自 `useStudio()` 而非此处)。无字段迁移。
3. **`useCommandPaletteState.ts` → 删文件**;`showCommandPalette`/`cmdSearch` 死状态丢弃(见 C 对 `handleExecuteCommand` 的处理)。
4. **`useFeishuWorkspaceState.ts` → 删文件**;死状态丢弃(见 C 对 `handleSyncToFeishu` 的处理)。

### C. `ThreadStateProvider.tsx` 改造(保留活逻辑,移除死状态)

- 删除对 4 个死 hook 的 import 与调用;`isEditingText` 改为本地 `useState`。(`selectedEvidence` 无需迁移——ThreadContext 版是死的。)
- **`handleExecuteCommand`**:保留(活)。移除内部 `setShowCommandPalette(false)`(命令面板弹窗已删,该状态无意义);`submitText(...)` 调用链不动。
- **`handleSyncToFeishu`**:保留(活)。移除内部对死状态的 set(`setIsFlying`/`setSyncStep`/`setSyncStepsVisible`/`setIsFeishuActionPending`——这些字段无活 UI 读取);保留 `submitText(sync_copy_to_feishu ...)` 与 `setIsSyncing` 守卫逻辑(防重复提交,`isSyncing` 保留为本地态)。
- **删除死 handler**:`handleSendNotification`、`handleInsertEmoji`、`handleAppendTag`(均无活引用)。
- 清理相关本地 `useState`:`isFlying`/`syncStep`/`syncStepsVisible`/`bitableUrl`/`wikiUrl` 等仅死 UI 用的状态,连同 [:94-111](../../web/src/components/thread/ThreadStateProvider.tsx) 的 bitable/wiki 拉取 `useEffect`(仅喂死字段)一并移除——**逐个 grep 确认无活消费方**后删。

### D. `ThreadContext.tsx` 瘦身

从 `ThreadContextProps` interface 与 provider `value` 中移除所有死字段:`rightTab`/`viewMode`/`carouselIndex`/`carouselImages`/`selectedEvidence`(ThreadContext 版)/`showCommandPalette`/`cmdSearch`/`feishuChats`/`selectedChatId`/`isFetchingChats`/`isSendingNotification`/`isFeishuActionPending`/`syncStepsVisible`/`syncStep`/`isFlying`/`bitableUrl`/`wikiUrl` 及死 handler。保留活字段(见「活消费边界」)。以 `tsc --noEmit` 零错误确认无活消费方遗漏。

---

## 后端改动(P1)

`tools.py:42` 的 `_repository()` 与 `studio_shared.py:33` 的 `repository()` 实现逐字相同。

1. 删 `tools.py:41-47` 的 `_repository()` 定义。
2. `tools.py:26` 的 import 扩为 `from data_foundation.studio_shared import is_admin_open_id, repository as _repository`——用 `as _repository` 别名,**14 处调用点**(148/193/243/324/356/378/387/428/450/472/494/514/580)零改名。
3. 清理因删定义不再使用的 import:`Iterator`([:5](../../data_foundation/tools.py))、`contextmanager`([:6](../../data_foundation/tools.py))、`ResourceRepository`([:32](../../data_foundation/tools.py))、`connect`([:21](../../data_foundation/tools.py))——**已核实**四者除 `_repository()` 定义外在 `tools.py` 内零他用,可全部删除。

对 deepagents 拓展面零影响:`@tool`/`tools=`/`RunnableConfig` 全不变,仅工具函数体内部 db helper 来源收敛。

---

## 测试策略

### 前端(权威工具,非 grep)
1. **knip 复跑**:`npx knip` —— 删除后 `thread/` 死文件清单应清空(仅剩本设计保留的活文件)。
2. **类型**:`cd web && npx tsc --noEmit` 零错误(证明 context 瘦身无活消费方遗漏)。
3. **lint**:`npx eslint src` 无 no-unused/no-undef。
4. **单测**:`node scripts/run-unit-tests.mjs`(删死 hook 测试后应全绿)。
5. **构建**:`npm run build` 通过。
6. **运行时(preview 工具)**:`StudioShell` 正常渲染 → 润色/瘦身/话题按钮触发 `submitText`(network 见 stream 提交)→ 飞书同步按钮触发 `sync_copy_to_feishu`(HITL 确认流)→ 草稿编辑器自适应高度正常 → 全站确认「张潇潇/unsplash/露营」假数据在生产路径零残留。

### 后端
1. `uv run pytest tests/data_foundation -q` 全绿。
2. `uv run python scripts/runtime_import_smoke.py` — `agent=OK`,无循环 import。
3. `import agent` 工具计数不变(去重不改工具数)。

## 部署与验证
1. 发布前门:后端 pytest + web(knip/tsc/eslint/unit/build)+ `git diff --check`。
2. 推送:`git -c http.proxy= -c https.proxy= push origin master`(失败改默认代理 `git push`)。
3. 部署:`uv run python scripts/deploy.py`。
4. 生产验证:登录 → `StudioShell` 正常 → 三个活按钮 + 飞书同步触发对话 → 页面无假数据。

## 风险

| 风险 | 缓解 |
|---|---|
| context 瘦身误删活字段致运行时 undefined | `selectedEvidence` 已核实来自 `useStudio()`(非 ThreadContext),ThreadContext 版是死的可删;`tsc --noEmit` 强制全消费方类型对齐兜底 |
| 活 handler 内死 setter 移除后残留悬空引用 | 逐 handler 核内部依赖;编译期 + eslint no-undef 兜底 |
| knip 误报(漏动态入口)误删活文件 | knip 结果 + 精确 import 复核双重确认;`tsc`/`build` 最终裁决 |
| 删 artifact-hooks/slot 波及活 artifact.tsx | 已核实 `artifact.tsx`/`artifact-context.ts` 活、`artifact-hooks`/`artifact-slot` 仅死 `messages/ai` 用 |
| P1 删 import 误删仍用的 | 逐个 grep,有他用则留 |
| 触碰 SDK 官方接线 | 硬约束:submit/context/stream/活 handler 的 submitText 链不动 |

## 提交规划
1. `fix(web): 删除旧 Thread() 生态死代码(含 PhoneSimulator 假数据)+ 迁移活字段至 provider`
2. `refactor(web): ThreadContext 瘦身——移除死 UI 状态字段`
3. `refactor(data_foundation): tools.py 复用 studio_shared.repository(消除 _repository 复制)`
