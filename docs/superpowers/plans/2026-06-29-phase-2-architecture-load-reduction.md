# Phase 2 Architecture Load Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce frontend architecture load without changing user behavior, and document runtime data/control paths in one maintainer-facing map.

**Architecture:** Start with the safest Thread extraction: move draft title/body, autosave, dirty-state, and AI-draft parsing behind `useThreadDraftState`. Keep `Thread` responsible for layout, stream submission, and route/view orchestration. Add `docs/architecture/runtime-map.md` as the single map for production request, identity, evidence, save, model, and background flows.

**Tech Stack:** Next.js, React 19 hooks, TypeScript, Node test runner, existing source-level frontend guard tests, Markdown architecture docs.

---

## Scope

This plan implements the first Phase 2 slice from `docs/superpowers/specs/2026-06-29-quality-architecture-operations-design.md`.

Do not extract Feishu workspace, preview, command palette, or workbench tab state in this slice. Those remain future Phase 2 tasks after the draft extraction is verified.

## File Map

- Create `web/src/components/thread/useThreadDraftState.ts`: draft state hook plus pure helpers for autosave keys and AI draft parsing.
- Modify `web/src/components/thread/index.tsx`: remove inline draft state/effects and consume the new hook.
- Modify `web/tests/thread-context.test.ts`: assert `Thread` wires `useThreadDraftState` and no longer owns draft autosave directly.
- Create `web/tests/thread-draft-state.test.ts`: unit tests for pure helper behavior.
- Create `docs/architecture/runtime-map.md`: runtime architecture and operational invariants map.

---

### Task 1: Add Draft State Contract Tests

**Files:**
- Create: `web/tests/thread-draft-state.test.ts`
- Modify: `web/tests/thread-context.test.ts`

- [ ] **Step 1: Write pure helper tests**

Create `web/tests/thread-draft-state.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDraftAutosaveKey,
  parseAiDraft,
  readDraftSnapshot,
  shouldDirtyDraft,
} from "../src/components/thread/useThreadDraftState";

test("buildDraftAutosaveKey scopes drafts by thread and new conversation", () => {
  assert.equal(buildDraftAutosaveKey(null), "xhs_autosave_draft_new");
  assert.equal(buildDraftAutosaveKey("thread-1"), "xhs_autosave_draft_thread-1");
});

test("parseAiDraft extracts short first line as title and keeps full content", () => {
  const draft = parseAiDraft("# ✨ 周末轻露营清单\n正文第一段\n正文第二段");

  assert.deepEqual(draft, {
    title: "周末轻露营清单",
    content: "# ✨ 周末轻露营清单\n正文第一段\n正文第二段",
  });
});

test("parseAiDraft falls back when first line is too long", () => {
  const draft = parseAiDraft("这是一行超过四十个字符的标题候选它不应该被塞进手机卡片标题字段里\n正文");

  assert.deepEqual(draft, {
    title: "小红书爆款文案",
    content: "这是一行超过四十个字符的标题候选它不应该被塞进手机卡片标题字段里\n正文",
  });
});

test("readDraftSnapshot tolerates missing and malformed autosave payloads", () => {
  assert.deepEqual(readDraftSnapshot(null), { title: "", content: "" });
  assert.deepEqual(readDraftSnapshot("{bad json"), { title: "", content: "" });
  assert.deepEqual(readDraftSnapshot(JSON.stringify({ title: "标题", content: "正文" })), {
    title: "标题",
    content: "正文",
  });
});

test("shouldDirtyDraft only marks dirty after a saved baseline exists", () => {
  assert.equal(shouldDirtyDraft({ title: "A", content: "B" }, { title: "", content: "" }), false);
  assert.equal(shouldDirtyDraft({ title: "A", content: "B" }, { title: "A", content: "B" }), false);
  assert.equal(shouldDirtyDraft({ title: "A2", content: "B" }, { title: "A", content: "B" }), true);
});
```

- [ ] **Step 2: Strengthen Thread source guardrails**

In `web/tests/thread-context.test.ts`, add:

