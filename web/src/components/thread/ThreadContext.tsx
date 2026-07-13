import { createContext, useContext, RefObject } from "react";
import { Message } from "@langchain/langgraph-sdk";

// HITL 中断契约,对齐后端 langchain HumanInTheLoopMiddleware(agent.py interrupt_on):
// 中断值为 HITLRequest(action_requests + review_configs);恢复提交 {decisions:[...]},
// 每个 action_request 一条 decision,按序对应。
export interface HITLActionRequest {
  action: string;
  args: Record<string, unknown>;
}
export interface HITLReviewConfig {
  action_name: string;
  allowed_decisions: ("approve" | "edit" | "reject" | "respond")[];
  args_schema?: Record<string, unknown>;
}
export interface HITLRequest {
  action_requests: HITLActionRequest[];
  review_configs: HITLReviewConfig[];
}
export type HITLDecision =
  | { type: "approve" }
  | { type: "reject"; message?: string }
  | { type: "respond"; message: string }
  | { type: "edit"; edited_action: { action: string; args: Record<string, unknown> } };

export interface UserSkillInvocation {
  skillId: string;
  versionId: string;
  mode: "execute" | "test";
}

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
  // stateUpdate:可选,把结构化数据(如采纳的 selected_notes)经官方 state 通道直传 graph,不经 LLM。
  submitText: (text: string, stateUpdate?: Record<string, unknown>) => void;
  executeUserSkill: (text: string, invocation: UserSkillInvocation) => void;
  handleSubmit: (e: any) => void;
  handleRegenerate: (parentCheckpoint: any) => void;
  /** 停止当前正在进行的生成(SDK stream.stop)。仅在 isLoading 时有效。 */
  stopGeneration: () => void;
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

  // HITL 工具审批中断:有待审批时 interrupt 非 null,respondToInterrupt 提交决定并恢复执行。
  interrupt: HITLRequest | null;
  respondToInterrupt: (decisions: HITLDecision[]) => void;

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
