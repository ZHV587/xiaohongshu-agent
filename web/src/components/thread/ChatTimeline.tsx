import { ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useStreamContext } from "@/providers/stream-context";
import { Button } from "../ui/button";
import { Message } from "@langchain/langgraph-sdk";
import { AssistantMessage } from "./messages/ai";
import { HumanMessage } from "./messages/human";
import { TooltipIconButton } from "./tooltip-icon-button";
import {
  ArrowDown,
  LoaderCircle,
  PanelRightOpen,
  PanelRightClose,
  SquarePen,
} from "lucide-react";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { BRAND } from "@/lib/brand";
import { useThread } from "./ThreadContext";
import { MessageGroup } from "./types";
import { ComposerPanel } from "./ComposerPanel";

const DO_NOT_RENDER_ID_PREFIX = "do-not-render-";

function groupMessages(messages: Message[]): MessageGroup[] {
  const groups: MessageGroup[] = [];
  let currentGroup: MessageGroup | null = null;

  for (const msg of messages) {
    if (msg.id?.startsWith(DO_NOT_RENDER_ID_PREFIX)) {
      continue;
    }

    if (msg.type === "human") {
      if (currentGroup) {
        groups.push(currentGroup);
      }
      currentGroup = {
        id: msg.id || Math.random().toString(),
        type: "human",
        humanMessage: msg,
      };
    } else if (msg.type === "ai") {
      const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
      const textContent = typeof msg.content === "string" ? msg.content : "";

      if (hasToolCalls) {
        if (!currentGroup || currentGroup.type !== "assistant") {
          if (currentGroup) {
            groups.push(currentGroup);
          }
          currentGroup = {
            id: msg.id || Math.random().toString(),
            type: "assistant",
            toolCalls: [],
          };
        }
        currentGroup.toolCalls = currentGroup.toolCalls || [];
        msg.tool_calls!.forEach((tc) => {
          if (!currentGroup!.toolCalls!.some((item) => item.id === tc.id)) {
            currentGroup!.toolCalls!.push({
              id: tc.id,
              name: tc.name,
              args: tc.args,
            });
          }
        });
      }

      if (textContent.trim().length > 0 || !hasToolCalls) {
        if (!currentGroup || currentGroup.type !== "assistant") {
          if (currentGroup) {
            groups.push(currentGroup);
          }
          currentGroup = {
            id: msg.id || Math.random().toString(),
            type: "assistant",
          };
        }
        currentGroup.aiMessage = msg;
        currentGroup.isThinkingOnly = false;
      }
    } else if (msg.type === "tool") {
      if (!currentGroup || currentGroup.type !== "assistant") {
        if (currentGroup) {
          groups.push(currentGroup);
        }
        currentGroup = {
          id: msg.id || Math.random().toString(),
          type: "assistant",
          toolCalls: [],
        };
      }
      currentGroup.toolCalls = currentGroup.toolCalls || [];
      const toolCallId = msg.tool_call_id;
      const existingCall = currentGroup.toolCalls.find((tc) => tc.id === toolCallId);
      if (existingCall) {
        existingCall.result = msg.content;
      } else {
        currentGroup.toolCalls.push({
          id: toolCallId,
          name: msg.name || "unknown",
          result: msg.content,
        });
      }
    }
  }

  if (currentGroup) {
    if (currentGroup.type === "assistant" && !currentGroup.aiMessage) {
      currentGroup.isThinkingOnly = true;
    }
    groups.push(currentGroup);
  }

  return groups;
}

function StickyToBottomContent(props: {
  content: ReactNode;
  footer?: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  const context = useStickToBottomContext();
  return (
    <div
      ref={context.scrollRef}
      style={{ width: "100%", height: "100%" }}
      className={props.className}
    >
      <div
        ref={context.contentRef}
        className={props.contentClassName}
      >
        {props.content}
      </div>

      {props.footer}
    </div>
  );
}

function ScrollToBottom(props: { className?: string }) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();

  if (isAtBottom) return null;
  return (
    <Button
      variant="outline"
      className={props.className}
      onClick={() => scrollToBottom()}
    >
      <ArrowDown className="h-4 w-4" />
      <span>回到底部</span>
    </Button>
  );
}

