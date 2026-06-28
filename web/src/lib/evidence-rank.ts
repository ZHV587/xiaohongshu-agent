// 依据排序信号的权威查找:从检索工具结果(stream 里的 tool 消息)按 resource_id 取
// score/why_selected/rank_signals。
//
// 为什么不从 xhs_topics/xhs_copy 的 evidence 代码块取:那是 LLM 写的精简块(刻意只含
// resource_id/title/summary/时效,防 LLM 编造排序分)。rank_signals 是后端 rank_evidence
// 在检索期算出的系统级产物,只存在于 semantic_search_resources / search_resources 的工具
// 结果里。把看板数据源接回工具结果 = 用系统权威产出展示,既不改精简契约、也不引入幻觉。

/** 检索工具白名单:其结果 results[*] 携带 rank_evidence 产出的 score/why_selected/rank_signals。 */
const RETRIEVAL_TOOLS = new Set(["semantic_search_resources", "search_resources"]);

export interface RankEnrichment {
  score?: number;
  why_selected?: string;
  rank_signals?: { relevance: number; freshness: number; performance: number };
}

/** 仅依赖 message 的最小形状,避免耦合 SDK 类型(也便于单测)。 */
interface ToolBearingMessage {
  type?: string;
  name?: string;
  content?: unknown;
}

function parseToolResult(content: unknown): { results?: unknown } | null {
  if (content == null) return null;
  let obj: unknown = content;
  if (typeof content === "string") {
    try {
      obj = JSON.parse(content);
    } catch {
      return null;
    }
  }
  return obj && typeof obj === "object" ? (obj as { results?: unknown }) : null;
}

/**
 * 在检索工具结果里按 resource_id 查 rank 信号。多轮检索命中同一 resource 时**取最近一次**
 * (rank 是 query 相关的相对量,最近的检索上下文最贴合用户当前在看的依据)。
 * 找不到(如纯图扩展依据 / 无检索轮次)返回空对象,看板优雅显示 N/A。
 */
export function lookupRankSignals(
  messages: ReadonlyArray<ToolBearingMessage> | undefined,
  resourceId: string | undefined,
): RankEnrichment {
  if (!messages || !resourceId) return {};
  let found: RankEnrichment = {};
  for (const message of messages) {
    if (message.type !== "tool" || !message.name || !RETRIEVAL_TOOLS.has(message.name)) {
      continue;
    }
    const data = parseToolResult(message.content);
    const results = data?.results;
    if (!Array.isArray(results)) continue;
    for (const item of results) {
      if (item && typeof item === "object" && (item as { resource_id?: unknown }).resource_id === resourceId) {
        const r = item as RankEnrichment & { resource_id: string };
        found = { score: r.score, why_selected: r.why_selected, rank_signals: r.rank_signals };
      }
    }
  }
  return found;
}
