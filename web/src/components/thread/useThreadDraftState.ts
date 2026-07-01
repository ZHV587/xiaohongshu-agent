import type { Message } from "@langchain/langgraph-sdk";
import {
  type Dispatch,
  type SetStateAction,
  useEffect,
  useState,
} from "react";

export interface DraftSnapshot {
  title: string;
  content: string;
}

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

export function shouldDirtyDraft(
  current: DraftSnapshot,
  saved: DraftSnapshot,
): boolean {
  return Boolean(
    saved.content &&
      (current.content !== saved.content || current.title !== saved.title),
  );
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

export function useThreadDraftState(
  threadId: string | null,
  messages: Message[],
): ThreadDraftState {
  const [draftTitle, setDraftTitle] = useState("");
  const [draftContent, setDraftContent] = useState("");
  const [isDirty, setIsDirty] = useState(false);
  const [lastSavedContent, setLastSavedContent] = useState("");
  const [lastSavedTitle, setLastSavedTitle] = useState("");

  useEffect(() => {
    const lastMsg = messages[messages.length - 1];
    if (!lastMsg || lastMsg.type !== "ai" || typeof lastMsg.content !== "string") {
      return;
    }

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
    setIsDirty(
      shouldDirtyDraft(current, {
        title: lastSavedTitle,
        content: lastSavedContent,
      }),
    );
  }, [threadId, draftTitle, draftContent, lastSavedContent, lastSavedTitle]);

  const resetForThreadSwitch = (nextThreadId: string | null) => {
    setIsDirty(false);
    setLastSavedContent("");
    setLastSavedTitle("");
    const saved = readDraftSnapshot(
      localStorage.getItem(buildDraftAutosaveKey(nextThreadId)),
    );
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
