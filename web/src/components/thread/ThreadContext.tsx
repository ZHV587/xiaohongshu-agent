import { createContext, useContext, RefObject } from "react";
import { Message } from "@langchain/langgraph-sdk";
import { SourceEvidence } from "./types";

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

  // Workstation states
  rightTab: "mock" | "feishu" | "evidence";
  setRightTab: (tab: "mock" | "feishu" | "evidence") => void;
  selectedEvidence: SourceEvidence | null;
  setSelectedEvidence: (ev: SourceEvidence | null) => void;
  viewMode: "detail" | "feed";
  setViewMode: (mode: "detail" | "feed") => void;
  isEditingText: boolean;
  setIsEditingText: (editing: boolean) => void;
  draftTitle: string;
  setDraftTitle: (title: string) => void;
  draftContent: string;
  setDraftContent: (content: string) => void;
  carouselIndex: number;
  setCarouselIndex: (i: number | ((prev: number) => number)) => void;
  carouselImages: string[];
  feishuChats: any[];
  setFeishuChats: (chats: any[]) => void;
  selectedChatId: string;
  setSelectedChatId: (id: string) => void;
  isFetchingChats: boolean;
  setIsFetchingChats: (fetching: boolean) => void;
  isSendingNotification: boolean;
  setIsSendingNotification: (sending: boolean) => void;
  isFeishuActionPending: boolean;
  setIsFeishuActionPending: (pending: boolean) => void;
  syncStepsVisible: boolean;
  setSyncStepsVisible: (visible: boolean) => void;
  syncStep: number;
  setSyncStep: (step: number) => void;
  isSyncing: boolean;
  setIsSyncing: (syncing: boolean) => void;
  isFlying: boolean;
  setIsFlying: (flying: boolean) => void;
  showCommandPalette: boolean;
  setShowCommandPalette: (show: boolean) => void;
  cmdSearch: string;
  setCmdSearch: (search: string) => void;
  bitableUrl: string | null;
  wikiUrl: string | null;

  // Actions
  handleSyncToFeishu: () => void;
  handleSendNotification: () => void;
  handleInsertEmoji: (emoji: string) => void;
  handleAppendTag: (tag: string) => void;
  handleEditBodyPaste: (e: any) => void;
  textareaRef: RefObject<HTMLTextAreaElement | null>;
}

export const ThreadContext = createContext<ThreadContextProps | null>(null);

export function useThread() {
  const ctx = useContext(ThreadContext);
  if (!ctx) {
    throw new Error("useThread must be used within a ThreadProvider");
  }
  return ctx;
}
