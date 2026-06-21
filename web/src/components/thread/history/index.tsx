// web/src/components/thread/history/index.tsx
import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { Thread } from "@langchain/langgraph-sdk";
import { useEffect, useState } from "react";

import { getContentString } from "../utils";
import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Activity, SquarePen, LogIn, LogOut, Sparkles, SlidersHorizontal } from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { getCurrentUser, loginWithFeishu, logout, type CurrentUser } from "@/lib/auth";

function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string | null) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const [, setView] = useQueryState("view");

  return (
    <div className="flex h-full w-full flex-col items-start gap-1 overflow-y-auto px-2 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
      {threads.map((t) => {
        // 优先用首条用户消息作标题;取不到(如失败/空会话)显示友好占位,
        // 不暴露 thread_id 这种 UUID(此前会显示成一长串乱码似的 ID)。
        let itemText = "未命名对话";
        if (
          typeof t.values === "object" &&
          t.values &&
          "messages" in t.values &&
          Array.isArray(t.values.messages) &&
          t.values.messages?.length > 0
        ) {
          const first = getContentString(t.values.messages[0].content).trim();
          if (first) itemText = first;
        }
        const active = t.thread_id === threadId;
        return (
          <button
            key={t.thread_id}
            type="button"
            onClick={(e) => {
              e.preventDefault();
              setView(null);
              if (t.thread_id === threadId) return;
              if (onThreadClick) {
                onThreadClick(t.thread_id);
              } else {
                setThreadId(t.thread_id);
              }
            }}
            className={cn(
              "w-full truncate rounded-lg px-3 py-2.5 text-left text-sm transition-all flex items-center justify-between",
              active
                ? "bg-oats text-coral border-l-2 border-coral font-semibold rounded-r-lg rounded-l-none pl-2"
                : "text-charcoal hover:bg-oats/50 rounded-lg",
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

function UserArea() {
  // 身份 JWT 在 httpOnly cookie 中,前端不可读;改向服务端 /api/me 询问当前飞书用户。
  const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => {
    let active = true;
    getCurrentUser().then((u) => {
      if (active) setUser(u);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!user) {
    return (
      <div className="border-border mt-auto border-t px-2 py-3 text-left">
        <Button
          variant="ghost"
          className="text-foreground/80 hover:bg-secondary w-full justify-start gap-2"
          onClick={() => loginWithFeishu(window.location.pathname + window.location.search)}
        >
          <LogIn className="size-4" />
          用飞书登录
        </Button>
      </div>
    );
  }

  const display = user.name || user.openId;
  return (
    <div className="border-oats-dark mt-auto flex items-center justify-between border-t p-4 text-left">
      <div className="flex items-center gap-2.5">
        <span className="bg-coral-light text-coral flex size-8 shrink-0 items-center justify-center rounded-lg font-bold text-xs">
          {display.slice(0, 1).toUpperCase()}
        </span>
        <span className="text-charcoal font-semibold flex-1 truncate text-xs max-w-[150px]" title={display}>
          {display}
        </span>
      </div>
      <button
        type="button"
        onClick={logout}
        title="退出登录"
        className="text-gray-400 hover:text-coral shrink-0 transition-colors cursor-pointer"
      >
        <LogOut className="size-4" />
      </button>
    </div>
  );
}

function SidebarBody({
  onLlmConfigOpen,
  onFeishuConfigOpen,
  onRuntimeFactsOpen,
  onThreadClick,
}: {
  onLlmConfigOpen: () => void;
  onFeishuConfigOpen: () => void;
  onRuntimeFactsOpen: () => void;
  onThreadClick?: (threadId: string | null) => void;
}) {
  const [, setThreadId] = useQueryState("threadId");
  const [, setView] = useQueryState("view");
  const [isAdmin, setIsAdmin] = useState(false);
  const { getThreads, threads, setThreads, threadsLoading, setThreadsLoading } =
    useThreads();

  useEffect(() => {
    fetch("/api/me")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setIsAdmin(Boolean(data?.user?.isAdmin)))
      .catch(() => setIsAdmin(false));
  }, []);

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
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-2">
          <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-lg text-sm">
            {BRAND.mark}
          </span>
          <span className="text-foreground text-[15px] font-semibold">{BRAND.name}</span>
        </div>
        <div className="flex items-center gap-1">
          {isAdmin && (
            <>
              <Button
                variant="ghost"
                size="icon"
                title="AI模型配置"
                onClick={onLlmConfigOpen}
                className="size-8 text-gray-400 hover:text-coral transition-colors"
              >
                <Sparkles className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title="飞书对接配置"
                onClick={onFeishuConfigOpen}
                className="size-8 text-gray-400 hover:text-coral transition-colors"
              >
                <SlidersHorizontal className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title="运行事实"
                onClick={onRuntimeFactsOpen}
                className="size-8 text-gray-400 hover:text-coral transition-colors"
              >
                <Activity className="size-4" />
              </Button>
            </>
          )}
        </div>
      </div>
      {/* 新对话 */}
      <div className="px-2 pb-2 text-left">
        <Button
          className="bg-primary text-primary-foreground hover:bg-primary/90 w-full justify-start gap-2"
          onClick={() => {
            setView(null);
            if (onThreadClick) {
              onThreadClick(null);
            } else {
              setThreadId(null);
            }
          }}
        >
          <SquarePen className="size-4" />
          新对话
        </Button>
      </div>
      <div className="text-muted-foreground px-4 pt-2 pb-1 text-xs tracking-wide text-left">最近</div>
      <div className="min-h-0 flex-1">
        {threadsLoading ? (
          <ThreadHistoryLoading />
        ) : (
          <ThreadList threads={threads} onThreadClick={onThreadClick} />
        )}
      </div>
      {/* 用户区:飞书登录态 */}
      <UserArea />
    </div>
  );
}

export default function ThreadHistory({
  onThreadClick,
}: {
  onThreadClick?: (threadId: string | null) => void;
}) {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );
  const [, setView] = useQueryState("view");

  return (
    <>
      <div className="hidden h-screen w-[300px] shrink-0 flex-col border-r lg:flex">
        <SidebarBody
          onLlmConfigOpen={() => setView("llm")}
          onFeishuConfigOpen={() => setView("feishu")}
          onRuntimeFactsOpen={() => setView("runtime-facts")}
          onThreadClick={onThreadClick}
        />
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
            <SidebarBody
              onLlmConfigOpen={() => setView("llm")}
              onFeishuConfigOpen={() => setView("feishu")}
              onRuntimeFactsOpen={() => setView("runtime-facts")}
              onThreadClick={onThreadClick}
            />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
