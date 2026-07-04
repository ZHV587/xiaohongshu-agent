import type { Message } from "@langchain/langgraph-sdk";
import {
  type Dispatch,
  type SetStateAction,
  useEffect,
  useState,
} from "react";
import { getContentString } from "@/components/thread/utils";

export interface DraftSnapshot {
  title: string;
  content: string;
}

export function buildDraftAutosaveKey(threadId: string | null): string {
  return `xhs_autosave_draft_${threadId ?? "new"}`;
}

// 只有 topics/panel 结构块、没有正文/xhs_copy 的 AI 消息不是草稿源(如"我整理了几个选题方向"
// + ```xhs_topics``` 块)。用它当草稿会把选题摘要误写进正文。这类消息返回 null,不覆盖既有草稿。
const NON_DRAFT_BLOCK_RE = /```xhs_(topics|panel)\b/;

/** 从单条 AI 文本解析草稿快照;若这条消息不含可用草稿(纯选题/面板/空)返回 null。 */
export function parseAiDraft(content: string): DraftSnapshot | null {
  const text = content.trim();
  if (!text) return null;

  // 优先:结构化 xhs_copy 块(权威草稿)。
  const structuredDraft = parseStructuredCopyDraft(text);
  if (structuredDraft) return structuredDraft;

  // 无 xhs_copy 但含 topics/panel 块 → 这是选题/面板消息,不是草稿,跳过(不覆盖既有草稿)。
  if (NON_DRAFT_BLOCK_RE.test(text)) return null;

  const firstLine = text
    .split("\n")[0]
    .replace(/^[#\s*✨🍠⛺☕🌿👇📝🌟🔥🚗]*/gu, "")
    .trim();

  return {
    title: firstLine && firstLine.length < 40 ? firstLine : "小红书爆款文案",
    content: text,
  };
}

/** 从消息流里取「最后一条含可用草稿的 AI 消息」的草稿快照。
 *
 * 旧实现只看 messages[len-1] 且要求 content 为 string:真实流里草稿那条 AI 消息后常跟着
 * tool/思考/human 消息,或 content 是 Anthropic 内容块数组 → 草稿永远解析不出、进深创是空态、
 * 返回后"内容消失"。这里从后往前扫,用 getContentString 兼容数组态,取第一条能解析出草稿的 AI 消息。 */
export function latestDraftFromMessages(messages: Message[]): DraftSnapshot | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.type !== "ai") continue;
    const content = getContentString(m.content);
    if (!content) continue;
    const draft = parseAiDraft(content);
    if (draft) return draft;
  }
  return null;
}

function parseStructuredCopyDraft(text: string): DraftSnapshot | null {
  const fence = /```xhs_copy[ \t]*\r?\n?([\s\S]*?)```/g;
  let match: RegExpExecArray | null;
  let latest: RegExpExecArray | null = null;
  while ((match = fence.exec(text)) !== null) latest = match;
  if (!latest) return null;

  try {
    const parsed = JSON.parse(latest[1].trim()) as {
      versions?: Array<{ title?: unknown; body?: unknown }>;
      title?: unknown;
      body?: unknown;
    };
    const firstVersion = Array.isArray(parsed.versions) ? parsed.versions[0] : null;
    const title = firstVersion?.title ?? parsed.title;
    const body = firstVersion?.body ?? parsed.body;
    if (typeof body !== "string" || !body.trim()) return null;
    return {
      title: typeof title === "string" && title.trim() ? title.trim() : "小红书爆款文案",
      content: body.trim(),
    };
  } catch {
    return null;
  }
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
    // 扫全量消息取最后一条含草稿的 AI 消息(而非只看数组末尾)。无草稿源(纯选题/工具/human
    // 结尾)时不动既有草稿——避免流中后续非草稿消息把已生成的正文清空("内容消失")。
    const next = latestDraftFromMessages(messages);
    if (!next) return;
    queueMicrotask(() => {
      setDraftTitle(next.title);
      setDraftContent(next.content);
      setLastSavedTitle(next.title);
      setLastSavedContent(next.content);
      setIsDirty(false);
    });
  }, [messages]);

  useEffect(() => {
    const current = { title: draftTitle, content: draftContent };
    localStorage.setItem(buildDraftAutosaveKey(threadId), JSON.stringify(current));
    queueMicrotask(() => {
      setIsDirty(
        shouldDirtyDraft(current, {
          title: lastSavedTitle,
          content: lastSavedContent,
        }),
      );
    });
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
