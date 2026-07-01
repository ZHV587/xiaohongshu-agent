# 前端死代码/假数据清理 + 后端 `_repository` 去重 设计

> 状态:待评审 · 日期:2026-07-01 · 范围:前端死子树清理(含假数据)+ 后端 P1 去重

## 目标

一轮低风险清理,兑现两个既有目标,**不删减任何在用功能**:

1. **真实数据铁律**:清除前端仅存的硬编码假业务数据(`PhoneSimulator` 的「张潇潇/露营」假博主假笔记、`usePreviewState` 的 3 张 Unsplash 假配图),连同承载它们的、生产入口零引用的旧 `Thread()` 三栏 UI 死子树。
2. **本轮解耦收尾(P1)**:把 `data_foundation/tools.py` 里与 `studio_shared.repository()` 逐字重复的 `_repository()` 上下文管理器收敛掉——这是上一轮三层解耦想消灭的复制粘贴中漏掉的最后一处。

## 非目标(明确排除,留待下一轮)

- 后端 P2(`repositories/resource.py` 1110 行拆分)、P4(`internal_api.py` 抽 `internal_auth.py`)——结构性重构,单独评估。
- `ThreadContext` 巨型 context 瘦身(删 `viewMode`/`rightTab`/`isFlying`/`syncStep` 等死字段)——属大 context 拆分,回归面大,下一轮。
- `useFeishuWorkspaceState` / `useWorkbenchTabsState` 相关灰色字段——虽当前 `StudioShell` 无 UI 入口,但飞书通知牵扯真实 SDK 接线(见硬约束),本轮一律不碰。

## 硬约束:保留全部 LangGraph SDK 官方接线

前端与 agent 的官方集成契约是 **LangGraph SDK streaming client**(不是 deepagents——deepagents 只管后端)。这套接线全部活在 `ThreadStateProvider` 内,本轮**一字不动**:

- `stream.submit({ messages, context, ...patch })`([ThreadStateProvider.tsx:167](../../web/src/components/thread/ThreadStateProvider.tsx))— 官方提交入口
- `context` / state patch — 前端喂权威数据给 agent 的官方通道(后端 `InjectedState` 接)
- `submitText` / `handleSubmit` / `handleRegenerate` / 飞书 HITL(`handleSyncToFeishu`/`handleSendNotification`)/ 草稿自动保存 / 会话切换 — 全保留

判据:凡触碰 `stream.submit`、`context`、`stream.*`、飞书工具调用的代码,一律视为官方接线,不在删除范围。删除对象仅限**纯展示、零 SDK 调用、且已被 `StudioShell` 取代**的旧 UI 残骸。

---

## 前端改动

### 现状(已核实)

生产入口链:`page.tsx` → `AppShell`([AppShell.tsx](../../web/src/components/AppShell.tsx))→ `ThreadStateProvider`(活,持全部 SDK 接线)→ `StudioProvider` → `StudioShell`。

旧 `Thread()` 三栏组件([thread/index.tsx](../../web/src/components/thread/index.tsx))**全项目零 import**,是死根。它拖着一棵只由它引用的展示子树。活 UI(`studio/`)对这棵子树的字段消费**仅一处**:`StudioContext.tsx:482-484` 调 `t.handleExecuteCommand(...)`(润色/瘦身/话题三个活按钮)——该函数活在 `ThreadStateProvider`,依赖 `submitText` + `setShowCommandPalette`,**不依赖**被删文件。

### A. 删除的文件(纯展示死代码,零 SDK 接线)

| 文件 | 理由 |
|---|---|
| `web/src/components/thread/index.tsx` | 死根 `Thread()`,零 import |
| `web/src/components/thread/PhoneSimulator.tsx` | **含假数据**(张潇潇/露营/写死标签),仅 `index.tsx` 引用 |
| `web/src/components/thread/ChatTimeline.tsx` | 仅 `index.tsx` 引用 |
| `web/src/components/thread/ComposerPanel.tsx` | 仅 `ChatTimeline` 引用 |
| `web/src/components/thread/RightInspector.tsx` | 仅 `index.tsx` 引用 |
| `web/src/components/thread/CommandPalette.tsx` | 命令面板**弹窗 UI**,仅 `index.tsx`/`ComposerPanel` 引用(注:state hook `useCommandPaletteState` 是活的,**保留**) |
| `web/mockup.html` | 根目录设计原型(63KB,含假数据),Next 不 serve、无引用 |

> 删除前逐一 `grep` 复核引用数,确保除死子树内部外无活引用(见测试策略)。

### B. 就地清理假数据(保留活逻辑)

`web/src/components/thread/usePreviewState.ts` **混住活与死**:
- **活**:`isEditingText`/`setIsEditingText` 被 `ThreadStateProvider` 原位编辑器自适应高度逻辑消费([:129](../../web/src/components/thread/ThreadStateProvider.tsx)、[:344](../../web/src/components/thread/ThreadStateProvider.tsx))。
- **死+假**:`carouselImages`(3 张 Unsplash 假图)、`viewMode`、`carouselIndex` 仅被已删的 `PhoneSimulator` 读。

