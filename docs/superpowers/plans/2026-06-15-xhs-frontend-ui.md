# 小红书文案助手 · 前端 UI 改造 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `web/`（官方 agent-chat-ui）从开发者灰阶风改造成「暖白极简」的小红书文案助手产品界面，含品牌化、选题/文案卡片、欢迎页、侧栏、工具调用友好化。

**Architecture:** 不换框架，沿用 shadcn/ui + Tailwind v4。换肤靠改 `globals.css` 的 CSS 变量；交互组件在现有 `Thread` 消息流上叠加。选题/文案靠 agent 输出约定 fence（`xhs_topics`/`xhs_copy`），前端在 `ai.tsx` 预抽取后渲染卡片，前端从不猜数据语义。

**Tech Stack:** Next.js 15 (App Router) + React 19 + TypeScript + Tailwind v4 + shadcn/ui + framer-motion + lucide-react + `@langchain/langgraph-sdk`。包管理 pnpm。

**设计依据:** `docs/superpowers/specs/2026-06-15-xhs-frontend-ui-design.md`

---

## 文件结构

**新增：**
- `web/src/lib/brand.ts` — 品牌常量（产品名、slogan、示例问题）。纯数据，无依赖。
- `web/src/lib/thread-actions.tsx` — `ThreadActionsContext` + `useThreadActions`，提供 `submitText(text)`，避免逐层透传。
- `web/src/lib/tool-display.ts` — 工具名→友好文案映射 + 识别工具类型的纯函数。
- `web/src/lib/xhs-blocks.ts` — 从 `contentString` 抽取 `xhs_topics`/`xhs_copy` 段的纯解析函数（与渲染分离，可独立推理）。
- `web/src/components/thread/messages/topic-cards.tsx` — 选题卡片组件。
- `web/src/components/thread/messages/copy-card.tsx` — 文案卡片组件。

**修改：**
- `web/src/app/globals.css` — `:root` 暖白色板 + `--radius`。
- `web/src/app/layout.tsx` — 字体栈、metadata。
- `web/src/components/thread/index.tsx` — 顶栏品牌、欢迎页、移除 GitHub 图标、文案中文化、provide actions context。
- `web/src/components/thread/history/index.tsx` — 侧栏品牌区、新对话按钮、最近分组、选中态、底部用户区、中文化。
- `web/src/components/thread/messages/ai.tsx` — 用 `xhs-blocks` 预抽取并分派卡片，其余走 `MarkdownText`。
- `web/src/components/thread/messages/human.tsx` — 用户气泡用主色。
- `web/src/components/thread/messages/tool-calls.tsx` — 重做为友好状态条 + 朴素展开。
- `web/src/providers/Stream.tsx` — 配置表单的 logo/标题/文案品牌化（顺带）。
- `prompts.py` / `skills/topic-content/SKILL.md` — 约定 agent 用 `xhs_topics`/`xhs_copy` fence 输出。

**验证说明（全程适用）：** 前端无测试框架，本计划不引入。每个前端任务的「验证」= `pnpm -C web exec tsc --noEmit`（类型检查）通过；阶段末做一次 `pnpm -C web build`。涉及纯函数的任务（`xhs-blocks.ts`、`tool-display.ts`）用一次性 Node 脚本断言验证后删除脚本。手动冒烟集中在最后的集成任务。Windows 下起 `langgraph dev` 前先杀残留 python 进程。

---

## Task 1: 暖白色板与圆角（换肤地基）

**Files:**
- Modify: `web/src/app/globals.css`（`:root` 块，约 6-37 行）

- [ ] **Step 1: 替换 `:root` 的亮色 oklch 变量为暖白色板**

把 `web/src/app/globals.css` 中 `:root {` 内的以下变量改为下列值（其余变量如 chart-*、sidebar-* 暂留，sidebar 在 Task 8 视觉上由组件类覆盖）。注意：现有文件 `:root` 用 oklch，保持 oklch 写法。

```css
:root {
  --background: oklch(0.985 0.006 70);      /* #FAF9F7 微暖白 */
  --foreground: oklch(0.32 0.012 60);       /* #3A352F 暖深灰 */
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.32 0.012 60);
  --popover: oklch(1 0 0);
  --popover-foreground: oklch(0.32 0.012 60);
  --primary: oklch(0.68 0.13 40);           /* #E07856 赤陶橙 */
  --primary-foreground: oklch(1 0 0);
  --secondary: oklch(0.95 0.008 70);        /* #F3F1EC 暖米 */
  --secondary-foreground: oklch(0.32 0.012 60);
  --muted: oklch(0.95 0.008 70);            /* #F3F1EC */
  --muted-foreground: oklch(0.64 0.015 65); /* #9A9389 暖灰 */
  --accent: oklch(0.94 0.025 50);           /* #FBEDE6 浅橙 */
  --accent-foreground: oklch(0.45 0.10 40);
  --destructive: oklch(0.577 0.245 27.325);
  --destructive-foreground: oklch(0.577 0.245 27.325);
  --border: oklch(0.9 0.02 60);             /* #EADFD4 暖边框 */
  --input: oklch(0.9 0.02 60);
  --ring: oklch(0.68 0.13 40);
  --chart-1: oklch(0.646 0.222 41.116);
  --chart-2: oklch(0.6 0.118 184.704);
  --chart-3: oklch(0.398 0.07 227.392);
  --chart-4: oklch(0.828 0.189 84.429);
  --chart-5: oklch(0.769 0.188 70.08);
  --radius: 0.875rem;
  --sidebar: oklch(0.95 0.008 70);
  --sidebar-foreground: oklch(0.32 0.012 60);
  --sidebar-primary: oklch(0.68 0.13 40);
  --sidebar-primary-foreground: oklch(1 0 0);
  --sidebar-accent: oklch(0.94 0.025 50);
  --sidebar-accent-foreground: oklch(0.45 0.10 40);
  --sidebar-border: oklch(0.9 0.02 60);
  --sidebar-ring: oklch(0.68 0.13 40);
}
```

> 注意 `tailwind.config.js` 里 colors 用 `hsl(var(--x))` 包裹，但 `@theme inline`（globals.css 内）用 `var(--x)` 直引用。Tailwind v4 以 `@theme inline` 为准，组件里的 `bg-primary` 等走的是 oklch 变量，直接生效。不要去改 `tailwind.config.js` 的 hsl 包裹（v4 下那份 config 的 colors 基本不被使用），避免引入不一致。如发现颜色不生效，以 `@theme inline` 映射为准排查。

