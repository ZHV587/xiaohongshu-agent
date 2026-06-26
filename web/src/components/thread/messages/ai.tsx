import { parsePartialJson } from "@langchain/core/output_parsers";
import { useState, useEffect, useMemo, useRef } from "react";
import { useStreamContext } from "@/providers/stream-context";
import { AIMessage, Checkpoint, Message } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { getContentString } from "../utils";
import { BranchSwitcher, CommandBar } from "./shared";
import { MarkdownText } from "../markdown-text";
import { LoadExternalComponent } from "@langchain/langgraph-sdk/react-ui";
import { cn } from "@/lib/utils";
import { ToolCalls, ToolResult } from "./tool-calls";
import { MessageContentComplex } from "@langchain/core/messages";
import { Fragment } from "react/jsx-runtime";
import { isAgentInboxInterruptSchema } from "@/lib/agent-inbox-interrupt";
import { ThreadView } from "../agent-inbox";
import { GenericInterruptView } from "./generic-interrupt";
import { useArtifact } from "../artifact-hooks";
import { parseXhsBlocks } from "@/lib/xhs-blocks";
import { TopicCards } from "./topic-cards";
import { CopyCard } from "./copy-card";
import { resolveToolRender, ToolResultCards } from "@/lib/tool-render";
import { LoaderCircle, ChevronDown } from "lucide-react";

function CustomComponent({
  message,
  thread,
}: {
  message: Message;
  thread: ReturnType<typeof useStreamContext>;
}) {
  const artifact = useArtifact();
  const { values } = useStreamContext();
  const customComponents = values.ui?.filter(
    (ui) => ui.metadata?.message_id === message.id,
  );

  if (!customComponents?.length) return null;
  return (
    <Fragment key={message.id}>
      {customComponents.map((customComponent) => (
        <LoadExternalComponent
          key={customComponent.id}
          stream={thread as unknown as ReturnType<typeof useStream>}
          message={customComponent}
          meta={{ ui: customComponent, artifact }}
        />
      ))}
    </Fragment>
  );
}

function parseAnthropicStreamedToolCalls(
  content: MessageContentComplex[],
): AIMessage["tool_calls"] {
  const toolCallContents = content.filter((c) => c.type === "tool_use" && c.id);

  return toolCallContents.map((tc) => {
    const toolCall = tc as Record<string, any>;
    let json: Record<string, any> = {};
    if (toolCall?.input) {
      try {
        json = parsePartialJson(toolCall.input) ?? {};
      } catch {
        // Pass
      }
    }
    return {
      name: toolCall.name ?? "",
      id: toolCall.id ?? "",
      args: json,
      type: "tool_call",
    };
  });
}

interface InterruptProps {
  interrupt?: unknown;
  isLastMessage: boolean;
  hasNoAIOrToolMessages: boolean;
}

function Interrupt({
  interrupt,
  isLastMessage,
  hasNoAIOrToolMessages,
}: InterruptProps) {
  const fallbackValue = Array.isArray(interrupt)
    ? (interrupt as Record<string, any>[])
    : (((interrupt as { value?: unknown } | undefined)?.value ??
        interrupt) as Record<string, any>);

  return (
    <>
      {isAgentInboxInterruptSchema(interrupt) &&
        (isLastMessage || hasNoAIOrToolMessages) && (
          <ThreadView interrupt={interrupt} />
        )}
      {interrupt &&
      !isAgentInboxInterruptSchema(interrupt) &&
      (isLastMessage || hasNoAIOrToolMessages) ? (
        <GenericInterruptView interrupt={fallbackValue} />
      ) : null}
    </>
  );
}

