// web/src/components/thread/history/index.tsx
import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/thread-context";
import { Thread } from "@langchain/langgraph-sdk";
import { useEffect, useRef, useState } from "react";

import { getContentString } from "../utils";
import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Activity,
  SquarePen,
  LogIn,
  LogOut,
  Sparkles,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";
import { toast } from "sonner";
import { BRAND } from "@/lib/brand";
import {
  getCurrentUser,
  loginWithFeishu,
  logout,
  type CurrentUser,
} from "@/lib/auth";

function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string | null) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const [, setView] = useQueryState("view");
  const { deleteThread } = useThreads();
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const confirmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearConfirmTimer = () => {
    if (confirmTimer.current) {
      clearTimeout(confirmTimer.current);
      confirmTimer.current = null;
    }
  };

  useEffect(() => () => clearConfirmTimer(), []);

  const switchTo = (id: string | null) => {
    if (id === null) {
      void (onThreadClick ? onThreadClick(null) : setThreadId(null));
    } else if (onThreadClick) {
      onThreadClick(id);
    } else {
      setThreadId(id);
    }
  };

  const startConfirm = (id: string) => {
    clearConfirmTimer();
    setConfirmingId(id);
    confirmTimer.current = setTimeout(() => setConfirmingId(null), 3000);
  };

  const cancelConfirm = () => {
    clearConfirmTimer();
    setConfirmingId(null);
  };

  const confirmDelete = async (id: string) => {
    clearConfirmTimer();
    setIsDeleting(true);
    try {
      await deleteThread(id);
      if (id === threadId) switchTo(null);
      setConfirmingId(null);
    } catch {
      toast.error("删除失败,请重试");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="[&::-webkit-scrollbar-thumb]:bg-border flex h-full w-full flex-col items-start gap-1 overflow-y-auto px-2 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full">
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
        const confirming = t.thread_id === confirmingId;

        if (confirming) {
          return (
            <div
              key={t.thread_id}
              className="bg-oats/60 flex min-h-11 w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm"
            >
              <span className="text-charcoal truncate">确认删除?</span>
              <div className="flex shrink-0 items-center gap-1">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 px-2 text-xs"
                  disabled={isDeleting}
                  onClick={(e) => {
                    e.stopPropagation();
                    cancelConfirm();
                  }}
                >
                  取消
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-coral hover:text-coral h-7 px-2 text-xs"
                  disabled={isDeleting}
                  onClick={(e) => {
                    e.stopPropagation();
                    void confirmDelete(t.thread_id);
                  }}
                >
                  删除
                </Button>
              </div>
            </div>
          );
        }

        return (
          <div
            key={t.thread_id}
            className={cn(
              "group flex min-h-11 w-full items-center rounded-lg transition-all",
              active
                ? "bg-oats text-coral border-coral rounded-l-none rounded-r-lg border-l-2"
                : "text-charcoal hover:bg-oats/50",
            )}
          >
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                setView(null);
                cancelConfirm();
                if (t.thread_id === threadId) return;
                switchTo(t.thread_id);
              }}
              className={cn(
                "min-w-0 flex-1 truncate px-3 py-2.5 text-left text-sm",
                active ? "pl-2 font-semibold" : "",
              )}
            >
              {itemText}
            </button>
            <button
              type="button"
              aria-label="删除会话"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                startConfirm(t.thread_id);
              }}
              className="text-charcoal-light hover:text-coral mr-2 flex size-7 shrink-0 items-center justify-center rounded transition-opacity opacity-0 group-hover:opacity-100"
            >
              <Trash2 className="size-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex w-full flex-col gap-1 px-2">
      {Array.from({ length: 12 }).map((_, i) => (
        <Skeleton
          key={i}
          className="h-9 w-full"
        />
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
          className="text-foreground/80 hover:bg-secondary min-h-11 w-full justify-start gap-2"
          onClick={() =>
            loginWithFeishu(window.location.pathname + window.location.search)
          }
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
        <span className="bg-coral-light text-coral flex size-8 shrink-0 items-center justify-center rounded-lg text-xs font-bold">
          {display.slice(0, 1).toUpperCase()}
        </span>
        <span
          className="text-charcoal max-w-[150px] flex-1 truncate text-xs font-semibold"
          title={display}
        >
          {display}
        </span>
      </div>
      <button
        type="button"
        onClick={logout}
        title="退出登录"
        className="hover:text-coral flex min-h-11 min-w-11 shrink-0 cursor-pointer items-center justify-center rounded-lg text-gray-400 transition-colors"
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
  }, [getThreads, setThreads, setThreadsLoading]);

  return (
    <nav
      aria-label="会话历史"
      className="flex h-full w-full flex-col"
    >
      {/* 品牌区 */}
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-2">
          <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-lg text-sm">
            {BRAND.mark}
          </span>
          <span className="text-foreground text-[15px] font-semibold">
            {BRAND.name}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {isAdmin && (
            <>
              <Button
                variant="ghost"
                size="icon"
                title="AI模型配置"
                onClick={onLlmConfigOpen}
                className="hover:text-coral min-h-11 min-w-11 text-gray-400 transition-colors"
              >
                <Sparkles className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title="飞书对接配置"
                onClick={onFeishuConfigOpen}
                className="hover:text-coral min-h-11 min-w-11 text-gray-400 transition-colors"
              >
                <SlidersHorizontal className="size-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                title="运行事实"
                onClick={onRuntimeFactsOpen}
                className="hover:text-coral min-h-11 min-w-11 text-gray-400 transition-colors"
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
          className="bg-primary text-primary-foreground hover:bg-primary/90 min-h-11 w-full justify-start gap-2"
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
      <div className="text-muted-foreground px-4 pt-2 pb-1 text-left text-xs tracking-wide">
        最近
      </div>
      <div className="min-h-0 flex-1">
        {threadsLoading ? (
          <ThreadHistoryLoading />
        ) : (
          <ThreadList
            threads={threads}
            onThreadClick={onThreadClick}
          />
        )}
      </div>
      {/* 用户区:飞书登录态 */}
      <UserArea />
    </nav>
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
          <SheetContent
            side="left"
            className="flex w-[300px] p-0 lg:hidden"
          >
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