- [ ] **Step 2: 类型/编译不受影响，启动确认**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过（CSS 改动不影响 TS）。

- [ ] **Step 3: 提交**

```bash
git add web/src/app/globals.css
git commit -m "feat(web): 暖白极简色板与圆角"
```

---

## Task 2: 字体栈与页面元数据

**Files:**
- Modify: `web/src/app/layout.tsx`

- [ ] **Step 1: 替换字体与 metadata**

把 `web/src/app/layout.tsx` 整体替换为（移除 `Inter`，用系统中文字体栈类）：

```tsx
import type { Metadata } from "next";
import "./globals.css";
import React from "react";
import { NuqsAdapter } from "nuqs/adapters/next/app";

export const metadata: Metadata = {
  title: "小红书文案助手",
  description: "你的小红书爆款搭子🍠",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body className="font-sans antialiased">
        <NuqsAdapter>{children}</NuqsAdapter>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: 在 globals.css 定义中文优先的 sans 字体栈**

在 `web/src/app/globals.css` 的 `@theme inline { ... }` 块内追加一行（让 `font-sans` 走中文栈）：

```css
  --font-sans: -apple-system, "PingFang SC", "Microsoft YaHei", "Noto Sans SC", system-ui, sans-serif;
```

- [ ] **Step 3: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 4: 提交**

```bash
git add web/src/app/layout.tsx web/src/app/globals.css
git commit -m "feat(web): 中文字体栈与产品元数据"
```

---

## Task 3: 品牌常量

**Files:**
- Create: `web/src/lib/brand.ts`

- [ ] **Step 1: 创建品牌常量**

```ts
// web/src/lib/brand.ts
export const BRAND = {
  name: "小红书文案助手",
  slogan: "你的小红书爆款搭子🍠",
  mark: "🍠",
  examples: [
    "帮我出「夏日防晒」的选题",
    "写一篇露营装备种草",
    "咖啡探店文案，给我 3 个标题",
    "穿搭｜平价单品穿出高级感",
  ],
} as const;
```

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 3: 提交**

```bash
git add web/src/lib/brand.ts
git commit -m "feat(web): 品牌常量 BRAND"
```

---

## Task 4: ThreadActions Context（submitText 能力下沉）

**Files:**
- Create: `web/src/lib/thread-actions.tsx`

- [ ] **Step 1: 创建 Context 与 hook**

选题卡片、欢迎页 chip 都需要"以编程方式发一条用户消息"。用 Context 提供 `submitText`，由 `Thread` 在 Task 9 注入实现，消费者无需透传。

```tsx
// web/src/lib/thread-actions.tsx
import { createContext, useContext, ReactNode } from "react";

export interface ThreadActions {
  /** 以编程方式提交一条人类文本消息（复用 Thread 的提交逻辑） */
  submitText: (text: string) => void;
}

const ThreadActionsContext = createContext<ThreadActions | null>(null);

export function ThreadActionsProvider({
  value,
  children,
}: {
  value: ThreadActions;
  children: ReactNode;
}) {
  return (
    <ThreadActionsContext.Provider value={value}>
      {children}
    </ThreadActionsContext.Provider>
  );
}

/** 消费 submitText。不在 Provider 内时返回 no-op，保证组件在任何上下文都不崩。 */
export function useThreadActions(): ThreadActions {
  const ctx = useContext(ThreadActionsContext);
  return ctx ?? { submitText: () => {} };
}
```

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 3: 提交**

```bash
git add web/src/lib/thread-actions.tsx
git commit -m "feat(web): ThreadActions context 提供 submitText"
```

<!-- APPEND-MARKER-1 -->

## Task 5: xhs-blocks 解析函数（纯函数，可独立验证）

**Files:**
- Create: `web/src/lib/xhs-blocks.ts`

把 AI 文本切成有序片段：普通文本 / 选题块 / 文案块。纯函数，不依赖 React，便于断言验证。

- [ ] **Step 1: 写实现**

```ts
// web/src/lib/xhs-blocks.ts
export interface TextSegment { kind: "text"; text: string }
export interface TopicsSegment {
  kind: "topics";
  data: { intro?: string; topics: string[] };
}
export interface CopySegment {
  kind: "copy";
  data: { title: string; body: string; tags: string[] };
}
export type Segment = TextSegment | TopicsSegment | CopySegment;

// 匹配 ```xhs_topics ... ``` 或 ```xhs_copy ... ```（含语言行后的换行）
const FENCE_RE = /```(xhs_topics|xhs_copy)\s*\n([\s\S]*?)```/g;

/**
 * 把内容字符串切成有序片段。
 * - 命中 fence 且 JSON.parse 成功且结构合法 → topics/copy 段
 * - 解析失败 → 该 fence 原样并入文本段（降级）
 * - 无 fence → 整体一个 text 段
 */
export function parseXhsBlocks(content: string): Segment[] {
  const segments: Segment[] = [];
  let lastIndex = 0;
  let m: RegExpExecArray | null;
  FENCE_RE.lastIndex = 0;

  const pushText = (text: string) => {
    if (text.length > 0) segments.push({ kind: "text", text });
  };

  while ((m = FENCE_RE.exec(content)) !== null) {
    const [full, lang, inner] = m;
    const parsed = tryParse(lang, inner);
    if (parsed) {
      pushText(content.slice(lastIndex, m.index));
      segments.push(parsed);
      lastIndex = m.index + full.length;
    }
    // parsed 为 null 时不前移 lastIndex，fence 留在文本里降级
  }
  pushText(content.slice(lastIndex));
  // 全是空 → 至少回一个 text 段，保证调用方有内容渲染
  if (segments.length === 0) segments.push({ kind: "text", text: content });
  return segments;
}

