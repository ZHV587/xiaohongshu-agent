# Web Desktop Design System Parity Implementation Plan

> **Superseded on 2026-07-03:** This plan is no longer the production execution source of truth. It treated Studio `Tweaks`, multi-layout exploration variants, and Workbench phone preview as parity targets. The user has since clarified that production must implement only the final approved web desktop experience. Use `docs/superpowers/plans/2026-07-03-web-production-final-design-system-alignment.md` instead.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Web desktop production UI into complete 1:1 alignment with `小红书文案助手 Design System/` for the Studio and Workbench starting points, while explicitly excluding mobile responsiveness for now.

**2026-07-03 user override:** Mobile/phone preview functionality is no longer required and has been removed from production desktop surfaces. `PhonePreview`, Workbench mobile preview tabs, Studio phone-frame preview panels, and production `PhoneFrame`/`NoteCard` preview usage are intentionally superseded by the latest request. Feishu sync, desktop Studio/Workbench flows, thinking UI, response UI, and copy actions remain in scope.

**Architecture:** Treat the design-system folder as the source of truth and production React as the integration target. Lock each parity area with a failing static or browser-level test first, then implement the smallest production change that connects real state and real backend wiring without reintroducing prototype mock business data.

**Tech Stack:** Next.js 15, React, TypeScript, CSS custom properties, existing DS primitives in `web/src/components/ds`, Node test runner, Playwright via `@playwright/test`.

---

## Scope And Non-Scope

**In scope:**
- Desktop viewport only: `1440x900`, `1440x960`, and `1360x860`.
- Design System source paths:
  - `小红书文案助手 Design System/_ds_manifest.json`
  - `小红书文案助手 Design System/tokens/*.css`
  - `小红书文案助手 Design System/styles.css`
  - `小红书文案助手 Design System/components/**`
  - `小红书文案助手 Design System/ui_kits/studio/**`
  - `小红书文案助手 Design System/ui_kits/workbench/**`
- Production targets:
  - `web/src/app/globals.css`
  - `web/src/components/ds/**`
  - `web/src/components/studio/**`
  - `web/src/components/workbench/**`
  - `web/src/components/AppShell.tsx`
  - `web/tests/ds-production-adherence.test.ts`
  - `web/tests/ds-ui-kit-alignment.test.ts`

**Out of scope for this plan:**
- Mobile responsive layout.
- Replacing real backend data with prototype mock data.
- Git commits unless explicitly requested by the user.
- Large unrelated refactors such as moving `StudioContext` exports solely to remove Fast Refresh warnings.

---

## File Responsibility Map

- `web/tests/ds-production-adherence.test.ts`: static source-of-truth parity tests for tokens, DS primitive usage, manifest component usage, and forbidden legacy UI imports.
- `web/tests/ds-ui-kit-alignment.test.ts`: static production wiring tests for Studio and Workbench UI-kit features, layout variants, motion markers, and desktop accessibility.
- `web/src/app/globals.css`: global design tokens, DS utility classes, motion keyframes, focus visibility, and shared scroll/fly/shimmer styles.
- `web/src/components/ds/**`: production DS primitives that must mirror `小红书文案助手 Design System/components/**`.
- `web/src/components/studio/StudioShell.tsx`: Studio starting point, section composition, desktop landmark, and Tweaks wiring.
- `web/src/components/studio/TweaksPanel.tsx`: reusable production port of `ui_kits/studio/tweaks-panel.jsx`.
- `web/src/components/studio/CreationScreen.tsx`: Studio creation view including chat, topic rail, right-panel layouts, preview, evidence panel, and trends.
- `web/src/components/studio/DeepCreation.tsx`: Deep creation variants: immersive, flow, workspace.
- `web/src/components/studio/Operations.tsx`: Account operations variants: page, inline, hybrid.
- `web/src/components/workbench/WorkbenchShell.tsx`: Workbench starting point, top bar, sidebar reuse, chat pane, command palette, right canvas, phone preview, Feishu sync, copy bar, and motion.

---

## Acceptance Matrix

