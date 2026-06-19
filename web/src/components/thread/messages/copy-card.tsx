// web/src/components/thread/messages/copy-card.tsx
import { useState } from "react";
import { Copy, CopyCheck, Database } from "lucide-react";
import type { CopySegment } from "@/lib/xhs-blocks";

export function CopyCard({ data }: { data: CopySegment["data"] }) {
  const [copied, setCopied] = useState(false);

  const fullText = [
    data.title,
    "",
    data.body,
    "",
    data.tags.join(" "),
  ].join("\n").trim();

  const handleCopy = () => {
    navigator.clipboard.writeText(fullText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="border-border bg-card overflow-hidden rounded-2xl border">
      <div className="border-border flex items-center justify-between border-b bg-secondary/60 px-4 py-2.5">
        <span className="bg-accent text-primary rounded-md px-2 py-0.5 text-xs font-semibold">
          完成文案
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="text-primary hover:bg-accent flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs transition-colors"
        >
          {copied ? <CopyCheck className="size-3.5" /> : <Copy className="size-3.5" />}
          {copied ? "已复制" : "一键复制"}
        </button>
      </div>
      <div className="px-4 py-3.5">
        <div className="text-foreground mb-2 text-sm font-semibold">{data.title}</div>
        <div className="text-foreground/80 mb-3 text-sm leading-relaxed whitespace-pre-wrap">
          {data.body}
        </div>
        {data.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {data.tags.map((tag, i) => (
              <span key={i} className="text-xs text-sky-700/80">
                {tag}
              </span>
            ))}
          </div>
        )}
        {data.evidence.length > 0 && (
          <div className="border-border/70 mt-3 border-t pt-3">
            <div className="text-muted-foreground mb-2 flex items-center gap-1.5 text-xs font-medium">
              <Database className="size-3.5" />
              <span>创作依据</span>
            </div>
            <div className="space-y-2">
              {data.evidence.map((source) => (
                <div key={source.resource_id} className="text-xs leading-relaxed">
                  <div className="text-foreground/80 font-medium">{source.title}</div>
                  <div className="text-muted-foreground">{source.summary}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