function tryParse(lang: string, inner: string): TopicsSegment | CopySegment | null {
  let obj: any;
  try {
    obj = JSON.parse(inner.trim());
  } catch {
    return null;
  }
  if (lang === "xhs_topics") {
    if (obj && Array.isArray(obj.topics) && obj.topics.every((t: unknown) => typeof t === "string")) {
      return { kind: "topics", data: { intro: typeof obj.intro === "string" ? obj.intro : undefined, topics: obj.topics } };
    }
    return null;
  }
  // xhs_copy
  if (obj && typeof obj.title === "string" && typeof obj.body === "string") {
    const tags = Array.isArray(obj.tags) ? obj.tags.filter((t: unknown) => typeof t === "string") : [];
    return { kind: "copy", data: { title: obj.title, body: obj.body, tags } };
  }
  return null;
}
```

- [ ] **Step 2: 写临时验证脚本并运行**

创建 `web/scripts/verify-xhs-blocks.mjs`（验证后删除）：

```js
import { parseXhsBlocks } from "../src/lib/xhs-blocks.ts";
import assert from "node:assert";

// 1. 纯文本
let s = parseXhsBlocks("你好");
assert.equal(s.length, 1); assert.equal(s[0].kind, "text");

// 2. 选题块
s = parseXhsBlocks('开场\n```xhs_topics\n{"intro":"给你3个","topics":["A","B"]}\n```\n收尾');
assert.equal(s.length, 3);
assert.equal(s[0].kind, "text"); assert.equal(s[1].kind, "topics");
assert.deepEqual(s[1].data.topics, ["A", "B"]); assert.equal(s[2].kind, "text");

// 3. 文案块
s = parseXhsBlocks('```xhs_copy\n{"title":"T","body":"B","tags":["#x"]}\n```');
assert.equal(s[0].kind, "copy"); assert.equal(s[0].data.title, "T");

// 4. 坏 JSON 降级为文本
s = parseXhsBlocks('```xhs_topics\n{bad json}\n```');
assert.equal(s[0].kind, "text");

console.log("ALL PASS");
```

Run: `pnpm -C web exec tsx scripts/verify-xhs-blocks.mjs`（若无 tsx：`pnpm -C web exec vite-node scripts/verify-xhs-blocks.mjs`；两者都不可用时跳过本步，依赖 Step 3 类型检查 + Task 9 冒烟）
Expected: 打印 `ALL PASS`

- [ ] **Step 3: 删除验证脚本 + 类型检查**

```bash
rm web/scripts/verify-xhs-blocks.mjs
```
Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 4: 提交**

```bash
git add web/src/lib/xhs-blocks.ts
git commit -m "feat(web): xhs_topics/xhs_copy 片段解析（含降级）"
```

---

## Task 6: 选题卡片组件 TopicCards

**Files:**
- Create: `web/src/components/thread/messages/topic-cards.tsx`

- [ ] **Step 1: 写组件**

```tsx
// web/src/components/thread/messages/topic-cards.tsx
import { ChevronRight } from "lucide-react";
import { useThreadActions } from "@/lib/thread-actions";
import { MarkdownText } from "../markdown-text";
import type { TopicsSegment } from "@/lib/xhs-blocks";