```ts
test("Thread delegates draft autosave and AI draft parsing to useThreadDraftState", () => {
  const thread = src("components", "thread", "index.tsx");
  const hook = src("components", "thread", "useThreadDraftState.ts");

  assert.match(thread, /useThreadDraftState\(/);
  assert.doesNotMatch(thread, /xhs_autosave_draft_/);
  assert.doesNotMatch(thread, /setLastSavedContent\(/);
  assert.match(hook, /buildDraftAutosaveKey/);
  assert.match(hook, /parseAiDraft/);
});
```

- [ ] **Step 3: Run tests and verify RED**

Run:

```powershell
cd web
npm run test:unit
```

Expected: FAIL because `useThreadDraftState.ts` does not exist and `Thread` still owns autosave logic.

---

### Task 2: Extract `useThreadDraftState`

**Files:**
- Create: `web/src/components/thread/useThreadDraftState.ts`
- Modify: `web/src/components/thread/index.tsx`

- [ ] **Step 1: Implement pure helpers and hook**

Create `web/src/components/thread/useThreadDraftState.ts` with:

```ts
import { Message } from "@langchain/langgraph-sdk";
import { Dispatch, SetStateAction, useEffect, useRef, useState } from "react";

export interface DraftSnapshot {
  title: string;
  content: string;
}

const DEFAULT_DRAFT: DraftSnapshot = {
  title: "精致露营「搬家式」装备清单",
  content:
    "夏天太适合露营啦！⛺但是作为一个精致的搬家式露营玩家，带什么装备去真的大有讲究！今天就给大家盘点一下我私藏的「搬家式」露营好物，少带一件体验感都打折！\n\n👇精致露营必带清单：\n1️⃣ 双顶充气天幕：不仅防雨防晒，最重要是拍照真的超出片！空间很大，容纳8个人也宽敞。",
};

export function buildDraftAutosaveKey(threadId: string | null): string {
  return `xhs_autosave_draft_${threadId ?? "new"}`;
}

export function parseAiDraft(content: string): DraftSnapshot {
  const text = content.trim();
  const firstLine = text
    .split("\n")[0]
    .replace(/^[#\s*✨🍠⛺☕🌿👇📝🌟🔥🚗]*/gu, "")
    .trim();
  return {
    title: firstLine && firstLine.length < 40 ? firstLine : "小红书爆款文案",
    content: text,
  };
}

export function readDraftSnapshot(raw: string | null): DraftSnapshot {
  if (!raw) return { title: "", content: "" };
  try {
    const parsed = JSON.parse(raw) as Partial<DraftSnapshot>;
    return {
      title: typeof parsed.title === "string" ? parsed.title : "",
      content: typeof parsed.content === "string" ? parsed.content : "",
    };
  } catch {
    return { title: "", content: "" };
  }
}

export function shouldDirtyDraft(current: DraftSnapshot, saved: DraftSnapshot): boolean {
  return Boolean(saved.content && (current.content !== saved.content || current.title !== saved.title));
}

export interface ThreadDraftState {
  draftTitle: string;
  setDraftTitle: Dispatch<SetStateAction<string>>;
  draftContent: string;
  setDraftContent: Dispatch<SetStateAction<string>>;
  isDirty: boolean;
  setIsDirty: Dispatch<SetStateAction<boolean>>;
  lastSavedTitle: string;
  lastSavedContent: string;
  resetForThreadSwitch: (threadId: string | null) => void;
}

export function useThreadDraftState(threadId: string | null, messages: Message[]): ThreadDraftState {
  const [draftTitle, setDraftTitle] = useState(DEFAULT_DRAFT.title);
  const [draftContent, setDraftContent] = useState(DEFAULT_DRAFT.content);
  const [isDirty, setIsDirty] = useState(false);
  const [lastSavedContent, setLastSavedContent] = useState("");
  const [lastSavedTitle, setLastSavedTitle] = useState("");
  const lastAiMessageId = useRef<string | undefined>(undefined);

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (!lastMsg || lastMsg.type !== "ai" || typeof lastMsg.content !== "string") return;
    if (lastMsg.id && lastMsg.id === lastAiMessageId.current) return;
    lastAiMessageId.current = lastMsg.id;
    const next = parseAiDraft(lastMsg.content);
    setDraftTitle(next.title);
    setDraftContent(next.content);
    setLastSavedTitle(next.title);
    setLastSavedContent(next.content);
    setIsDirty(false);
  }, [messages]);

  useEffect(() => {
    const current = { title: draftTitle, content: draftContent };
    localStorage.setItem(buildDraftAutosaveKey(threadId), JSON.stringify(current));
    setIsDirty(shouldDirtyDraft(current, { title: lastSavedTitle, content: lastSavedContent }));
  }, [threadId, draftTitle, draftContent, lastSavedContent, lastSavedTitle]);

  const resetForThreadSwitch = (nextThreadId: string | null) => {
    setIsDirty(false);
    setLastSavedContent("");
    setLastSavedTitle("");
    const saved = readDraftSnapshot(localStorage.getItem(buildDraftAutosaveKey(nextThreadId)));
    setDraftTitle(saved.title);
    setDraftContent(saved.content);
  };

  return {
    draftTitle,
    setDraftTitle,
    draftContent,
    setDraftContent,
    isDirty,
    setIsDirty,
    lastSavedTitle,
    lastSavedContent,
    resetForThreadSwitch,
  };
}
```

