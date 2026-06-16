// web/src/components/thread/history/index.tsx
import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { Thread } from "@langchain/langgraph-sdk";
import { useEffect } from "react";

import { getContentString } from "../utils";
import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { SquarePen } from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";

function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");

  return (
    <div className="flex h-full w-full flex-col items-start gap-1 overflow-y-auto px-2 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
      {threads.map((t) => {
        let itemText = t.thread_id;
        if (
          typeof t.values === "object" &&
          t.values &&
          "messages" in t.values &&
          Array.isArray(t.values.messages) &&
          t.values.messages?.length > 0
        ) {
          itemText = getContentString(t.values.messages[0].content);
        }
        const active = t.thread_id === threadId;
        return (
          <button
            key={t.thread_id}
            type="button"
            onClick={(e) => {
              e.preventDefault();
              onThreadClick?.(t.thread_id);
              if (t.thread_id === threadId) return;
              setThreadId(t.thread_id);
            }}
            className={cn(
              "w-full truncate rounded-lg px-3 py-2 text-left text-sm transition-colors",
              active
                ? "bg-accent text-accent-foreground font-medium"
                : "text-foreground/80 hover:bg-secondary",
            )}
          >
            {itemText}
          </button>
        );
      })}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex w-full flex-col gap-1 px-2">
      {Array.from({ length: 12 }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

function SidebarBody() {
  const [, setThreadId] = useQueryState("threadId");
  const { getThreads, threads, setThreads, threadsLoading, setThreadsLoading } =
    useThreads();

  useEffect(() => {
    if (typeof window === "undefined") return;
    setThreadsLoading(true);
    getThreads()
      .then(setThreads)
      .catch(console.error)
      .finally(() => setThreadsLoading(false));
  }, []);

  return (
    <div className="flex h-full w-full flex-col">
      {/* 品牌区 */}
      <div className="flex items-center gap-2 px-4 pt-4 pb-3">
        <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-lg text-sm">
          {BRAND.mark}
        </span>
        <span className="text-foreground text-[15px] font-semibold">{BRAND.name}</span>
      </div>
      {/* 新对话 */}
      <div className="px-2 pb-2">
        <Button
          className="bg-primary text-primary-foreground hover:bg-primary/90 w-full justify-start gap-2"
          onClick={() => setThreadId(null)}
        >
          <SquarePen className="size-4" />
          新对话
        </Button>
      </div>
      <div className="text-muted-foreground px-4 pt-2 pb-1 text-xs tracking-wide">最近</div>
      <div className="min-h-0 flex-1">
        {threadsLoading ? <ThreadHistoryLoading /> : <ThreadList threads={threads} />}
      </div>
      {/* 用户区（本地 mock 占位） */}
      <div className="border-border mt-auto flex items-center gap-2.5 border-t px-4 py-3">
        <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-full text-xs">
          我
        </span>
        <span className="text-muted-foreground text-xs">团队成员</span>
      </div>
    </div>
  );
}

export default function ThreadHistory() {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );

  return (
    <>
      <div className="hidden h-screen w-[300px] shrink-0 flex-col border-r lg:flex">
        <SidebarBody />
      </div>
      <div className="lg:hidden">
        <Sheet
          open={!!chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (isLargeScreen) return;
            setChatHistoryOpen(open);
          }}
        >
          <SheetContent side="left" className="flex w-[300px] p-0 lg:hidden">
            <SheetHeader className="sr-only">
              <SheetTitle>会话历史</SheetTitle>
            </SheetHeader>
            <SidebarBody />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
