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

export interface MessageGroup {
  id: string;
  type: "human" | "assistant";
  humanMessage?: Message;
  aiMessage?: Message;
  toolCalls?: { name: string; args?: any; result?: any; id?: string }[];
  isThinkingOnly?: boolean;
}
