import { Message } from "@langchain/langgraph-sdk";

export interface SourceEvidence {
  resource_id: string;
  title: string;
  summary: string;
  source_updated_at?: string;
  indexed_at?: string;
  score?: number;
  why_selected?: string;
  rank_signals?: {
    relevance: number;
    freshness: number;
    performance: number;
  };
}

export type SidebarView = "mock" | "feishu" | "evidence" | "facts" | null;

/** 工具调用条目(思考链 / 富卡片共用) */
export interface ToolEntry {
  id?: string;
  name: string;
  args?: any;
  result?: any;
}

/**
 * 一个 assistant 回合内的有序渲染块。
 * 关键:每条 ai 文本消息独立成块,绝不互相覆盖(修复"内容消失");
 * 工具调用聚合成 tools 块并按出现顺序与文本交错(修复"思考链不完整")。
 */
export type AssistantBlock =
  | { kind: "tools"; tools: ToolEntry[] }
  | { kind: "ai"; message: Message };

export interface MessageGroup {
  id: string;
  type: "human" | "assistant";
  humanMessage?: Message;
  /** assistant 回合的有序渲染块(human 组不用) */
  blocks?: AssistantBlock[];
  isThinkingOnly?: boolean;
}
