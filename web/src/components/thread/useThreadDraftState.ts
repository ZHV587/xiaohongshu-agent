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

/** 从单条 AI 文本解析草稿快照;仅当含结构化成品块(xhs_copy/xhs_imitation)时返回草稿,
 *  其它(纯选题/面板/确认语/问句/空)一律返回 null,不覆盖既有草稿。 */
export function parseAiDraft(content: string): DraftSnapshot | null {
  const text = content.trim();
  if (!text) return null;

  // 草稿的**唯一**来源是结构化成品块:xhs_copy(常规文案)或 xhs_imitation(两段式仿写成品)。
  // 二者都由输出协议(prompts.py §5)强制,正文/标题从块里的 versions[0] 或顶层 title/body 取。
  return parseStructuredCopyDraft(text);

  // ⚠ 不再有"纯文本兜底":此前任何 AI 大白话(如采纳确认"已收录 N 条…"、意图分流问句、
  // 选题引导语)都会被当草稿写进编辑器 → ① 正文被确认语污染;② status 变 draft 而非 writing,
  // "生成中"状态条不显示;③ chooseTopic 的 alreadyHasCopy 误判为真、点选题卡直接早返回不再
  // 触发生成(表现:点了没反应、几分钟无动静)。成品在本系统永远走 xhs_copy/xhs_imitation 块,
  // 故只认结构化块,大白话一律不当草稿(返回 null,不覆盖既有草稿)。
}

/** 从消息流里取「最后一条含可用草稿的 AI 消息」的草稿快照。
 *
 * 从后往前扫,用 getContentString 兼容数组态,取**当前这一轮**里能解析出草稿的 AI 消息:
 * 遇到 human 消息即停(不跨越对话回合边界)。这条边界很关键——换选题时会 submitText 追加一条
 * "写第 N 个选题" 的 human 消息,若不停在这条边界继续往前扫,会扫到**上一个选题**的 xhs_copy,
 * 把编辑器又填回上一个选题的旧正文(用户报告:新选题点进去是以前的东西)。停在 human 边界后:
 * 换选题→本轮还没产出 copy→返回 null→effect 的 `if(!next) return` 保持 chooseTopic 已清空的
 * 草稿(显示空+生成中),新 copy 流到后再填;精修(配标签/润色)同样只认本轮新 copy,旧稿由
 * 状态保留(effect 不清 null),行为不变。
 * 返回后"内容消失"的老问题(草稿那条 AI 后跟 tool/思考消息)仍解决:那些不是 human,不触发停。 */
export function latestDraftFromMessages(messages: Message[]): DraftSnapshot | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    // 回合边界:遇到用户消息即停,只认"最后一条用户消息之后"这一轮的成品,不跨回合回捞旧选题的稿。
    if (m.type === "human") break;
    if (m.type !== "ai") continue;
    const content = getContentString(m.content);
    if (!content) continue;
    const draft = parseAiDraft(content);
    if (draft) return draft;
  }
  return null;
}

function parseStructuredCopyDraft(text: string): DraftSnapshot | null {
  // xhs_copy(常规成品)与 xhs_imitation(仿写成品)结构同构(顶层 title/body 或 versions[0]),
  // 都当草稿源;取两类块里**最后出现**的那个(最新产出)。
  const fence = /```(?:xhs_copy|xhs_imitation)[ \t]*\r?\n?([\s\S]*?)```/g;
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