export function TopicCards({ data }: { data: TopicsSegment["data"] }) {
  const { submitText } = useThreadActions();
  return (
    <div className="flex flex-col gap-2">
      {data.intro && (
        <div className="text-foreground">
          <MarkdownText>{data.intro}</MarkdownText>
        </div>
      )}
      <div className="flex flex-col gap-2">
        {data.topics.map((topic, i) => (
          <button
            key={i}
            type="button"
            onClick={() => submitText(`写第 ${i + 1} 个`)}
            className="border-border hover:border-primary hover:bg-accent group flex items-center gap-3 rounded-xl border bg-card px-3.5 py-3 text-left transition-colors"
          >
            <span className="bg-accent text-primary flex size-6 flex-shrink-0 items-center justify-center rounded-md text-xs font-semibold">
              {i + 1}
            </span>
            <span className="text-foreground flex-1 text-sm">{topic}</span>
            <ChevronRight className="text-muted-foreground size-4 flex-shrink-0" />
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/thread/messages/topic-cards.tsx
git commit -m "feat(web): 选题卡片 TopicCards（点选自动发送）"
```

<!-- APPEND-MARKER-2 -->

## Task 7: 文案卡片组件 CopyCard

**Files:**
- Create: `web/src/components/thread/messages/copy-card.tsx`

- [ ] **Step 1: 写组件**

```tsx
// web/src/components/thread/messages/copy-card.tsx
import { useState } from "react";
import { Copy, CopyCheck } from "lucide-react";
import type { CopySegment } from "@/lib/xhs-blocks";

export function CopyCard({ data }: { data: CopySegment["data"] }) {
  const [copied, setCopied] = useState(false);

  const fullText = [
    data.title,
    "",
    data.body,
    "",
    data.tags.join(" "),
  ].join("\n").trim();

  const handleCopy = () => {
    navigator.clipboard.writeText(fullText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="border-border bg-card overflow-hidden rounded-2xl border">
      <div className="border-border flex items-center justify-between border-b bg-secondary/60 px-4 py-2.5">
        <span className="bg-accent text-primary rounded-md px-2 py-0.5 text-xs font-semibold">
          完成文案
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="text-primary hover:bg-accent flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs transition-colors"
        >
          {copied ? <CopyCheck className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "已复制" : "一键复制"}
        </button>
      </div>
      <div className="px-4 py-3.5">
        <div className="text-foreground mb-2 text-sm font-semibold">{data.title}</div>
        <div className="text-foreground/80 mb-3 text-sm leading-relaxed whitespace-pre-wrap">
          {data.body}
        </div>
        {data.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.tags.map((tag, i) => (
              <span key={i} className="text-xs text-sky-700/80">
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/thread/messages/copy-card.tsx
git commit -m "feat(web): 文案卡片 CopyCard（一键复制）"
```

---

## Task 8: 在 ai.tsx 接入预抽取与卡片分派

**Files:**
- Modify: `web/src/components/thread/messages/ai.tsx`（约 102-167 行，AssistantMessage 内 contentString 的渲染处）

现状（约 163-167 行）：
```tsx
{contentString.length > 0 && (
  <div className="py-1">
    <MarkdownText>{contentString}</MarkdownText>
  </div>
)}
```

- [ ] **Step 1: 在文件顶部加导入**

在 `web/src/components/thread/messages/ai.tsx` 现有 import 区追加：

```tsx
import { parseXhsBlocks } from "@/lib/xhs-blocks";
import { TopicCards } from "./topic-cards";
import { CopyCard } from "./copy-card";
```

- [ ] **Step 2: 用分段渲染替换上面那段**

把 Step 0 现状那段替换为：

```tsx
{contentString.length > 0 && (
  <div className="flex flex-col gap-3 py-1">
    {parseXhsBlocks(contentString).map((seg, i) => {
      if (seg.kind === "topics") return <TopicCards key={i} data={seg.data} />;
      if (seg.kind === "copy") return <CopyCard key={i} data={seg.data} />;
      return <MarkdownText key={i}>{seg.text}</MarkdownText>;
    })}
  </div>
)}
```

- [ ] **Step 3: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 4: 提交**

```bash
git add web/src/components/thread/messages/ai.tsx
git commit -m "feat(web): AI 消息预抽取并分派选题/文案卡片"
```

<!-- APPEND-MARKER-3 -->

## Task 9: 工具显示映射（tool-display.ts，纯函数）

**Files:**
- Create: `web/src/lib/tool-display.ts`

把工具名/调用信息映射为友好中文。子智能体经由 `task` 工具委派——`tc.name` 是 `task`，真正的子 agent 名在 args 里（deepagents 的 task 工具参数含 `subagent_type` 或 `description`）。写文件类工具靠 args 路径判断。

- [ ] **Step 1: 写实现**

```ts
// web/src/lib/tool-display.ts

export interface ToolDisplay {
  /** true 表示这是内部噪音（skills 内部读写），完全不渲染 */
  hidden: boolean;
  running: string;  // 进行中文案
  done: string;     // 完成文案
}

/** 取 args 里可能的文件路径字段 */
function argPath(args: Record<string, any> | undefined): string {
  if (!args) return "";
  return String(args.file_path ?? args.path ?? args.filename ?? "");
}

/**
 * 由工具名 + args 推导显示信息。
 * resultCount: 若已知工具结果的行数（read_xhs_data 的 rows.length），用于完成态计数。
 */
export function getToolDisplay(
  name: string | undefined,
  args?: Record<string, any>,
  resultCount?: number,
): ToolDisplay {
  const path = argPath(args);

  // skills 内部操作：读写命中 /skills/ 的文件，纯噪音
  if (path.includes("/skills/")) {
    return { hidden: true, running: "", done: "" };
  }

  switch (name) {
    case "read_xhs_data":
      return {
        hidden: false,
        running: "正在读取你的爆款库…",
        done: resultCount != null ? `已读取爆款库（${resultCount} 条）` : "已读取爆款库",
      };
    case "task":
      // 子 agent 委派（baokuan-analyst 等）
      return { hidden: false, running: "正在分析爆款规律…", done: "已总结这批爆款的共性" };
    case "write_file":
    case "edit_file":
      if (path.includes("/shared/")) {
        return { hidden: false, running: "正在更新你的风格库…", done: "已更新你的风格库" };
      }
      if (path.includes("/drafts/")) {
        return { hidden: false, running: "正在保存草稿…", done: "已保存草稿" };
      }
      if (path.includes("/analysis/")) {
        return { hidden: true, running: "", done: "" }; // 中间分析文件，内部噪音
      }
      return { hidden: false, running: "正在写入…", done: "已写入" };
    case "read_file":
      // 读 /analysis/ /shared/ 等内部文件，不展示
      return { hidden: true, running: "", done: "" };
    default:
      return { hidden: false, running: "正在处理…", done: "已完成" };
  }
}

/** 从 read_xhs_data 的结果 content 里取 rows 行数；取不到返回 undefined */
export function extractRowCount(content: unknown): number | undefined {
  try {
    const obj = typeof content === "string" ? JSON.parse(content) : content;
    if (obj && Array.isArray((obj as any).rows)) return (obj as any).rows.length;
  } catch {
    /* ignore */
  }
  return undefined;
}
```

> 说明：`read_file` 在本工作流里只用于读 `/analysis/`、`/shared/` 等内部文件，统一隐藏。若将来有面向用户的 read_file 用途，再细化。`/analysis/` 写入是子 agent 的中间产物，隐藏。

- [ ] **Step 2: 临时验证脚本**

创建 `web/scripts/verify-tool-display.mjs`：

```js
import { getToolDisplay, extractRowCount } from "../src/lib/tool-display.ts";
import assert from "node:assert";

assert.equal(getToolDisplay("read_xhs_data", {}, 32).done, "已读取爆款库（32 条）");
assert.equal(getToolDisplay("read_xhs_data", {}).done, "已读取爆款库");
assert.equal(getToolDisplay("task", { subagent_type: "baokuan-analyst" }).running, "正在分析爆款规律…");
assert.equal(getToolDisplay("write_file", { file_path: "/shared/xhs-style.md" }).done, "已更新你的风格库");
assert.equal(getToolDisplay("write_file", { file_path: "/drafts/x-1.md" }).done, "已保存草稿");
assert.equal(getToolDisplay("read_file", { file_path: "/skills/topic-content/SKILL.md" }).hidden, true);
assert.equal(getToolDisplay("write_file", { file_path: "/analysis/露营.md" }).hidden, true);
assert.equal(extractRowCount('{"columns":[],"rows":[1,2,3]}'), 3);
console.log("ALL PASS");
```

Run: `pnpm -C web exec tsx scripts/verify-tool-display.mjs`（无 tsx 则同 Task 5 的回退，或跳过依赖 Step 3）
Expected: `ALL PASS`

- [ ] **Step 3: 删脚本 + 类型检查**

```bash
rm web/scripts/verify-tool-display.mjs
```
Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 4: 提交**

```bash
git add web/src/lib/tool-display.ts
git commit -m "feat(web): 工具名→友好文案映射"
```

<!-- APPEND-MARKER-4 -->

## Task 10: 重做工具调用 UI（tool-calls.tsx）

**Files:**
- Modify: `web/src/components/thread/messages/tool-calls.tsx`（整体替换）

设计：`ToolCalls`（AI 消息的发起）只在「无匹配 ToolResult」时显示「⟳ 进行中」状态条；`ToolResult`（独立 tool 消息）显示「✓ 完成」状态条 + 可展开朴素内容 + 查看原始。配对靠 `tc.id ↔ message.tool_call_id`。隐藏项（skills/analysis 内部操作）不渲染。

- [ ] **Step 1: 整体替换 tool-calls.tsx**

```tsx
// web/src/components/thread/messages/tool-calls.tsx
import { AIMessage, ToolMessage } from "@langchain/langgraph-sdk";
import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, LoaderCircle, Check } from "lucide-react";
import { useStreamContext } from "@/providers/Stream";
import { getToolDisplay, extractRowCount } from "@/lib/tool-display";

// 进行中状态条：仅当该 tool_call 还没有对应的 ToolResult 时显示
export function ToolCalls({
  toolCalls,
}: {
  toolCalls: AIMessage["tool_calls"];
}) {
  const thread = useStreamContext();
  if (!toolCalls || toolCalls.length === 0) return null;

  // 已存在结果的 tool_call_id 集合
  const resolvedIds = new Set(
    thread.messages
      .filter((m): m is ToolMessage => m.type === "tool")
      .map((m) => (m as ToolMessage).tool_call_id)
      .filter(Boolean),
  );

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-2">
      {toolCalls.map((tc, idx) => {
        const display = getToolDisplay(tc.name, tc.args as Record<string, any>);
        if (display.hidden) return null;
        if (tc.id && resolvedIds.has(tc.id)) return null; // 已完成 → 交给 ToolResult 渲染
        return (
          <div
            key={tc.id || idx}
            className="border-border bg-card text-muted-foreground inline-flex w-fit items-center gap-2 rounded-xl border px-3.5 py-2 text-sm"
          >
            <LoaderCircle className="text-primary size-3.5 animate-spin" />
            {display.running}
          </div>
        );
      })}
    </div>
  );
}

// 完成状态条 + 可展开朴素内容
export function ToolResult({ message }: { message: ToolMessage }) {
  const [expanded, setExpanded] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  // 解析结果内容
  let parsed: any = message.content;
  let isJson = false;
  try {
    if (typeof message.content === "string") {
      parsed = JSON.parse(message.content);
      isJson = typeof parsed === "object" && parsed !== null;
    }
  } catch {
    parsed = message.content;
  }

  const rowCount =
    message.name === "read_xhs_data" ? extractRowCount(message.content) : undefined;
  const display = getToolDisplay(message.name, undefined, rowCount);
  if (display.hidden) return null;

  const rawStr =
    typeof message.content === "string"
      ? message.content
      : JSON.stringify(message.content, null, 2);

  const hasRows = isJson && Array.isArray(parsed?.rows) && Array.isArray(parsed?.columns);

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="border-border inline-flex w-fit items-center gap-2 rounded-xl border bg-[oklch(0.97_0.02_145)] px-3.5 py-2 text-sm text-[oklch(0.45_0.08_145)] transition-colors hover:opacity-90"
      >
        <Check className="size-3.5" />
        {display.done}
        <ChevronDown
          className={`size-3.5 transition-transform ${expanded ? "rotate-180" : ""}`}
        />
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-border mt-2 rounded-xl border bg-card p-3">
              {hasRows ? (
                <RowCards columns={parsed.columns} rows={parsed.rows} />
              ) : (
                <div className="text-foreground/80 text-sm leading-relaxed whitespace-pre-wrap">
                  {typeof parsed === "string" ? parsed : rawStr}
                </div>
              )}
              <button
                type="button"
                onClick={() => setShowRaw((v) => !v)}
                className="text-muted-foreground border-border mt-3 w-full border-t pt-2 text-left text-xs hover:text-foreground"
              >
                ⧉ {showRaw ? "收起原始数据" : "查看原始（开发用）"}
              </button>
              {showRaw && (
                <pre className="text-muted-foreground mt-2 max-h-64 overflow-auto rounded-lg bg-secondary p-2 text-xs whitespace-pre-wrap">
                  {rawStr}
                </pre>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// 通用行卡：按列名平铺「列名：值」，不猜字段语义
function RowCards({ columns, rows }: { columns: string[]; rows: Record<string, any>[] }) {
  const MAX = 8;
  const shown = rows.slice(0, MAX);
  return (
    <div className="flex flex-col gap-2">
      {shown.map((row, i) => (
        <div key={i} className="border-border/60 rounded-lg border bg-secondary/40 px-3 py-2">
          {columns.map((col) => {
            const v = row[col];
            if (v == null || v === "") return null;
            const text = typeof v === "object" ? JSON.stringify(v) : String(v);
            return (
              <div key={col} className="flex gap-2 text-xs leading-relaxed">
                <span className="text-muted-foreground min-w-[3rem] flex-shrink-0">{col}</span>
                <span className="text-foreground break-all">{text}</span>
              </div>
            );
          })}
        </div>
      ))}
      {rows.length > MAX && (
        <div className="text-muted-foreground pt-1 text-center text-xs">
          还有 {rows.length - MAX} 条…
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。（`ToolCalls`/`ToolResult` 的导出签名未变，`ai.tsx` 调用处无需改。）

- [ ] **Step 3: 提交**

```bash
git add web/src/components/thread/messages/tool-calls.tsx
git commit -m "feat(web): 工具调用友好化（状态条+朴素展开+行卡）"
```

<!-- APPEND-MARKER-5 -->

## Task 11: 用户气泡用主色

**Files:**
- Modify: `web/src/components/thread/messages/human.tsx`（约 113-117 行）

现状：
```tsx
{contentString ? (
  <p className="bg-muted ml-auto w-fit rounded-3xl px-4 py-2 text-right whitespace-pre-wrap">
    {contentString}
  </p>
) : null}
```

- [ ] **Step 1: 改气泡配色为主色**

替换为：

```tsx
{contentString ? (
  <p className="bg-primary text-primary-foreground ml-auto w-fit rounded-3xl px-4 py-2 text-right whitespace-pre-wrap">
    {contentString}
  </p>
) : null}
```

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/thread/messages/human.tsx
git commit -m "feat(web): 用户气泡改用主色"
```

---

## Task 12: 侧栏品牌化与会话列表

**Files:**
- Modify: `web/src/components/thread/history/index.tsx`（整体替换）

侧栏顶部品牌区、新对话按钮、「最近」分组、会话项选中态、底部用户区。新对话/用户名由 props 接入（用户名本地用 mock 占位）。

- [ ] **Step 1: 整体替换 history/index.tsx**

```tsx
// web/src/components/thread/history/index.tsx
import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { Thread } from "@langchain/langgraph-sdk";
import { useEffect } from "react";

import { getContentString } from "../utils";
import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { SquarePen } from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";

function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");

  return (
    <div className="flex h-full w-full flex-col items-start gap-1 overflow-y-auto px-2 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
      {threads.map((t) => {
        let itemText = t.thread_id;
        if (
          typeof t.values === "object" &&
          t.values &&
          "messages" in t.values &&
          Array.isArray(t.values.messages) &&
          t.values.messages?.length > 0
        ) {
          itemText = getContentString(t.values.messages[0].content);
        }
        const active = t.thread_id === threadId;
        return (
          <button
            key={t.thread_id}
            type="button"
            onClick={(e) => {
              e.preventDefault();
              onThreadClick?.(t.thread_id);
              if (t.thread_id === threadId) return;
              setThreadId(t.thread_id);
            }}
            className={cn(
              "w-full truncate rounded-lg px-3 py-2 text-left text-sm transition-colors",
              active
                ? "bg-accent text-accent-foreground font-medium"
                : "text-foreground/80 hover:bg-secondary",
            )}
          >
            {itemText}
          </button>
        );
      })}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex w-full flex-col gap-1 px-2">
      {Array.from({ length: 12 }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

function SidebarBody() {
  const [, setThreadId] = useQueryState("threadId");
  const { getThreads, threads, setThreads, threadsLoading, setThreadsLoading } =
    useThreads();

  useEffect(() => {
    if (typeof window === "undefined") return;
    setThreadsLoading(true);
    getThreads()
      .then(setThreads)
      .catch(console.error)
      .finally(() => setThreadsLoading(false));
  }, []);

  return (
    <div className="flex h-full w-full flex-col">
      {/* 品牌区 */}
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-lg text-sm">
          {BRAND.mark}
        </span>
        <span className="text-foreground text-[15px] font-semibold">{BRAND.name}</span>
      </div>
      {/* 新对话 */}
      <div className="px-2 pb-2">
        <Button
          className="bg-primary text-primary-foreground hover:bg-primary/90 w-full justify-start gap-2"
          onClick={() => setThreadId(null)}
        >
          <SquarePen className="size-4" />
          新对话
        </Button>
      </div>
      <div className="text-muted-foreground px-4 pt-2 pb-1 text-xs tracking-wide">最近</div>
      <div className="min-h-0 flex-1">
        {threadsLoading ? <ThreadHistoryLoading /> : <ThreadList threads={threads} />}
      </div>
      {/* 用户区（本地 mock 占位） */}
      <div className="border-border mt-auto flex items-center gap-2.5 border-t px-4 py-3">
        <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-full text-xs">
          我
        </span>
        <span className="text-muted-foreground text-xs">团队成员</span>
      </div>
    </div>
  );
}

export default function ThreadHistory() {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );

  return (
    <>
      <div className="hidden h-screen w-[300px] shrink-0 flex-col border-r lg:flex">
        <SidebarBody />
      </div>
      <div className="lg:hidden">
        <Sheet
          open={!!chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (isLargeScreen) return;
            setChatHistoryOpen(open);
          }}
        >
          <SheetContent side="left" className="flex w-[300px] p-0 lg:hidden">
            <SheetHeader className="sr-only">
              <SheetTitle>会话历史</SheetTitle>
            </SheetHeader>
            <SidebarBody />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
```

> 注：`thread/index.tsx` 里那个宽 300px 的 motion 容器（260-283 行）已经把 `<ThreadHistory />` 包在白底滑出层里。本组件桌面端返回的 `w-[300px]` 块嵌在其中即可，配色由 `border-r` + 内部 `bg` 跟随主题。`thread/index.tsx` 的容器 `bg-white` 在 Task 13 改为 `bg-sidebar`。

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 3: 提交**

```bash
git add web/src/components/thread/history/index.tsx
git commit -m "feat(web): 侧栏品牌化、新对话、选中态、用户区"
```

<!-- APPEND-MARKER-6 -->

## Task 13: Thread 集成（顶栏品牌、欢迎页、actions provider、中文化）

**Files:**
- Modify: `web/src/components/thread/index.tsx`（多处精确编辑）

本任务把前面的组件接起来：注入 `submitText`、品牌化顶栏与欢迎页、移除 GitHub 图标、文案中文化、侧栏容器配色。逐步精确替换。

- [ ] **Step 1: 调整导入**

在 `web/src/components/thread/index.tsx` 顶部：
- 加：`import { BRAND } from "@/lib/brand";`
- 加：`import { ThreadActionsProvider } from "@/lib/thread-actions";`
- 删除 `import { GitHubSVG } from "../icons/github";`（不再用）。

- [ ] **Step 2: 删除 OpenGitHubRepo 组件**

删除 `web/src/components/thread/index.tsx` 中整个 `function OpenGitHubRepo() { ... }` 定义（约 90-112 行，含 `TooltipProvider` 包裹的 GitHub 链接）。其引用在 Step 6/7 一并移除。

- [ ] **Step 3: 抽出 submitText 并包裹 Provider**

现有 `handleSubmit`（约 197-237 行）从 `input`/`contentBlocks` 构造消息。新增一个可复用的 `submitText`，并让 `handleSubmit` 复用它。在 `handleSubmit` 定义之前插入：

```tsx
  const submitText = (text: string) => {
    if (!text.trim() || isLoading) return;
    setFirstTokenReceived(false);
    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: text as Message["content"],
    };
    const toolMessages = ensureToolCallsHaveResponses(stream.messages);
    const context =
      Object.keys(artifactContext).length > 0 ? artifactContext : undefined;
    stream.submit(
      { messages: [...toolMessages, newHumanMessage], context },
      {
        streamMode: ["values"],
        streamSubgraphs: true,
        streamResumable: true,
        optimisticValues: (prev) => ({
          ...prev,
          context,
          messages: [...(prev.messages ?? []), ...toolMessages, newHumanMessage],
        }),
      },
    );
  };
```

- [ ] **Step 4: 包裹整个返回 JSX 于 Provider**

`Thread` 的 `return (` 当前最外层是 `<div className="flex h-screen w-full overflow-hidden">`。在它外面包一层 Provider：

```tsx
  return (
    <ThreadActionsProvider value={{ submitText }}>
      <div className="flex h-screen w-full overflow-hidden">
        {/* …原有全部内容保持不变… */}
      </div>
    </ThreadActionsProvider>
  );
```

（即：在最外层 `<div ...>` 前加 `<ThreadActionsProvider value={{ submitText }}>`，在其对应闭合 `</div>` 后加 `</ThreadActionsProvider>`。）

- [ ] **Step 5: 侧栏滑出容器配色**

把约 262 行的 `className="absolute z-20 h-full overflow-hidden border-r bg-white"` 中的 `bg-white` 改为 `bg-sidebar`。

- [ ] **Step 6: 顶栏品牌（chatStarted 分支）**

把 chatStarted 顶栏里的 LangGraph logo + "Agent Chat"（约 363-370 行）替换为品牌：

```tsx
                  <span className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-lg">
                    {BRAND.mark}
                  </span>
                  <span className="text-xl font-semibold tracking-tight">
                    {BRAND.name}
                  </span>
```

并删除该顶栏右侧的 `<OpenGitHubRepo />`（约 374-376 行 `<div className="flex items-center"><OpenGitHubRepo /></div>`，整块删掉）。把「New thread」的 `tooltip="New thread"` 改为 `tooltip="新对话"`。

- [ ] **Step 7: 非 chatStarted 顶栏移除 GitHub 图标**

把 `!chatStarted` 分支里 `<div className="absolute top-2 right-4 flex items-center"><OpenGitHubRepo /></div>`（约 328-330 行）整块删掉。

- [ ] **Step 8: 欢迎页品牌 + 示例 chip**

把 footer 里 `!chatStarted` 的 LangGraph logo + "Agent Chat"（约 437-444 行）替换为品牌 + slogan + 示例：

```tsx
                  {!chatStarted && (
                    <div className="flex flex-col items-center gap-3">
                      <span className="bg-primary text-primary-foreground flex size-14 items-center justify-center rounded-2xl text-3xl">
                        {BRAND.mark}
                      </span>
                      <h1 className="text-2xl font-semibold tracking-tight">{BRAND.name}</h1>
                      <p className="text-muted-foreground text-sm">{BRAND.slogan}</p>
                      <div className="mt-2 flex max-w-xl flex-wrap justify-center gap-2">
                        {BRAND.examples.map((ex) => (
                          <button
                            key={ex}
                            type="button"
                            onClick={() => submitText(ex)}
                            className="border-border text-foreground/70 hover:border-primary hover:bg-accent rounded-full border bg-card px-3.5 py-1.5 text-xs transition-colors"
                          >
                            {ex}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
```

- [ ] **Step 9: 输入框与开关文案中文化**

在 `web/src/components/thread/index.tsx` 中：
- `placeholder="Type your message..."` → `placeholder="说说你想写什么方向…"`
- `Hide Tool Calls` 文案那段（含 `Switch id="render-tool-calls"` 与 `Label`，约 488-500 行）整块删除（友好化后不需要该开关）。一并删除文件顶部不再使用的 `Switch`、`Label` 导入与 `hideToolCalls` 的 `useQueryState`（约 123-126 行）——**注意**：`ai.tsx` 仍在用自己的 `hideToolCalls`，那是另一个文件，不要动 ai.tsx。仅删除 index.tsx 内本地未再使用的。若删除后 `hideToolCalls` 在 index.tsx 仍有引用则保留声明，只删 UI。
- `Upload PDF or Image` → `上传图片或 PDF`
- 「Send」按钮文字 `Send` → `发送`；停止按钮 `Cancel` → `停止`。
- `Scroll to bottom` → `回到底部`。

- [ ] **Step 10: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。若报 `hideToolCalls`/`Switch`/`Label` 未使用，按 Step 9 删除对应声明；若仍被引用则保留。

- [ ] **Step 11: 提交**

```bash
git add web/src/components/thread/index.tsx
git commit -m "feat(web): Thread 品牌化、欢迎页示例、submitText、文案中文化"
```

<!-- APPEND-MARKER-7 -->

## Task 14: 配置表单品牌化（Stream.tsx，顺带）

**Files:**
- Modify: `web/src/providers/Stream.tsx`（约 188-199 行的表单头部）

本地 `.env` 配好 URL/assistantId 时此表单不出现，但属品牌化范围，顺手改掉 logo 与英文文案。

- [ ] **Step 1: 替换表单头部品牌块**

把 `web/src/providers/Stream.tsx` 中（约 190-199 行）：
```tsx
              <LangGraphLogoSVG className="h-7" />
              <h1 className="text-xl font-semibold tracking-tight">
                Agent Chat
              </h1>
            </div>
            <p className="text-muted-foreground">
              Welcome to Agent Chat! Before you get started, you need to enter
              the URL of the deployment and the assistant / graph ID.
            </p>
```
替换为：
```tsx
              <span className="text-3xl">🍠</span>
              <h1 className="text-xl font-semibold tracking-tight">
                小红书文案助手
              </h1>
            </div>
            <p className="text-muted-foreground">
              连接你的 LangGraph 服务后即可开始。请填写部署地址与图/助手 ID。
            </p>
```

> `LangGraphLogoSVG` 导入若变为未使用，删除其 import 行（约 20 行）。其他英文 Label（Deployment URL 等）属开发配置项，本期可不译，保留。

- [ ] **Step 2: 类型检查**

Run: `pnpm -C web exec tsc --noEmit`
Expected: 通过。

- [ ] **Step 3: 提交**

```bash
git add web/src/providers/Stream.tsx
git commit -m "feat(web): 配置表单品牌化"
```

---

## Task 15: 后端约定 agent 用 fence 输出选题/文案

**Files:**
- Modify: `prompts.py`（工作流第 4、5 步）
- Modify: `skills/topic-content/SKILL.md`（第一步、第二步输出格式）

让 agent 把选题菜单包进 ` ```xhs_topics `、最终文案包进 ` ```xhs_copy `，前端才能渲染卡片。这是提示词层改动，不动后端逻辑。

- [ ] **Step 1: 改 prompts.py 的第 4 步（选题输出）**

把 `prompts.py` 中工作流第 4 步：
```
4. 基于分析,产出 3~5 个【选题方向】,以清晰列表呈现(每个选题:一句话角度 + 预期爆点)。
   **停在这里,等用户选择,不要直接写完整文案。**
```
替换为：
```
4. 基于分析,产出 3~5 个【选题方向】。**必须**用如下代码块输出(前端据此渲染成可点选卡片),
   intro 写一句引导语,topics 每项是"一句话角度（预期爆点）":

   ```xhs_topics
   {"intro": "根据你的爆款库，给你这几个方向，点一个我就展开写：", "topics": ["选题角度1（为什么可能火）", "选题角度2（……）"]}
   ```

   代码块必须是合法 JSON、单独成段。**停在这里,等用户选择,不要直接写完整文案。**
```

- [ ] **Step 2: 改 prompts.py 的第 5 步（文案输出）**

把第 5 步：
```
5. 用户选定某个选题后,写完整文案:
   - 标题(小红书标题党风格,可带 emoji)
   - 正文(分段、口语化、带 emoji、有记忆点)
   - 话题标签(#xxx 形式,5~10 个)
   以可直接复制的分块格式输出在对话里,同时用 write_file 存一份到 /drafts/<slug>.md。
```
替换为：
```
5. 用户选定某个选题后,写完整文案。**必须**用如下代码块输出(前端据此渲染成带一键复制的文案卡):

   ```xhs_copy
   {"title": "小红书标题党风格，可带 emoji", "body": "分段、口语化、带 emoji、有记忆点的正文（用 \\n 表示换行）", "tags": ["#标签1", "#标签2"]}
   ```

   代码块必须是合法 JSON（正文里的换行用 \\n、引号转义）、单独成段。
   同时用 write_file 存一份到 /drafts/<slug>.md。
```

- [ ] **Step 3: 同步改 SKILL.md**

把 `skills/topic-content/SKILL.md` 第一步第 4 点的"列表呈现"改为要求输出 ` ```xhs_topics ` JSON 块（同 Step 1 的格式与示例）；把第二步那段三引号 `【标题】/【正文】/【话题标签】` 模板替换为 ` ```xhs_copy ` JSON 块（同 Step 2 的格式）。保留"停下等用户选择""存 /drafts/"等流程说明不变。

- [ ] **Step 4: 提交**

```bash
git add prompts.py skills/topic-content/SKILL.md
git commit -m "feat: agent 用 xhs_topics/xhs_copy fence 输出选题与文案"
```

<!-- APPEND-MARKER-8 -->

## Task 16: 集成验证（构建 + 手动冒烟）

**Files:** 无（验证任务）

- [ ] **Step 1: 生产构建**

Run: `pnpm -C web build`
Expected: 构建成功，无类型/编译错误。若报错，定位到具体文件修复后重跑。

- [ ] **Step 2: 起后端（先清残留进程）**

Windows 下先确认无残留 python 进程占用 2024 端口（参考项目既有纪律）：

```bash
tasklist | grep -i python || echo "无 python 进程"
```
如有残留，逐个 `taskkill //PID <pid> //F`。然后单独终端起后端：
```bash
cd "e:/小红书智能体" && langgraph dev
```
Expected: 监听 http://localhost:2024，无报错。

- [ ] **Step 3: 起前端**

另一终端：
```bash
pnpm -C web dev
```
打开 http://localhost:3000。

- [ ] **Step 4: 冒烟核对清单（逐项确认）**

- [ ] 欢迎页：🍠 图标 + 「小红书文案助手」+ 「你的小红书爆款搭子🍠」+ 4 个示例 chip；点一个 chip 能发起对话。
- [ ] 整体观感：暖白底、赤陶橙主色、圆角、中文字体；无 LangGraph logo、无 GitHub 图标、无英文残留（顶栏/输入框/按钮）。
- [ ] 用户气泡为橙色、右对齐。
- [ ] 选题：发一个方向（如「帮我出夏日防晒选题」），agent 出选题后渲染成可点卡片（序号+文字+箭头）；点某张卡，自动发出「写第 N 个」并继续生成。
- [ ] 文案：选定后渲染成 `CopyCard`（完成文案标签 + 标题/正文/标签）；点「一键复制」→ 按钮变「已复制」，粘贴板内容为标题+正文+标签。
- [ ] 降级：若某次 agent 没按 fence 输出，内容仍以普通 markdown 正常显示、不报错、不白屏。
- [ ] 工具调用：读爆款库时显示「⟳ 正在读取你的爆款库…」；完成变绿色「✓ 已读取爆款库（N 条）」；点开看到「列名：值」行卡；再点「查看原始（开发用）」显示 JSON。
- [ ] 工具隐藏：读 SKILL / 写 /analysis/ 等内部操作不出现在界面。
- [ ] 侧栏：品牌区、「新对话」橙按钮、「最近」分组、会话项选中态高亮、底部用户区显示正常。

- [ ] **Step 5: 多用户隔离回归**

确认前端改动未影响 auth。复用既有脚本：
```bash
cd "e:/小红书智能体" && python verify_1b3.py
```
Expected: 与改造前一致（隔离/共享行为不变）。

- [ ] **Step 6: 收尾提交（若冒烟中有微调）**

```bash
git add -A
git commit -m "fix(web): 集成冒烟修正"
```

若无修改则跳过。

---

## 自检回顾（写计划后）

- **Spec 覆盖**：换肤(T1/T2) · 品牌常量(T3) · 选题卡(T5/T6/T8) · 文案卡(T7/T8) · 欢迎页(T13) · 侧栏(T12) · 工具友好化(T9/T10) · 中文化(T13/T14) · 后端 fence 约定(T15) · 验证(T16)。spec 五个重点环节全覆盖。
- **前端不猜语义**：T10 的 RowCards 按 columns 平铺，不识别字段；与 spec 5.8 核心原则一致。
- **两条消息配对**：T10 用 `tc.id ↔ tool_call_id` + resolvedIds 集合判断进行中/完成，与 spec 一致。
- **类型一致性**：`parseXhsBlocks`/`Segment`/`TopicsSegment`/`CopySegment`(T5) 被 T6/T7/T8 复用；`getToolDisplay`/`extractRowCount`(T9) 被 T10 复用；`submitText`(T13) 经 `ThreadActions`(T4) 被 T6/T13 复用，签名一致。
- **降级**：T5 解析失败并入文本段；T8 文本段走 MarkdownText；保证不白屏。








