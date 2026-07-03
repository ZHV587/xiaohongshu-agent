import { createContext, useContext, RefObject } from "react";
import { Message } from "@langchain/langgraph-sdk";

export interface ThreadContextProps {
  threadId: string | null;
  setThreadId: (id: string | null) => void;
  chatHistoryOpen: boolean;
  setChatHistoryOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  view: string | null;
  setView: (v: string | null) => void;
  input: string;
  setInput: (v: string) => void;
  contentBlocks: any[];
  setContentBlocks: (v: any[] | ((prev: any[]) => any[])) => void;
  isLoading: boolean;
  isStreaming: boolean;
  error: unknown;
  setFirstTokenReceived: (v: boolean) => void;
  submitText: (text: string) => void;
  handleSubmit: (e: any) => void;
  handleRegenerate: (parentCheckpoint: any) => void;
  handleFileUpload: (e: any) => void;
  dropRef: RefObject<HTMLDivElement | null>;
  removeBlock: (idx: number) => void;
  dragOver: boolean;
  handlePaste: (e: any) => void;
  messages: Message[];

  // 草稿工作台状态
  draftTitle: string;
  setDraftTitle: (title: string) => void;
  draftContent: string;
  setDraftContent: (content: string) => void;
  isDirty: boolean;
  isSyncing: boolean;
  setIsSyncing: (syncing: boolean) => void;
  lastSavedTitle: string;
  lastSavedContent: string;

  // Actions
  handleExecuteCommand: (cmd: string) => void;
  handleSyncToFeishu: () => void;
}

export const ThreadContext = createContext<ThreadContextProps | null>(null);

export function useThread() {
  const ctx = useContext(ThreadContext);
  if (!ctx) {
    throw new Error("useThread must be used within a ThreadProvider");
  }
  return ctx;
}

/** 非抛出版:provider 不存在时返回 null(供 DEV 预览路由等无 ThreadProvider 的场景优雅降级)。 */
export function useThreadOptional(): ThreadContextProps | null {
  return useContext(ThreadContext);
}