| Area | Source Of Truth | Production Target | Required Acceptance |
|---|---|---|---|
| Tokens | `tokens/*.css` | `globals.css` | Every token name exists in production globals. |
| DS primitives | `components/**` | `web/src/components/ds/**` | Every manifest component has production usage outside DS library. |
| Studio root | `ui_kits/studio/app.jsx` | `StudioShell.tsx` | `create`, `deep`, `ops` sections wired; desktop `main` and `h1` present. |
| Studio Tweaks | `ui_kits/studio/tweaks-panel.jsx` | `TweaksPanel.tsx`, `StudioShell.tsx` | Panel opens, has segmented radios, supports host edit-mode messages, controls variants. |
| Studio creation | `ui_kits/studio/CreationScreen.jsx` | `CreationScreen.tsx` | `stack`, `split`, `composer`; topic rail; draft/phone preview; evidence slide-over. |
| Studio deep | `ui_kits/studio/DeepCreation.jsx`, `DeepEditor.jsx` | `DeepCreation.tsx`, `DeepEditor.tsx` | `immersive`, `flow`, `workspace`; editor, assistant, evidence, preview panels. |
| Studio ops | `ui_kits/studio/Operations.jsx` | `Operations.tsx` | `page`, `inline`, `hybrid`; dashboard, calendar, library, backfill, pipeline states. |
| Workbench root | `ui_kits/workbench/app.jsx` | `WorkbenchShell.tsx` | Sidebar + chat + right canvas; `Ctrl+P`; reauth; fly-to-sync motion. |
| Workbench sidebar | `Sidebar.jsx` | `WorkbenchShell.tsx`, `Recents` integration | New chat CTA, recent list semantics, active item styling, admin/config affordance preserved. |
| Workbench chat | `ChatPane.jsx` | `WorkbenchShell.tsx` | Topic cards, writing spinner, command affordance, composer footer, send action. |
| ThinkingAura source | `components/content/ThinkingAura.jsx` | `ThinkingAura.tsx`, `globals.css` | Ping dot, done/active/pending stepper, collapsible logs, timestamps, default open/collapsed behavior. |
| Thinking trace mapping | live LangGraph messages/tool calls | `thinking-trace.ts`, `StudioContext.tsx` | User, AI, thinking, tool-call, tool-result, streaming and completed states are derived from real timeline data. |
| Conversation response UI | `ChatPane.jsx`, `CreationScreen.jsx` | `CreationScreen.tsx`, `WorkbenchShell.tsx` | User bubble, thinking panel, topic response, writing/streaming status, final response, empty/loading/error states. |
| Workbench top bar | `TopBar.jsx` | `WorkbenchShell.tsx` | Brand lockup, Ready badge, reauth prompt language and action. |
| Workbench right canvas | `RightCanvas.jsx`, `PhonePreview.jsx` | `WorkbenchShell.tsx` | Tab header, detail/feed segmented control, phone preview, bottom copy bar. |
| Workbench Feishu | `FeishuSync.jsx` | `WorkbenchShell.tsx` | Bitable card, group notify card, progress steps, QR flip-card reauth. |
| Workbench palette | `CommandPalette.jsx` | `WorkbenchShell.tsx` | Search input, filtered commands, Esc close affordance, command actions. |
| Studio shell/history | `Shell.jsx` | `Shell.tsx` | Top bar, section switcher, recents/sidebar behavior, active item styling, admin panel entry. |
| Studio composer | `Composer.jsx` | `Composer.tsx`, `DeepEditor.tsx`, creation/deep views | Copy doctor, score/schedule bar, emoji insertion, visual studio, risk panel, version controls. |
| Primitive source parity | `components/**/*.jsx` | `web/src/components/ds/**` | Prop APIs, variants, focus/hover/loading/dim states match DS source where production uses them. |
| Brand guidelines | `guidelines/*.card.html`, `styles.css` | `globals.css`, production screens | Logo, radius, elevation, typography, spacing, dark theme and semantic colors are represented or intentionally excluded. |
| Desktop UAT | manifest viewports | Playwright script | No page errors, no console errors, no failed requests, no horizontal overflow at desktop width. |

---

## Task 1: Freeze The Design System Inventory

**Files:**
- Modify: `web/tests/ds-production-adherence.test.ts`
- Read: `小红书文案助手 Design System/_ds_manifest.json`
- Read: `小红书文案助手 Design System/ui_kits/studio/*.jsx`
- Read: `小红书文案助手 Design System/ui_kits/workbench/*.jsx`

- [x] **Step 1: Write the failing inventory completeness test**

Add a test named `design-system desktop starting points have production parity tests`. It must assert that `ds-ui-kit-alignment.test.ts` includes test names for:

```ts
[
  "studio production shell exposes the DS Tweaks variants",
  "creation screen supports all DS right-panel layouts",
  "deep creation supports all DS forms and supporting panels",
  "operations screen supports all DS hosting variants",
  "workbench starting point has a production entry and DS interaction affordances",
  "workbench right canvas carries the DS bottom copy bar",
  "workbench command palette mirrors the DS searchable palette",
  "workbench feishu sync mirrors the DS sync cards and flip auth",
  "desktop shells expose accessible landmarks and keyboard focus affordances",
]
```

- [x] **Step 2: Run the test to verify it fails**

Run:

```powershell
cd E:\小红书智能体\web
npm run test:unit -- --test-name-pattern "design-system desktop starting points"
```

