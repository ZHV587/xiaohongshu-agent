// web/src/components/thread/messages/topic-cards.tsx
import { ChevronRight } from "lucide-react";
import { useThreadActions } from "@/lib/thread-actions";
import { MarkdownText } from "../markdown-text";
import type { TopicsSegment } from "@/lib/xhs-blocks";

export function TopicCards({ data }: { data: TopicsSegment["data"] }) {
  const { submitText } = useThreadActions();
  return (
    <div className="flex flex-col gap-2">
      {data.intro && (
        <div className="text-foreground">
          <MarkdownText>{data.intro}</MarkdownText>
        </div>
      )}
      <div className="flex flex-col gap-2">
        {data.topics.map((topic, i) => (
          <button
            key={i}
            type="button"
            onClick={() => submitText(`我选第 ${i + 1} 个选题："${topic}"。请帮我围绕这个选题写一篇完整的小红书爆款文案。`)}
            className="border-border hover:border-primary hover:bg-accent group flex items-center gap-3 rounded-xl border bg-card px-3.5 py-3 text-left transition-colors"
          >
            <span className="bg-accent text-primary flex size-6 flex-shrink-0 items-center justify-center rounded-md text-xs font-semibold">
              {i + 1}
            </span>
            <span className="text-foreground flex-1 text-sm">{topic}</span>
            <ChevronRight className="text-muted-foreground size-4 flex-shrink-0" />
          </button>
        ))}
      </div>
    </div>
  );
}
