"use client";

// AppShell — the production root UI. Mounts the 创作运营工作室 (StudioShell)
// inside the real ThreadStateProvider (LangGraph stream / draft / Feishu HITL
// wiring) and StudioProvider (the useStudio bridge). Replaces the old
// three-pane Thread() as page.tsx's leaf.

import { ThreadStateProvider } from "./thread/ThreadStateProvider";
import { StudioProvider } from "./studio/StudioContext";
import { StudioShell } from "./studio/StudioShell";

export function AppShell() {
  return (
    <ThreadStateProvider>
      <StudioProvider>
        <StudioShell />
      </StudioProvider>
    </ThreadStateProvider>
  );
}