export function ChatTimeline() {
  const stream = useStreamContext();
  const {
    threadId,
    setThreadId,
    chatHistoryOpen,
    setChatHistoryOpen,
    submitText,
    handleRegenerate,
    isLoading,
    isStreaming,
  } = useThread();

  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const messages = stream.messages;
  const chatStarted = !!threadId || !!messages.length;
  const hasNoAIOrToolMessages = !messages.find(
    (m) => m.type === "ai" || m.type === "tool",
  );

  return (
    <div className="relative flex min-w-0 flex-1 flex-col overflow-hidden h-full">
      {chatStarted && (
        <div className="relative z-10 flex items-center justify-between gap-3 p-2 bg-white/70 backdrop-blur-xs border-b border-coral-light/20 select-none">
          <div className="relative flex items-center justify-start gap-2">
            <div className="absolute left-0 z-10">
              {(!chatHistoryOpen || !isLargeScreen) && (
                <Button
                  className="hover:bg-gray-100"
                  variant="ghost"
                  onClick={() => setChatHistoryOpen((p: boolean) => !p)}
                >
                  {chatHistoryOpen ? (
                    <PanelRightOpen className="size-5" />
                  ) : (
                    <PanelRightClose className="size-5" />
                  )}
                </Button>
              )}
            </div>
            <motion.button
              type="button"
              className="flex cursor-pointer items-center gap-2"
              onClick={() => setThreadId(null)}
              animate={{ marginLeft: !chatHistoryOpen ? 48 : 0 }}
              transition={{ type: "spring", stiffness: 300, damping: 30 }}
            >
              <span className="bg-primary text-primary-foreground flex size-8 items-center justify-center rounded-xl font-display shadow-xs text-base">
                {BRAND.mark}
              </span>
              <span className="text-base font-bold tracking-tight text-charcoal font-display">
                {BRAND.name}
              </span>
            </motion.button>
          </div>

          <div className="flex items-center gap-4">
            <TooltipIconButton
              size="lg"
              className="p-4 hover:text-coral transition-colors"
              tooltip="新对话"
              variant="ghost"
              onClick={() => setThreadId(null)}
            >
              <SquarePen className="size-5" />
            </TooltipIconButton>
          </div>
        </div>
      )}

      <StickToBottom className="relative flex-1 overflow-hidden">
        <StickyToBottomContent
          className={cn(
            "absolute inset-0 overflow-y-scroll px-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-coral/20 [&::-webkit-scrollbar-track]:bg-transparent",
            !chatStarted && "mt-[25vh] flex flex-col items-stretch",
            chatStarted && "grid grid-rows-[1fr_auto]"
          )}
          contentClassName="pt-8 pb-16 max-w-3xl mx-auto flex flex-col gap-4 w-full"
          content={
            <>
              {groupMessages(messages).map((group, index, arr) => {
                const isLast = index === arr.length - 1;
                return group.type === "human" ? (
                  <HumanMessage
                    key={group.id}
                    message={group.humanMessage!}
                    isLoading={isLoading && isLast}
                  />
                ) : (
                  <AssistantMessage
                    key={group.id}
                    message={group.aiMessage}
                    isLoading={isLoading}
                    handleRegenerate={handleRegenerate}
                    precedingTools={group.toolCalls}
                    isThinkingOnly={group.isThinkingOnly}
                  />
                );
              })}
              {hasNoAIOrToolMessages && !!stream.interrupt && (
                <AssistantMessage
                  key="interrupt-msg"
                  message={undefined}
                  isLoading={isLoading}
                  handleRegenerate={handleRegenerate}
                />
              )}
              {isLoading && !isStreaming && (
                (!messages.length || messages[messages.length - 1].type === "human") && (
                  <div className="mr-auto flex flex-col gap-2 py-2 w-full max-w-[460px]">
                    <div className="bg-white border border-coral-light/60 p-3.5 rounded-2xl shadow-xs flex items-center gap-2.5">
                      <LoaderCircle className="size-4 animate-spin text-coral" />
                      <span className="text-xs text-charcoal-light">正在启动智能分析...</span>
                    </div>
                  </div>
                )
              )}
            </>
          }
          footer={
            <div className="sticky bottom-0 flex flex-col items-center gap-8 bg-transparent w-full">
              {!chatStarted && (
                <div className="flex flex-col items-center gap-3">
                  <span className="bg-primary text-primary-foreground flex size-14 items-center justify-center rounded-2xl text-3xl shadow-md">
                    {BRAND.mark}
                  </span>
                  <h1 className="text-2xl font-bold tracking-tight text-charcoal font-display">{BRAND.name}</h1>
                  <p className="text-gray-500 text-sm">{BRAND.slogan}</p>
                  <div className="mt-2 flex max-w-xl flex-wrap justify-center gap-2">
                    {BRAND.examples.map((ex) => (
                      <button
                        key={ex}
                        type="button"
                        onClick={() => submitText(ex)}
                        className="border-coral-light/60 text-charcoal/70 hover:border-coral hover:bg-coral-light rounded-full border bg-white px-3.5 py-1.5 text-xs transition-colors cursor-pointer"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <ScrollToBottom className="animate-in fade-in-0 zoom-in-95 absolute bottom-full left-1/2 mb-4 -translate-x-1/2 border-coral-light text-coral" />

              <ComposerPanel />
            </div>
          }
        />
      </StickToBottom>
    </div>
  );
}
