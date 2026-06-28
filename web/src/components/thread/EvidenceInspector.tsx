import { useThread } from "./ThreadContext";
import { useStreamContext } from "@/providers/stream-context";
import { lookupRankSignals } from "@/lib/evidence-rank";
import { Database, FileText, Sparkles, TrendingUp, X } from "lucide-react";
import { EvidenceTime } from "./messages/evidence-time";

export function EvidenceInspector() {
  const { selectedEvidence, setSelectedEvidence, setRightTab } = useThread();
  const stream = useStreamContext();

  if (!selectedEvidence) {
    return (
      <div className="flex flex-col items-center justify-center text-center p-8 h-full bg-oats/10 text-gray-400 select-none">
        <Database className="size-10 mb-3 text-coral/30" />
        <p className="text-xs font-medium">请在左侧对话卡片中点击任意一个“创作依据”</p>
        <p className="text-[10px] text-gray-400 mt-1">查看该来源的深度算法相关性与数据分析</p>
      </div>
    );
  }

  const { title, summary, source_updated_at, indexed_at } = selectedEvidence;
  // rank 信号的权威源是检索工具结果(非 LLM 写的精简 evidence 块)。优先用 evidence 自带值
  // (未来若契约扩展则直接生效),否则按 resource_id 从 stream 的检索工具结果补全。
  const enrichment = lookupRankSignals(stream.messages, selectedEvidence.resource_id);
  const score = selectedEvidence.score ?? enrichment.score;
  const why_selected = selectedEvidence.why_selected ?? enrichment.why_selected;
  const rank_signals = selectedEvidence.rank_signals ?? enrichment.rank_signals;

  return (
    <div className="flex flex-col h-full bg-oats/10 text-charcoal">
      {/* Page Header */}
      <div className="p-4 bg-white border-b border-coral-light/60 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <Database className="size-4.5 text-coral" />
          <span className="text-xs font-bold">依据相关度分析</span>
        </div>
        <button
          onClick={() => {
            setSelectedEvidence(null);
            setRightTab("mock");
          }}
          className="text-gray-400 hover:text-coral transition-colors p-1"
        >
          <X className="size-4" />
        </button>
      </div>

      {/* Main Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 custom-scrollbar">
        {/* Title & Summary */}
        <div className="bg-white border border-coral-light/60 rounded-xl p-3.5 shadow-xs space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-bold text-charcoal">
            <FileText className="size-3.5 text-coral/80" />
            <span>{title}</span>
          </div>
          <p className="text-[10px] text-charcoal-light leading-relaxed">{summary}</p>
        </div>

        {/* Selected Explanation Callout */}
        {why_selected && (
          <div className="bg-coral-light/30 border border-coral/20 rounded-xl p-3.5 shadow-xs space-y-1">
            <div className="flex items-center gap-1.5 text-[10px] font-bold text-coral">
              <Sparkles className="size-3.5" />
              <span>推荐理由</span>
            </div>
            <p className="text-[10px] text-charcoal leading-relaxed">{why_selected}</p>
          </div>
        )}

        {/* Scores & Weights */}
        <div className="bg-white border border-coral-light/60 rounded-xl p-4 shadow-xs space-y-4">
          <div className="flex justify-between items-center border-b pb-2">
            <span className="text-xs font-bold">综合排序得分</span>
            <span className="text-sm font-black text-coral font-mono">{score !== undefined ? score.toFixed(4) : "N/A"}</span>
          </div>

          <div className="space-y-3.5 text-[10px]">
            {/* Relevance */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-gray-500">
                <span>相关度 (Relevance Score)</span>
                <span className="font-semibold text-charcoal font-mono">
                  {rank_signals?.relevance !== undefined ? `${(rank_signals.relevance * 100).toFixed(1)}%` : "N/A"}
                </span>
              </div>
              <div className="h-1.5 bg-oats rounded-full overflow-hidden">
                <div
                  className="h-full bg-coral transition-all duration-500"
                  style={{ width: `${(rank_signals?.relevance ?? 0) * 100}%` }}
                />
              </div>
            </div>

            {/* Freshness */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-gray-500">
                <span>时效性 (Freshness Decay)</span>
                <span className="font-semibold text-charcoal font-mono">
                  {rank_signals?.freshness !== undefined ? `${(rank_signals.freshness * 100).toFixed(1)}%` : "N/A"}
                </span>
              </div>
              <div className="h-1.5 bg-oats rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 transition-all duration-500"
                  style={{ width: `${(rank_signals?.freshness ?? 0) * 100}%` }}
                />
              </div>
            </div>

            {/* Performance */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-gray-500 flex-wrap gap-x-1">
                <span>爆款历史表现 (Engagement tanh)</span>
                <span className="font-semibold text-charcoal font-mono">
                  {rank_signals?.performance !== undefined ? `${(rank_signals.performance * 100).toFixed(1)}%` : "N/A"}
                </span>
              </div>
              <div className="h-1.5 bg-oats rounded-full overflow-hidden">
                <div
                  className="h-full bg-amber-500 transition-all duration-500"
                  style={{ width: `${(rank_signals?.performance ?? 0) * 100}%` }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Timestamps */}
        <div className="bg-white border border-coral-light/60 rounded-xl p-3.5 shadow-xs text-[10px] space-y-2">
          <div className="flex items-center gap-1.5 text-gray-500 font-bold border-b pb-1.5">
            <TrendingUp className="size-3.5" />
            <span>时效跟踪</span>
          </div>
          <div className="space-y-1">
            <EvidenceTime sourceUpdatedAt={source_updated_at} indexedAt={indexed_at} />
          </div>
        </div>
      </div>
    </div>
  );
}