- [ ] **Step 2: Replace inline draft state in `Thread`**

In `web/src/components/thread/index.tsx`:

- Import `useThreadDraftState`.
- Remove inline `draftTitle`, `draftContent`, `isDirty`, `lastSavedTitle`, `lastSavedContent` state declarations.
- Remove the duplicate AI-to-draft effects.
- Use `useThreadDraftState(threadId, messages)` and destructure the same values.
- In the thread-switch effect, call `resetForThreadSwitch(threadId)` instead of reading localStorage directly.

- [ ] **Step 3: Run focused frontend tests**

Run:

```powershell
cd web
npm run test:unit
```

Expected: PASS.

- [ ] **Step 4: Run TypeScript**

Run:

```powershell
cd web
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 5: Commit draft extraction**

Run:

```powershell
git add -- web/src/components/thread/useThreadDraftState.ts web/src/components/thread/index.tsx web/tests/thread-draft-state.test.ts web/tests/thread-context.test.ts
git commit -m "refactor(ui): extract thread draft state"
```

---

### Task 3: Add Runtime Architecture Map

**Files:**
- Create: `docs/architecture/runtime-map.md`

- [ ] **Step 1: Write runtime map**

Create `docs/architecture/runtime-map.md` with sections for:

- request flow
- identity flow
- evidence flow
- save flow
- model flow
- background flow
- invariants not to change casually
- related guard tests

- [ ] **Step 2: Verify doc names hard constraints**

Run:

```powershell
rg -n "N_WORKERS=1|Postgres|Feishu|Config Center|evidence|outbox|LangGraph" docs/architecture/runtime-map.md
```

Expected: output includes all listed concepts.

- [ ] **Step 3: Commit runtime map**

Run:

```powershell
git add -- docs/architecture/runtime-map.md
git commit -m "docs: add runtime architecture map"
```

---

### Task 4: Full Phase 2 Slice Verification

**Files:**
- No code files should change unless verification finds a defect.

- [ ] **Step 1: Run frontend unit tests**

Run:

```powershell
cd web
npm run test:unit
```

Expected: PASS.

- [ ] **Step 2: Run TypeScript**

Run:

```powershell
cd web
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 3: Run Python regression suite**

Run:

```powershell
$env:HTTPS_PROXY='socks5://127.0.0.1:7897'
uv run pytest
```

Expected: PASS.

- [ ] **Step 4: Inspect scope**

Run:

```powershell
git diff --stat HEAD~2..HEAD
```

Expected: files are limited to the hook extraction, associated tests, and runtime map.

---

## Completion Criteria

This Phase 2 slice is complete when:

- `Thread` delegates draft autosave and AI-draft parsing to `useThreadDraftState`.
- Draft autosave keys remain per-thread and preserve the `new` conversation fallback.
- Dirty-state behavior still requires a saved baseline.
- Existing thread context values remain available to child components.
- `docs/architecture/runtime-map.md` gives maintainers one place to understand runtime flows and invariants.
- `npm run test:unit`, `tsc --noEmit`, and `uv run pytest` pass.