export function ThinkingAura({
  toolCalls,
  status = "done",
}: {
  toolCalls: { name: string; args?: any; result?: any }[];
  status?: "running" | "done";
}) {
  const [isExpanded, setIsExpanded] = useState(status === "running");
  const [mountedTime, setMountedTime] = useState<Date | null>(null);
  const [displayedLogs, setDisplayedLogs] = useState<string[]>([]);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setMountedTime(new Date());
  }, []);

  useEffect(() => {
    if (status === "running") {
      setIsExpanded(true);
    }
  }, [status]);

  // Auto-scroll the terminal logs box to the bottom as new logs stream in
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTo({
        top: containerRef.current.scrollHeight,
        behavior: "smooth",
      });
    }
  }, [displayedLogs.length]);

  const visibleCalls = useMemo(() => {
    return (toolCalls || []).filter(tc => {
      if (!tc.name) return false;
      const spec = resolveToolRender(tc.name, tc.args as Record<string, unknown>);
      if (spec.aura === "hidden") return false;  // skills 内部噪音等,不展示
      if (spec.card) return false;               // 有专属富卡片的工具不在思考链里重复
      return true;
    });
  }, [toolCalls]);

  // Memoize targetLogs to prevent reference mutation on every render and avoid React effect reset loops
  const targetLogs = useMemo(() => {
    const logs: string[] = [];
    let seconds = 0;
    
    const formatOffsetTime = (offsetSeconds: number) => {
      if (!mountedTime) return "00:00:00";
      const t = new Date(mountedTime.getTime() + offsetSeconds * 1000);
      const pad = (n: number) => String(n).padStart(2, '0');
      return `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
    };

    visibleCalls.forEach((tc) => {
      const spec = resolveToolRender(tc.name, tc.args as Record<string, unknown>);
      if (spec.aura === "hidden") return;
      const lines = spec.aura.logs?.({ result: tc.result, name: tc.name }) ?? [];
      lines.forEach((line, idx) => {
        logs.push(`[${formatOffsetTime(seconds + idx)}] ${line}`);
      });
      seconds += Math.max(lines.length, 1) + 1;
    });

    return logs;
  }, [visibleCalls, mountedTime]);

  // Stream logs effect
  useEffect(() => {
    if (status === "done") {
      setDisplayedLogs(targetLogs);
      return;
    }

    let timer: NodeJS.Timeout;
    const streamNext = () => {
      setDisplayedLogs((prev) => {
        if (prev.length < targetLogs.length) {
          timer = setTimeout(streamNext, 350); 
          return [...prev, targetLogs[prev.length]];
        }
        return prev;
      });
    };

    if (displayedLogs.length < targetLogs.length) {
      timer = setTimeout(streamNext, 150);
    }

    return () => {
      clearTimeout(timer);
    };
  }, [displayedLogs.length, status, targetLogs]);

  if (!toolCalls || toolCalls.length === 0 || visibleCalls.length === 0) return null;

  const steps: { label: string; isDone: boolean; key: string }[] = [];
  visibleCalls.forEach((tc, idx) => {
    const isLast = idx === visibleCalls.length - 1;
    const isStepDone = status === "done" || !isLast;
    const spec = resolveToolRender(tc.name, tc.args as Record<string, unknown>);
    if (spec.aura === "hidden") return;
    steps.push({
      key: `${tc.name || "tool"}-${idx}`,
      label: isStepDone ? spec.aura.done({ result: tc.result, name: tc.name }) : spec.aura.running,
      isDone: isStepDone,
    });
  });

  if (status === "running") {
    steps.push({
      key: "running-loader",
      label: "正在分析选题规律并撰写小红书笔记...",
      isDone: false,
    });
  }

  return (
    <div className="mr-auto flex flex-col gap-2 py-2 w-full max-w-[460px] select-none">
      <div className="bg-white border border-coral-light/60 p-3.5 rounded-2xl shadow-xs space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="relative flex h-2 w-2">
              {status === "running" && (
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-coral opacity-75"></span>
              )}
              <span className={cn("relative inline-flex rounded-full h-2 w-2", status === "running" ? "bg-coral" : "bg-green-500")}></span>
            </div>
            <span className="text-xs font-bold text-charcoal font-display">思考轨迹 (Thinking Aura)</span>
          </div>
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-[10px] text-coral hover:text-coral-hover font-semibold flex items-center gap-0.5 cursor-pointer border-none bg-transparent outline-none"
          >
            <span>{isExpanded ? "收起分析详情" : "展开分析详情"}</span>
            <ChevronDown className={cn("size-3 transition-transform", isExpanded && "rotate-180")} />
          </button>
        </div>

        <div className="space-y-2 text-xs">
          {steps.map((step) => (
            <div key={step.key} className={cn("flex items-center gap-2", step.isDone ? "text-green-600" : "text-coral font-semibold")}>
              {step.isDone ? (
                <span className="text-green-500 font-bold">✓</span>
              ) : (
                <LoaderCircle className="size-3.5 animate-spin text-coral" />
              )}
              <span>{step.label}</span>
            </div>
          ))}
        </div>

        {isExpanded && displayedLogs.length > 0 && (
          <div 
            ref={containerRef}
            className="border-t border-oats-dark pt-2.5 mt-2 space-y-2 text-[9px] text-gray-400 font-mono bg-oats-light/40 p-2.5 rounded-xl border border-coral-light/20 max-h-32 overflow-y-auto custom-scrollbar"
          >
            {displayedLogs.map((line, index) => (
              <div key={index} className="animate-in fade-in-0 slide-in-from-left-1 duration-200">
                <span className="text-coral font-bold">{line.substring(0, 10)}</span>
                {line.substring(10)}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


export function AssistantMessage({
  message,
  isLoading,
  handleRegenerate,
  precedingTools = [],
  isThinkingOnly = false,
}: {
  message: Message | undefined;
  isLoading: boolean;
  handleRegenerate: (parentCheckpoint: Checkpoint | null | undefined) => void;
  precedingTools?: { id?: string; name: string; args?: any; result?: any }[];
  isThinkingOnly?: boolean;
}) {
  const content = message?.content ?? [];
  const contentString = getContentString(content);
  const thread = useStreamContext();
  const isLastMessage =
    thread.messages[thread.messages.length - 1].id === message?.id;
  const hasNoAIOrToolMessages = !thread.messages.find(
    (m) => m.type === "ai" || m.type === "tool",
  );
  const meta = message ? thread.getMessagesMetadata(message) : undefined;
  const threadInterrupt = thread.interrupt;

  const parentCheckpoint = meta?.firstSeenState?.parent_checkpoint;
  const anthropicStreamedToolCalls = Array.isArray(content)
    ? parseAnthropicStreamedToolCalls(content)
    : undefined;

  const hasToolCalls =
    message &&
    "tool_calls" in message &&
    message.tool_calls &&
    message.tool_calls.length > 0;
  const toolCallsHaveContents =
    hasToolCalls &&
    message.tool_calls?.some(
      (tc) => tc.args && Object.keys(tc.args).length > 0,
    );
  const hasAnthropicToolCalls = !!anthropicStreamedToolCalls?.length;
  const isToolResult = message?.type === "tool";

  return (
    <div className="group mr-auto flex w-full items-start gap-2">
      <div className="flex w-full flex-col gap-2">
        {precedingTools && precedingTools.length > 0 && (
          <ThinkingAura
            toolCalls={precedingTools}
            status={isThinkingOnly && isLoading ? "running" : "done"}
          />
        )}

        {/* 工具富卡片(搜索发现等):注册表驱动,独立于思考链,流式/完成都展示 */}
        <ToolResultCards tools={precedingTools} />

        {!isThinkingOnly && (
          isToolResult ? (
          <>
            <ToolResult message={message} />
            <Interrupt
              interrupt={threadInterrupt}
              isLastMessage={isLastMessage}
              hasNoAIOrToolMessages={hasNoAIOrToolMessages}
            />
          </>
        ) : (
          <>
            {contentString.length > 0 && (
              <div className="flex flex-col gap-3 py-1">
                {parseXhsBlocks(contentString).map((seg, i) => {
                  if (seg.kind === "topics") {
                    return (
                      <div key={i} className="flex flex-col gap-2 relative">
                        <TopicCards data={seg.data} />
                        {seg.isPending && (
                          <div className="border border-border/60 bg-white/60 backdrop-blur-xs text-charcoal-light inline-flex w-fit items-center gap-2 rounded-xl px-3.5 py-2 text-xs shadow-xs animate-pulse">
                            <LoaderCircle className="text-coral size-3.5 animate-spin" />
                            <span>正在精炼选题规律...</span>
                          </div>
                        )}
                      </div>
                    );
                  }
                  if (seg.kind === "copy") {
                    return (
                      <div key={i} className="flex flex-col gap-2 relative">
                        <CopyCard data={seg.data} />
                        {seg.isPending && (
                          <div className="border border-border/60 bg-white/60 backdrop-blur-xs text-charcoal-light inline-flex w-fit items-center gap-2 rounded-xl px-3.5 py-2 text-xs shadow-xs animate-pulse">
                            <LoaderCircle className="text-coral size-3.5 animate-spin" />
                            <span>正在生成爆款文案排版...</span>
                          </div>
                        )}
                      </div>
                    );
                  }
                  if (seg.kind === "pending") {
                    return (
                      <div
                        key={i}
                        className="border-border bg-card text-muted-foreground inline-flex w-fit items-center gap-2 rounded-xl border px-3.5 py-2 text-sm"
                      >
                        <LoaderCircle className="text-primary size-3.5 animate-spin" />
                        {seg.lang === "xhs_topics" ? "正在整理选题…" : "正在生成文案…"}
                      </div>
                    );
                  }
                  return <MarkdownText key={i}>{seg.text}</MarkdownText>;
                })}
              </div>
            )}

            <>
              {(hasToolCalls && toolCallsHaveContents && (
                <ToolCalls toolCalls={message.tool_calls} />
              )) ||
                (hasAnthropicToolCalls && (
                  <ToolCalls toolCalls={anthropicStreamedToolCalls} />
                )) ||
                (hasToolCalls && (
                  <ToolCalls toolCalls={message.tool_calls} />
                ))}
            </>

            {message && (
              <CustomComponent
                message={message}
                thread={thread}
              />
            )}
            <Interrupt
              interrupt={threadInterrupt}
              isLastMessage={isLastMessage}
              hasNoAIOrToolMessages={hasNoAIOrToolMessages}
            />
            <div
              className={cn(
                "mr-auto flex items-center gap-2 transition-opacity",
                "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100",
              )}
            >
              <BranchSwitcher
                branch={meta?.branch}
                branchOptions={meta?.branchOptions}
                onSelect={(branch) => thread.setBranch(branch)}
                isLoading={isLoading}
              />
              <CommandBar
                content={contentString}
                isLoading={isLoading}
                isAiMessage={true}
                handleRegenerate={() => handleRegenerate(parentCheckpoint)}
              />
            </div>
          </>
        ))}
      </div>
    </div>
  );
}

export function AssistantMessageLoading() {
}