**做法**:保留 `usePreviewState` 结构不动,仅把 `createPreviewInitialState()` 里的 `carouselImages` 假 URL 数组改为 `[]`。这样假数据 100% 清除、`isEditingText` 活逻辑零影响、`ThreadContext` 形状不变(死字段留空,清理留待下一轮 context 瘦身)。

> 与后端一致的空态语义:`StudioContext.tsx` 的配图早已是 `useMemo(() => [], [])` 真实空容器 + 按 `images.length` 守卫。此改动使 `usePreviewState` 对齐同一「无源即空」范式。

### C. `ThreadStateProvider` 不改

`usePreviewState` 保留 → provider 对它的调用与灌进 context 的字段全部不动。`handleExecuteCommand`/`submitText`/飞书 HITL/草稿全保留。**前端唯一实际改动是 B 的一行数组 + A 的删文件。**

---

## 后端改动(P1)

`data_foundation/tools.py:42` 的 `_repository()` 与 `data_foundation/studio_shared.py:33` 的 `repository()` 实现逐字相同(`connect()` → `ResourceRepository` → `close()`,均 `@contextmanager`)。

**做法**:
1. 删除 `tools.py:41-47` 的 `_repository()` 定义。
2. `tools.py:26` 已有 `from data_foundation.studio_shared import is_admin_open_id`,扩为 `import (is_admin_open_id, repository as _repository)`——用 `as _repository` 别名,**14 处调用点** `with _repository() as repo`([tools.py](../../data_foundation/tools.py) 行 148/193/243/324/356/378/387/428/450/472/494/514/580)**无需逐一改名**,零调用点改动。
3. 清理因删定义而不再使用的 import:`Iterator`([:5](../../data_foundation/tools.py))、`contextmanager`([:6](../../data_foundation/tools.py))、`ResourceRepository`([:32](../../data_foundation/tools.py))、`connect`——**前提是删定义后模块内确无其他使用者**;逐个 `grep` 确认后再删,有他用则保留。

对 deepagents 的拓展面零影响:`@tool` 装饰、`tools=` 列表挂载、`RunnableConfig` 取身份全不变;改的仅是工具函数体内部 db helper 的来源。

---

## 测试策略

### 前端

1. **删除前**:对每个待删文件 `grep -rn "<basename>" web/src` 复核,确认引用仅来自死子树内部(`index.tsx` / 被删链)。
2. **静态验证**:`cd web && npx tsc --noEmit`(类型零错误)+ `npx eslint src`(无 no-unused/no-undef)——证明无活代码引用被删符号。
3. **构建**:`cd web && npm run build` 通过。
4. **运行时验证(preview 工具)**:起 dev server → `StudioShell` 正常渲染 → 三个活按钮(润色/瘦身/话题)仍触发 `submitText`(console/network 见 stream 提交)→ 草稿编辑器自适应高度正常(`isEditingText` 活逻辑未断)→ 全站 `grep` 确认「张潇潇」「unsplash」「露营」假数据在 `web/src` 生产路径零残留。

### 后端

1. `uv run pytest tests/data_foundation -q` 全绿(工具行为不变)。
2. `uv run python scripts/runtime_import_smoke.py` — `agent=OK`,无循环 import。
3. agent 装配 smoke:`import agent` 后工具计数不变(去重不改工具数量)。

## 部署与验证

1. 本地发布前门:后端 `uv run pytest tests/data_foundation -q` + `web` 三件套(tsc/eslint/build)+ `git diff --check`。
2. 推送:`git -c http.proxy= -c https.proxy= push origin master`(失败改默认代理 `git push`,见项目 memory)。
3. 部署:`uv run python scripts/deploy.py`(pull → langgraph build → compose up → 健康检查 + smoke)。
4. 生产验证:登录 → `StudioShell` 正常 → 润色/瘦身/话题按钮触发对话 → 页面无假数据。

## 风险

| 风险 | 缓解 |
|---|---|
| 误删活文件 | 删前逐一 grep 复核引用;tsc+eslint 兜底 |
| `usePreviewState` 活字段 `isEditingText` 被牵动 | 只改 `carouselImages` 一行,不动 hook 结构与其余字段 |
| P1 删 import 误删仍在用的 | 逐个 grep 确认无其他使用者再删,有他用则留 |
| 触碰 SDK 官方接线 | 硬约束:凡碰 `stream.submit`/`context`/飞书工具的代码不在删除范围 |

## 提交规划

1. `fix(web): 清除 PhoneSimulator/usePreviewState 假业务数据 + 删旧 Thread() 死代码子树`
2. `refactor(data_foundation): tools.py 复用 studio_shared.repository(消除 _repository 复制)`
