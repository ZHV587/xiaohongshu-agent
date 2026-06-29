# Phase 2 Command Palette State Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Ctrl+P command palette state and keyboard handling out of `Thread` while preserving existing command execution behavior.

**Architecture:** Create `useCommandPaletteState` for palette open state, search text, and global keyboard shortcuts. Keep `handleExecuteCommand` in `Thread` because it depends on `submitText`, `draftContent`, and toast side effects.

**Tech Stack:** React hooks, TypeScript, existing Node source-guard unit tests.

---

## File Map

- Create `web/src/components/thread/useCommandPaletteState.ts`: hook plus pure keyboard helper.
- Modify `web/src/components/thread/index.tsx`: replace inline state/effect with the hook.
- Modify `web/tests/thread-context.test.ts`: assert `Thread` delegates command palette state and no longer owns keyboard listener logic.
- Create `web/tests/command-palette-state.test.ts`: verify the pure keyboard helper.

---

### Task 1: Add Tests

**Files:**
- Create: `web/tests/command-palette-state.test.ts`
- Modify: `web/tests/thread-context.test.ts`

- [ ] **Step 1: Add pure keyboard helper tests**

Create tests for:

- Ctrl+P opens/toggles.
- Meta+P opens/toggles.
- Plain `p` is ignored.
- Escape closes.

- [ ] **Step 2: Add Thread delegation guard**

Assert that `Thread` calls `useCommandPaletteState`, and no longer contains raw `addEventListener("keydown"` or `e.key.toLowerCase() === "p"` logic.

- [ ] **Step 3: Run RED**

Run:

```powershell
cd web
npm run test:unit
```

Expected: FAIL because the hook does not exist and `Thread` still owns keyboard handling.

---

### Task 2: Extract Hook

**Files:**
- Create: `web/src/components/thread/useCommandPaletteState.ts`
- Modify: `web/src/components/thread/index.tsx`

- [ ] **Step 1: Implement hook**

Expose:

- `showCommandPalette`
- `setShowCommandPalette`
- `cmdSearch`
- `setCmdSearch`

The hook registers the same keydown behavior as before: Ctrl/Cmd+P toggles the palette and prevents browser print; Escape closes it.

- [ ] **Step 2: Wire `Thread`**

Replace inline command palette state/effect with `useCommandPaletteState()`.

- [ ] **Step 3: Verify**

Run:

```powershell
cd web
npm run test:unit
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: PASS.

- [ ] **Step 4: Commit**

Run:

```powershell
git add -- docs/superpowers/plans/2026-06-29-phase-2-command-palette-state.md web/src/components/thread/useCommandPaletteState.ts web/src/components/thread/index.tsx web/tests/command-palette-state.test.ts web/tests/thread-context.test.ts
git commit -m "refactor(ui): extract command palette state"
```

---

## Completion Criteria

- `Thread` no longer owns command palette state or keyboard listener logic.
- Ctrl/Cmd+P and Escape behavior is preserved.
- `handleExecuteCommand` remains in `Thread` until command execution dependencies are separated.
- `npm run test:unit` and `tsc --noEmit` pass.
