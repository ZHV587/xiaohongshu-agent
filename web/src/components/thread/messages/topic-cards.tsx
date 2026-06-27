// web/src/components/thread/messages/topic-cards.tsx
import { Database } from "lucide-react";
import { useThreadActions } from "@/lib/thread-actions-context";
import { MarkdownText } from "../markdown-text";
import type { TopicsSegment } from "@/lib/xhs-blocks";
import { EvidenceTime } from "./evidence-time";
import { useThread } from "../ThreadContext";
import { cn } from "@/lib/utils";

export function TopicCards({ data }: { data: TopicsSegment["data"] }) {
  const { submitText } = useThreadActions();

  const threadCtx = useThread();

  return (
    <div className="flex flex-col gap-3.5 my-2">
      {data.intro && (
        <div className="text-foreground/90 text-sm font-medium pl-1 mb-1 leading-relaxed">
          <MarkdownText>{data.intro}</MarkdownText>
        </div>
      )}
      <div className="flex flex-col gap-3">
        {data.topics.map((topic, i) => (
          <div
            key={i}
            className="group/topic relative overflow-hidden flex items-center justify-between gap-4 rounded-2xl border border-border bg-card p-4 hover:border-coral/40 hover:shadow-[0_8px_30px_rgba(229,46,64,0.16),0_0_15px_rgba(229,46,64,0.08)] transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
          >
            {/* Left glowing accent line */}
            <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-coral scale-y-0 group-hover/topic:scale-y-100 transition-transform origin-center duration-300 rounded-l-2xl" />
            
            {/* Main content area: clicks trigger copywriting workflow */}
            <div
              onClick={() =>
                submitText(
                  `我选第 ${i + 1} 个选题："${topic}"。请帮我围绕这个选题写一篇完整的小红书爆款文案。`,
                  { selected_topic: { topic, evidence: data.evidence } },
                )
              }
              className="flex items-center gap-4 flex-1 cursor-pointer"
            >
              <span className="bg-muted text-muted-foreground group-hover/topic:bg-coral group-hover/topic:text-white group-hover/topic:scale-110 group-hover/topic:rotate-6 flex size-7 flex-shrink-0 items-center justify-center rounded-full font-display text-xs font-semibold transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] shadow-2xs">
                {i + 1}
              </span>
              <span className="text-foreground/90 flex-1 text-sm font-medium leading-relaxed font-sans transition-colors">
                {topic}
              </span>
            </div>
            
            {/* Save button: directly saves the topic card to DB/Feishu */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                submitText(`保存第 ${i + 1} 个选题："${topic}"。`, { selected_topic: { topic, evidence: data.evidence } });
              }}
              className="z-10 flex-shrink-0 px-2.5 py-1 text-[11px] font-semibold text-coral border border-coral/20 rounded-full bg-coral/5 hover:bg-coral hover:text-white transition-all duration-300 active:scale-95 cursor-pointer"
            >
              保存
            </button>
          </div>
        ))}
      </div>
      {data.evidence.length > 0 && (
        <div className="border-border/70 mt-0.5 border-t px-1 pt-3">
          <div className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs font-medium">
            <Database className="size-3.5" />
            <span>创作依据 (点击可查看分析)</span>
          </div>
          <div className="space-y-2">
            {data.evidence.map((source) => (
              <div
                key={source.resource_id}
                onClick={() => {
                  if (threadCtx) {
                    threadCtx.setSelectedEvidence(source);
                    threadCtx.setRightTab("evidence");
                  }
                }}
                className={cn(
                  "text-xs leading-relaxed p-2.5 rounded-xl border border-coral-light/20 bg-oats-light/20 cursor-pointer hover:border-coral hover:bg-white hover:shadow-2xs transition-all",
                  threadCtx?.selectedEvidence?.resource_id === source.resource_id && "border-coral bg-white shadow-2xs"
                )}
              >
                <div className="text-foreground/80 font-semibold">{source.title}</div>
                <div className="text-muted-foreground line-clamp-2 mt-0.5">{source.summary}</div>
                <div className="mt-1">
                  <EvidenceTime sourceUpdatedAt={source.source_updated_at} indexedAt={source.indexed_at} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
