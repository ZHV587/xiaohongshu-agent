// web/src/components/thread/messages/topic-cards.tsx
import { ChevronRight, Database } from "lucide-react";
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
          <button
            key={i}
            type="button"
            onClick={() => submitText(`我选第 ${i + 1} 个选题："${topic}"。请帮我围绕这个选题写一篇完整的小红书爆款文案。`)}
            className="group/topic relative overflow-hidden flex items-center gap-4 rounded-2xl border border-border bg-card p-4 text-left transition-all duration-300 hover:border-primary/30 hover:shadow-[0_6px_20px_-8px_rgba(229,46,64,0.12)] active:scale-[0.995]"
          >
            {/* Left glowing accent line */}
            <div className="absolute left-0 top-0 bottom-0 w-[3px] bg-primary scale-y-0 group-hover/topic:scale-y-100 transition-transform origin-center duration-300 rounded-l-2xl" />
            
            {/* Index badge with scale and subtle rotate animation */}
            <span className="bg-muted text-muted-foreground group-hover/topic:bg-primary group-hover/topic:text-primary-foreground group-hover/topic:scale-110 group-hover/topic:rotate-6 flex size-7 flex-shrink-0 items-center justify-center rounded-full font-display text-xs font-semibold transition-all duration-300 shadow-2xs group-hover/topic:shadow-xs">
              {i + 1}
            </span>
            
            {/* Topic content text */}
            <span className="text-foreground/90 group-hover/topic:text-foreground flex-1 text-sm font-medium leading-relaxed transition-colors font-sans">
              {topic}
            </span>
            
            {/* Action Arrow with transition */}
            <ChevronRight className="text-muted-foreground/60 size-5 flex-shrink-0 transition-all duration-300 ease-out group-hover/topic:translate-x-1 group-hover/topic:text-primary" />
          </button>
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