Expected: FAIL listing missing test-name strings.

- [x] **Step 3: Add missing static test shells**

Add the missing test cases to `web/tests/ds-ui-kit-alignment.test.ts`. Each shell should use `assertIncludes` against concrete production files. Do not write production code in this task.

- [x] **Step 4: Run the test to verify it passes**

Run:

```powershell
npm run test:unit -- --test-name-pattern "design-system desktop starting points|workbench command palette|workbench feishu sync"
```

Expected: Inventory test passes; newly added command/Feishu tests may fail until their implementation tasks.

---

## Task 2: Complete Workbench TopBar Parity

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/TopBar.jsx`

- [x] **Step 1: Write the failing TopBar test**

Add a test named `workbench top bar mirrors DS brand and reauth prompt` asserting `WorkbenchShell.tsx` contains:

```ts
[
  "小红书文案助手",
  "v1.2 工作台",
  "飞书 CLI 状态：Ready (bot)",
  "User 身份已过期，点此扫码重连",
  "setTab(\"feishu\")",
  "setScanned(false)",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench top bar mirrors"
```

Expected: FAIL for any missing literal.

- [x] **Step 3: Implement minimal TopBar parity**

Update `WorkbenchTopBar` to use the DS literal title/subtitle/status/reauth copy while preserving existing production actions:

```tsx
<span>小红书文案助手</span>
<span>v1.2 工作台</span>
<Badge tone="synced" dot>飞书 CLI 状态：Ready (bot)</Badge>
<Button ...>User 身份已过期，点此扫码重连</Button>
```

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench top bar mirrors"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 3: Complete Workbench RightCanvas Header And Bottom Bar

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/RightCanvas.jsx`

- [x] **Step 1: Write the failing RightCanvas structural test**

Assert `WorkbenchShell.tsx` contains:

```ts
[
  "📱 小红书手机预览",
  "🔗 飞书同步协作",
  "详情视窗",
  "瀑布流卡片",
  "RightCanvasBottomBar",
  "文案长度",
  "一键复制纯文案",
  "navigator.clipboard.writeText",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench right canvas"
```

Expected: FAIL for missing labels or copy bar.

- [x] **Step 3: Implement header and bottom bar**

Update `RightCanvas`:
- Use two tab labels exactly: `📱 小红书手机预览`, `🔗 飞书同步协作`.
- Move detail/feed segmented control into the tab header, visible only for mock tab.
- Keep `RightCanvasBottomBar` at the bottom with `文案长度：{body.length} / 1000 字`.
- Keep `CopyButton` using `navigator.clipboard.writeText(body)` and `已复制` feedback.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench right canvas"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 4: Complete Workbench PhonePreview Detail And Feed Parity

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/PhonePreview.jsx`

- [x] **Step 1: Write the failing PhonePreview test**

Assert `WorkbenchShell.tsx` contains:

```ts
[
  "笔记详情",
  "点赞",
  "收藏",
  "评论",
  "关注",
  "发现",
  "附近",
  "PhoneFrame width={330}",
  "NoteCard dim",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench phone preview"
```

Expected: FAIL until missing phone detail/feed structure is present.

- [x] **Step 3: Implement desktop phone detail/feed structure**

Inside `PhonePreview`:
- Detail mode must render a phone top nav with `笔记详情`.
- Detail mode must render author row, follow button, title/body, and bottom action row with `点赞`, `收藏`, `评论`.
- Feed mode must render top tabs `关注`, `发现`, `附近`, and a two-column feed using `NoteCard` plus dim cards.
- Continue using real `note`, `images`, and `user`; never import `XHS_DATA`.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench phone preview"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 5: Complete Workbench FeishuSync Parity

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/FeishuSync.jsx`

- [x] **Step 1: Write the failing FeishuSync test**

Assert `WorkbenchShell.tsx` contains:

```ts
[
  "同步到飞书多维表格",
  "APP Token: bascnu",
  "绑定选题记录",
  "飞书文档列映射",
  "字数检测",
  "立即同步至飞书多维表格",
  "群发通知与协同审核",
  "选择接收通知的飞书群聊",
  "一键发送通知至飞书群聊",
  "飞书个人身份已过期",
  "飞书个人身份重连成功",
  "setSyncing",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench feishu sync mirrors"
```

Expected: FAIL until FeishuSync is fully ported.

- [x] **Step 3: Implement FeishuSync cards**

Update `FeishuSync`:
- Add Bitable write `Card` with `Row`, `KV`, and connection badge.
- Add sync progress state `steps` and `syncing`.
- Add group notify `Card` using production `Select`.
- Keep QR flip-card reauth using `rotateY(180deg)`.
- Use current production `note` data for title/body length.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench feishu sync mirrors"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 6: Complete Workbench CommandPalette Search Parity

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/CommandPalette.jsx`

- [x] **Step 1: Write the failing CommandPalette test**

Assert `WorkbenchShell.tsx` contains:

```ts
[
  "Input",
  "输入命令或搜索动作",
  "ESC",
  "无匹配命令",
  "setQuery",
  "commands.filter",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench command palette mirrors"
```

Expected: FAIL until the palette has searchable command UI.

- [x] **Step 3: Implement searchable palette**

Update `CommandPalette`:
- Import or reuse DS `Input`.
- Add `const [query, setQuery] = useState("")`.
- Define commands with `id`, `name`, `desc`, `icon`, `color`.
- Render filtered commands with `commands.filter((command) => (command.name + command.desc).toLowerCase().includes(query.toLowerCase()))`.
- Render `无匹配命令` for empty results.
- Keep existing `onRun` actions wired to production actions.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench command palette mirrors"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 7: Complete ThinkingAura Source Parity

**Files:**
- Modify: `web/tests/ds-production-adherence.test.ts`
- Modify: `web/tests/thinking-aura-collapsed.test.ts`
- Modify: `web/src/components/ds/content/ThinkingAura.tsx`
- Modify if required: `web/src/app/globals.css`
- Source: `小红书文案助手 Design System/components/content/ThinkingAura.jsx`

- [x] **Step 1: Write the failing ThinkingAura source-parity tests**

Assert production `ThinkingAura.tsx` and `globals.css` contain the DS contract:

```ts
[
  "思考轨迹 (Thinking Aura)",
  "steps",
  "logs",
  "defaultOpen",
  "defaultCollapsed",
  "xhs-ping",
  "收起分析详情",
  "展开分析详情",
  "done",
  "active",
  "pending",
  "✓",
  "◐",
  "○",
  "font-mono",
]
```

Also assert `globals.css` contains the ThinkingAura motion markers:

```ts
[
  "@keyframes xhs-ping",
  "spin 1.4s linear infinite",
]
```

- [x] **Step 2: Run the failing tests**

```powershell
cd E:\小红书智能体\web
npm run test:unit -- --test-name-pattern "ThinkingAura|thinking aura"
```

Expected: FAIL for any missing prop, literal, status, or motion marker.

- [x] **Step 3: Implement source parity without changing consumers**

Patch `ThinkingAura.tsx` only for primitive-level gaps:
- Preserve existing TypeScript API compatibility.
- Support DS `defaultOpen` while keeping any existing `defaultCollapsed` compatibility.
- Render title `思考轨迹 (Thinking Aura)` by default.
- Render the coral ping dot using `xhs-ping`.
- Render done/active/pending visual states exactly enough to satisfy DS markers.
- Render collapsible log rows with visible timestamps and monospace time styling.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "ThinkingAura|thinking aura"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 8: Complete Timeline And Tool-Call Response Mapping

**Files:**
- Modify: `web/tests/studio-timeline.test.ts`
- Modify: `web/tests/creation-timeline-render.test.ts`
- Modify: `web/src/lib/thinking-trace.ts`
- Modify if required: `web/src/components/studio/StudioContext.tsx`

- [x] **Step 1: Write failing timeline mapping tests**

Add tests proving real LangGraph thread data maps into UI-ready response items:
- Human messages render as user conversation bubbles.
- Final AI messages render as assistant response bubbles.
- AI messages with tool calls render an active `thinking` item.
- Tool messages render log rows under the matching thinking item.
- Completed runs collapse thinking details by default.
- Current loading run remains expanded and active.
- Tool-only intermediate messages do not produce fake final assistant prose.
- Tool logs are stringified safely and never render raw `[object Object]`.

- [x] **Step 2: Run the failing timeline tests**

```powershell
npm run test:unit -- --test-name-pattern "timeline|thinking trace|creation timeline"
```

Expected: FAIL for any missing mapping behavior.

- [x] **Step 3: Implement the mapping**

Patch `thinking-trace.ts` so it exposes stable conversation item shapes for:

```ts
[
  "user",
  "assistant",
  "thinking",
  "tool-call",
  "tool-result",
  "loading",
  "error",
]
```

Rules:
- Use real thread messages and production loading/error state.
- Do not synthesize prototype-only reasoning content.
- Derive step `state` as `active`, `done`, or `pending` from real message order and loading status.
- Keep raw backend payloads out of visible UI unless they are sanitized for logs.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "timeline|thinking trace|creation timeline"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 9: Complete Studio Conversation Response UI

**Files:**
- Modify: `web/tests/creation-timeline-render.test.ts`
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/studio/CreationScreen.tsx`
- Source: `小红书文案助手 Design System/ui_kits/studio/CreationScreen.jsx`

- [x] **Step 1: Write the failing Studio response UI tests**

Assert `CreationScreen.tsx` contains:

```ts
[
  "ChatColumn",
  "timeline.map",
  "item.kind === \"thinking\"",
  "ThinkingAura",
  "defaultCollapsed",
  "logs={item.run.logs.length ? item.run.logs : null}",
  "正在思考并检索数据底座",
  "item.kind === \"user\"",
  "item.kind === \"assistant\"",
  "StateNote",
]
```

- [x] **Step 2: Run the failing tests**

```powershell
npm run test:unit -- --test-name-pattern "creation timeline|studio conversation response"
```

Expected: FAIL if Studio chat does not render all response states explicitly.

- [x] **Step 3: Implement Studio response parity**

Patch `ChatColumn` in `CreationScreen.tsx`:
- Render user bubbles, assistant bubbles, and ThinkingAura blocks from production `timeline`.
- Render active loading copy `正在思考并检索数据底座`.
- Collapse completed thinking runs by default.
- Expand current thinking run while streaming/loading.
- Show honest empty and error states with `StateNote`.
- Keep TopicCard selection and right-panel updates wired to existing production actions.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "creation timeline|studio conversation response"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 10: Complete Workbench Conversation Response UI

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/ChatPane.jsx`

- [x] **Step 1: Write the failing Workbench response UI test**

Assert `WorkbenchShell.tsx` contains:

```ts
[
  "WorkbenchChatPane",
  "ThinkingAura",
  "D.thinkingSteps",
  "D.thinkingLogs",
  "正在针对",
  "流式同步至右侧预览",
  "✅ 已完成",
  "润色工具箱",
  "图片或 PDF",
  "Ctrl+P",
  "生成",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench conversation response"
```

Expected: FAIL until Workbench conversation states match the DS ChatPane.

- [x] **Step 3: Implement production-safe Workbench response parity**

Patch `WorkbenchChatPane`:
- Use production `timeline`, `topics`, `selectedTopic`, and loading state.
- Show ThinkingAura for active analysis and tool logs.
- Show TopicCard options when real topics are available.
- Show DS writing copy only while real loading or draft generation is active.
- Show final completion copy only when the production note body exists.
- Keep composer actions wired to existing production `actions`.
- Do not import prototype `D` or `XHS_DATA`; if marker strings are needed for static tests, use equivalent local production constants rather than mock business data.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench conversation response"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 11: Complete Response Empty, Loading, Error, And Streaming States

**Files:**
- Modify: `web/tests/thread-ui-guardrails.test.ts`
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify as required: `web/src/components/studio/CreationScreen.tsx`
- Modify as required: `web/src/components/workbench/WorkbenchShell.tsx`
- Modify as required: `web/src/components/studio/Operations.tsx`

- [x] **Step 1: Write failing response-state guardrail tests**

Assert the production UI never visibly renders:

```ts
[
  "undefined",
  "null",
  "NaN",
  "[object Object]",
]
```

Add static or browser tests for:
- empty thread
- backend loading
- backend error
- no topics
- no selected topic
- no draft body
- long assistant response
- active streaming response
- expanded and collapsed thinking logs

- [x] **Step 2: Run the failing guardrail tests**

```powershell
npm run test:unit -- --test-name-pattern "guardrail|empty|loading|error|streaming"
```

Expected: FAIL if any state is missing or unsafe.

- [x] **Step 3: Implement response-state parity**

Patch the smallest components necessary:
- Use `StateNote` for honest empty/loading/error states.
- Clamp or wrap long response text so desktop layouts do not overflow.
- Keep response controls disabled while required data is missing.
- Ensure streaming indicators are tied to real loading state, not permanent mock flags.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "guardrail|empty|loading|error|streaming"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 12: Complete Workbench Sidebar And ChatPane Parity

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Modify if required: `web/src/components/studio/Shell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/Sidebar.jsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/ChatPane.jsx`

- [x] **Step 1: Write the failing sidebar/chat test**

Assert `WorkbenchShell.tsx` contains:

```ts
[
  "WorkbenchSidebar",
  "WorkbenchChatPane",
  "开启全新灵感对话",
  "最近创作",
  "TopicCard",
  "writing",
  "spin 0.7s linear infinite",
  "Ctrl+P",
  "生成",
  "onSelectTopic",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench sidebar and chat mirror"
```

Expected: FAIL until Workbench-specific sidebar/chat markers exist.

- [x] **Step 3: Implement production-safe sidebar/chat parity**

Implement or extract `WorkbenchSidebar` and `WorkbenchChatPane` inside `WorkbenchShell.tsx` unless the file becomes too large, in which case create:

```text
web/src/components/workbench/WorkbenchSidebar.tsx
web/src/components/workbench/WorkbenchChatPane.tsx
```

Rules:
- Use real `useStudio()` topics/timeline/actions.
- Do not import `XHS_DATA`.
- If there are no topics, show real empty state.
- Keep current `Recents` admin/config behavior if reusing `Recents`; if replacing it, preserve access to admin configuration.
- Use DS `TopicCard` for available topics.
- Show a writing/spinner state only when real `t.isLoading` or equivalent production timeline state is active.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench sidebar and chat mirror"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 13: Complete Workbench Image Carousel And Preview Actions

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/workbench/WorkbenchShell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/app.jsx`
- Source: `小红书文案助手 Design System/ui_kits/workbench/PhonePreview.jsx`

- [x] **Step 1: Write the failing image carousel test**

Assert `WorkbenchShell.tsx` contains:

```ts
[
  "imgIdx",
  "setImgIdx",
  "onPrev",
  "onNext",
  "上一张",
  "下一张",
  "chevron-left",
  "chevron-right",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "workbench image carousel"
```

Expected: FAIL until carousel state/actions are present.

- [x] **Step 3: Implement carousel using real images**

Add `imgIdx` state to `WorkbenchShell`, pass it into `RightCanvas` and `PhonePreview`, and wire `onPrev`/`onNext` to cycle through `useStudio().images`. If `images.length === 0`, hide arrow controls and keep the existing non-image preview empty state.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "workbench image carousel"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 14: Complete Studio Shell And Recents Parity Audit

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/studio/Shell.tsx`
- Source: `小红书文案助手 Design System/ui_kits/studio/Shell.jsx`

- [x] **Step 1: Write the failing shell/recents test**

Assert `Shell.tsx` contains:

```ts
[
  "StudioTopBar",
  "工作区切换",
  "开启全新灵感对话",
  "历史会话",
  "管理员配置",
  "panel-left-close",
  "panel-left-open",
  "borderLeft",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "studio shell and recents"
```

Expected: FAIL if top bar/sidebar parity is incomplete.

- [x] **Step 3: Implement only missing shell/sidebar parity**

Keep production history wired to LangGraph threads. Do not restore prototype `recents` mock data. Preserve:
- collapsible sidebar
- new chat CTA
- admin config panel
- active thread styling
- top nav labels

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "studio shell and recents"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 15: Complete Studio Composer Parity Audit

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/studio/Composer.tsx`
- Modify if required: `web/src/components/studio/DeepEditor.tsx`
- Source: `小红书文案助手 Design System/ui_kits/studio/Composer.jsx`

- [x] **Step 1: Write the failing composer test**

Assert `Composer.tsx` contains:

```ts
[
  "CopyDoctor",
  "ScheduleBar",
  "VisualStudio",
  "RiskPanel",
  "EmptyComposer",
  "quickEmoji",
  "润色",
  "瘦身",
  "配标签",
  "同步飞书",
  "定稿并排期",
  "文案体检",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "studio composer mirrors"
```

Expected: FAIL until composer subpanels and actions are present.

- [x] **Step 3: Implement composer parity with real actions**

Keep all actions wired to `useStudio().actions`. For any prototype-only toast action, either wire to an existing production action or show an honest disabled/empty state. Do not add fake AI image output.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "studio composer mirrors"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 16: Complete Studio Creation Screen Parity Audit

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/studio/CreationScreen.tsx`
- Source: `小红书文案助手 Design System/ui_kits/studio/CreationScreen.jsx`

- [x] **Step 1: Write or extend the failing creation-screen test**

Assert `CreationScreen.tsx` includes markers for:

```ts
[
  "RightLayout",
  "SelectedTopicBar",
  "DraftSnapshot",
  "TopicRail",
  "EvidencePanel",
  "TrendingTopics",
  "ThinkingAura",
  "PhoneFrame",
  "NoteCard",
]
```

- [x] **Step 2: Run the test**

```powershell
npm run test:unit -- --test-name-pattern "creation screen supports"
```

Expected: FAIL if any source-of-truth feature is missing.

- [x] **Step 3: Implement only missing desktop parity**

Use production state from `useStudio()`. If no real data exists, render real empty states, not mock topic cards.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "creation screen supports"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 17: Complete Studio DeepCreation And DeepEditor Parity Audit

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/studio/DeepCreation.tsx`
- Modify: `web/src/components/studio/DeepEditor.tsx`
- Source: `小红书文案助手 Design System/ui_kits/studio/DeepCreation.jsx`
- Source: `小红书文案助手 Design System/ui_kits/studio/DeepEditor.jsx`

- [x] **Step 1: Extend the deep creation test**

Assert:

```ts
[
  "DeepImmersive",
  "DeepFlow",
  "DeepWorkspace",
  "BigEditor",
  "AssistantPanel",
  "EvidenceRail",
  "NotePreview",
  "StepCards",
  "Version",
  "话题标签",
  "文案体检",
]
```

- [x] **Step 2: Run the test**

```powershell
npm run test:unit -- --test-name-pattern "deep creation supports"
```

Expected: FAIL if any desktop deep creation piece is missing.

- [x] **Step 3: Implement missing pieces**

Keep real note state and real actions:
- `actions.updateField`
- `actions.setVersion`
- `actions.addTag`
- `actions.removeTag`
- `actions.polish`
- `actions.shorten`
- `actions.addTags`

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "deep creation supports"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 18: Complete Studio Operations Parity Audit

**Files:**
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify: `web/src/components/studio/Operations.tsx`
- Source: `小红书文案助手 Design System/ui_kits/studio/Operations.jsx`

- [x] **Step 1: Extend operations test**

Assert:

```ts
[
  "OpsPage",
  "OpsInline",
  "OpsHybrid",
  "AccountRail",
  "DashboardBody",
  "CalendarSection",
  "LibrarySection",
  "BackfillSection",
  "PipelineSection",
  "StateNote",
]
```

- [x] **Step 2: Run the test**

```powershell
npm run test:unit -- --test-name-pattern "operations screen supports"
```

Expected: FAIL if any operations feature is missing.

- [x] **Step 3: Implement missing desktop parity**

Use `loadState` for loading/empty/error states. Do not create fake dashboard values.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "operations screen supports"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 19: DS Primitive Source Parity Audit

**Files:**
- Modify: `web/tests/ds-production-adherence.test.ts`
- Modify as needed: `web/src/components/ds/**`
- Source: `小红书文案助手 Design System/components/**/*.jsx`
- Source: `小红书文案助手 Design System/components/**/*.d.ts`

- [x] **Step 1: Write failing primitive API tests**

For each manifest component, assert production source includes the important public props from DS `.d.ts` files:

```ts
[
  "Button",
  "IconButton",
  "Badge",
  "Avatar",
  "Card",
  "StatCard",
  "NoteCard",
  "PhoneFrame",
  "Input",
  "Select",
  "Textarea",
  "TopicCard",
  "ThinkingAura",
  "HashtagTag",
]
```

The test should compare names and required prop markers, not exact source text.

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "DS primitive source parity"
```

Expected: FAIL for missing props or variants.

- [x] **Step 3: Implement missing primitive props/states**

Patch only the specific primitive gaps. Preserve existing production imports and no-CDN icon strategy.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "DS primitive source parity|each manifest DS component"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 20: Brand Guidelines, Dark Theme, And Motion Audit

**Files:**
- Modify: `web/tests/ds-production-adherence.test.ts`
- Modify: `web/tests/ds-ui-kit-alignment.test.ts`
- Modify as needed: `web/src/app/globals.css`
- Source: `小红书文案助手 Design System/guidelines/*.card.html`
- Source: `小红书文案助手 Design System/styles.css`
- Source: `小红书文案助手 Design System/tokens/*.css`

- [x] **Step 1: Write failing guideline coverage tests**

Assert production globals and UI wiring cover:

```ts
[
  "--coral-brand",
  "--shadow-coral",
  "--radius-phone",
  "--rail-sidebar",
  "--rail-canvas",
  "--topbar-height",
  ".dark",
  "secIn",
  "toastIn",
  "slide-in-right",
  "pop-in",
  "lift",
  "custom-scrollbar",
]
```

- [x] **Step 2: Run the failing test**

```powershell
npm run test:unit -- --test-name-pattern "brand guidelines and motion"
```

Expected: FAIL for missing guideline or motion markers.

- [x] **Step 3: Implement missing global styles**

Patch `globals.css` only for missing tokens/utilities/keyframes. Do not redesign the palette.

- [x] **Step 4: Verify**

```powershell
npm run test:unit -- --test-name-pattern "brand guidelines and motion"
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

---

## Task 21: Desktop Browser UAT Harness

**Files:**
- Create: `web/tests/e2e/ds-desktop-parity.spec.ts`
- Source: `小红书文案助手 Design System/_ds_manifest.json`

- [x] **Step 1: Create Playwright test with mocked auth/backend**

The test must cover:
- `/`
- `/?mode=workbench`
- Desktop viewport `1440x960`
- Open Studio Tweaks and click all three variant groups.
- Exercise Studio creation, deep, and operations sections.
- Open Workbench command palette with `Ctrl+P`.
- Search a Workbench command and verify filtered results.
- Switch Workbench right canvas tabs.
- Toggle detail/feed preview.
- Click Feishu reauth.
- Run Feishu sync and observe progress states.
- Click copy button.
- Render a mocked thread with user, assistant, tool-call, tool-result, and streaming messages.
- Verify ThinkingAura appears in Studio and Workbench conversation panes.
- Expand and collapse ThinkingAura logs.
- Verify active streaming copy and final completion copy do not appear at the same time.
- Verify a long assistant response wraps without horizontal overflow.
- Verify empty, loading, and error response states render honest `StateNote` content.
- Run once with dense mocked data and once with empty collections.

- [x] **Step 2: Add assertions**

For each route assert:

```ts
expect(page.locator("main")).toHaveCount(1);
expect(page.locator("h1")).toHaveCount(1);
expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 2)).toBeTruthy();
expect(pageErrors).toEqual([]);
expect(failedRequests).toEqual([]);
expect(consoleErrors).toEqual([]);
```

- [x] **Step 3: Run the browser UAT**

Run:

```powershell
npm run build
npm run start -- -p 3100
npx playwright test web/tests/e2e/ds-desktop-parity.spec.ts --project=chromium
```

Expected: PASS. Stop the `next start -p 3100` process after the run.

---

## Task 22: Visual Screenshot Regression Spot Check

**Files:**
- Create: `web/tests/e2e/ds-desktop-visual.spec.ts`
- Output: Playwright screenshots under the test output folder.

- [x] **Step 1: Create visual spot-check test**

Capture desktop screenshots for:
- Studio create stack layout.
- Studio create split layout.
- Studio deep workspace.
- Studio ops hybrid.
- Workbench mock detail.
- Workbench mock feed.
- Workbench Feishu sync.
- Workbench command palette open.

- [x] **Step 2: Add non-blank and overlap assertions**

Assert each screenshot has non-zero bytes and each page has:

```ts
document.documentElement.scrollWidth <= innerWidth + 2
document.querySelectorAll("main").length === 1
document.querySelectorAll("h1").length === 1
```

- [x] **Step 3: Run visual spot-check**

```powershell
npm run build
npm run start -- -p 3100
npx playwright test web/tests/e2e/ds-desktop-visual.spec.ts --project=chromium
```

Expected: PASS. Stop the `next start -p 3100` process after the run.

---

## Task 23: Final Full Verification

**Files:**
- No production file changes unless a verification failure demands a TDD fix.

- [x] **Step 1: Run frontend unit tests**

```powershell
cd E:\小红书智能体\web
npm run test:unit
```

Expected: all tests pass.

- [x] **Step 2: Run TypeScript**

Run separately from `next build` to avoid `.next/types` write races:

```powershell
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: exit code 0.

- [x] **Step 3: Run production build**

```powershell
npm run build
```

Expected: exit code 0. Known existing warnings are acceptable:
- `StudioContext.tsx` Fast Refresh warning.
- Next ESLint plugin warning.
- LangGraph auth passthrough warning.

- [x] **Step 4: Run backend tests if backend-related files were touched**

```powershell
cd E:\小红书智能体
uv run pytest
```

Expected: all non-skipped tests pass.

Result: not run; no backend-related files were touched during the desktop Design System parity work.

---

## Execution Rules

- Do not continue implementation until this plan is accepted.
- Implement tasks in order.
- Each task starts with a failing test.
- Do not run `tsc --noEmit` in parallel with `npm run build`; they race on `.next/types`.
- Do not restore `.kiro`; the user explicitly requested it deleted.
- Do not touch `ONBOARDING.md` or `scripts/_snip.py` unless the user explicitly asks.
- Do not add mock business data to production UI.
- Keep mobile issues documented but unimplemented for this Web desktop phase.

---

## Self-Review

- Spec coverage: the plan covers tokens, brand guidelines, DS primitives, ThinkingAura source parity, real thinking-trace/tool-call mapping, Studio conversation response UI, Workbench conversation response UI, response empty/loading/error/streaming states, Studio root, Studio shell/recents, Studio Tweaks, Composer, Creation, DeepCreation, Operations, Workbench root, Sidebar, ChatPane, TopBar, RightCanvas, PhonePreview, image carousel, FeishuSync, CommandPalette, desktop accessibility, dense/empty/streaming desktop UAT, and screenshot spot checks.
- Placeholder scan: no `TBD`, `TODO`, or unspecified “handle later” items remain.
- Type consistency: planned component/function names match current production names or explicit new names: `TweaksPanel`, `TweakRadio`, `ThinkingAura`, `deriveTimeline`, `RightCanvasBottomBar`, `CopyButton`, `FeishuSync`, `CommandPalette`.
- Known gap intentionally excluded: mobile responsive parity.
