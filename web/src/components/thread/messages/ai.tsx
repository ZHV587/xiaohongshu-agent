import { parsePartialJson } from "@langchain/core/output_parsers";
import { useState, useEffect } from "react";
import { useStreamContext } from "@/providers/Stream";
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
import { useArtifact } from "../artifact";
import { parseXhsBlocks } from "@/lib/xhs-blocks";
import { TopicCards } from "./topic-cards";
import { CopyCard } from "./copy-card";
import { LoaderCircle } from "lucide-react";

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

export function AssistantMessage({
  message,
  isLoading,
  handleRegenerate,
}: {
  message: Message | undefined;
  isLoading: boolean;
  handleRegenerate: (parentCheckpoint: Checkpoint | null | undefined) => void;
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
        {isToolResult ? (
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
                  if (seg.kind === "topics") return <TopicCards key={i} data={seg.data} />;
                  if (seg.kind === "copy") return <CopyCard key={i} data={seg.data} />;
                  if (seg.kind === "pending")
                    return (
                      <div
                        key={i}
                        className="border-border bg-card text-muted-foreground inline-flex w-fit items-center gap-2 rounded-xl border px-3.5 py-2 text-sm"
                      >
                        <LoaderCircle className="text-primary size-3.5 animate-spin" />
                        {seg.lang === "xhs_topics" ? "正在整理选题…" : "正在生成文案…"}
                      </div>
                    );
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
        )}
      </div>
    </div>
  );
}

export function AssistantMessageLoading() {
  const [isExpanded, setIsExpanded] = useState(false);
  const [mountedTime, setMountedTime] = useState<Date | null>(null);

  useEffect(() => {
    setMountedTime(new Date());
  }, []);

  const formatOffsetTime = (offsetSeconds: number) => {
    if (!mountedTime) return "00:00:00";
    const t = new Date(mountedTime.getTime() + offsetSeconds * 1000);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${pad(t.getHours())}:${pad(t.getMinutes())}:${pad(t.getSeconds())}`;
  };

  return (
    <div className="mr-auto flex flex-col gap-2 py-2 w-full max-w-[460px]">
      <div className="bg-white border border-coral-light/60 p-3.5 rounded-2xl shadow-xs space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {/* 呼吸脉动指示灯 */}
            <div className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-coral opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-coral"></span>
            </div>
            <span className="text-xs font-bold text-charcoal font-display">思考轨迹 (Thinking Aura)</span>
          </div>
          <button 
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-[10px] text-coral hover:text-coral-hover font-semibold flex items-center gap-0.5 cursor-pointer"
          >
            <span>{isExpanded ? "收起分析详情" : "展开分析详情"}</span>
          </button>
        </div>

        {/* 步进器 stepper */}
        <div className="space-y-2 text-xs">
          <div className="flex items-center gap-2 text-green-600">
            <span className="text-green-500 font-bold">✓</span>
            <span>已成功解析飞书多维表格 (45 条爆款装备数据)</span>
          </div>
          <div className="flex items-center gap-2 text-coral font-semibold">
            <LoaderCircle className="size-3.5 animate-spin text-coral" />
            <span>正在分析选题规律并撰写小红书笔记...</span>
          </div>
        </div>

        {/* 可折叠的思考日志日志 */}
        {isExpanded && (
          <div className="border-t border-oats-dark pt-2.5 mt-2 space-y-2 text-[9px] text-gray-400 font-mono bg-oats-light/40 p-2.5 rounded-xl border border-coral-light/20 max-h-32 overflow-y-auto custom-scrollbar">
            <div><span className="text-coral font-bold">[{formatOffsetTime(0)}]</span> 开始连接并读取飞书多维表格，自动过滤噪声列防爆窗口。</div>
            <div><span className="text-coral font-bold">[{formatOffsetTime(2)}]</span> 爆款算法筛选：互动量排名前 10% 的内容多具备痛点防坑属性。</div>
            <div><span className="text-coral font-bold">[{formatOffsetTime(3)}]</span> 精炼爆款关键词：#露营清单、#性价比露营装备、#新手指南。</div>
            <div><span className="text-coral font-bold">[{formatOffsetTime(4)}]</span> 正在结合大数据选题生成包含排版 Emoji 的笔记草稿...</div>
          </div>
        )}
      </div>
    </div>
  );
}
