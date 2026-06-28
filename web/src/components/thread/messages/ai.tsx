import { useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useStreamContext } from "@/providers/stream-context";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import { useStream } from "@langchain/langgraph-sdk/react";
import { getContentString } from "../utils";
import { BranchSwitcher, CommandBar } from "./shared";
import { MarkdownText } from "../markdown-text";
import { LoadExternalComponent } from "@langchain/langgraph-sdk/react-ui";
import { cn } from "@/lib/utils";
import { Fragment } from "react/jsx-runtime";
import { isAgentInboxInterruptSchema } from "@/lib/agent-inbox-interrupt";
import { ThreadView } from "../agent-inbox";
import { GenericInterruptView } from "./generic-interrupt";
import { useArtifact } from "../artifact-hooks";
import { parseXhsBlocks } from "@/lib/xhs-blocks";
import { TopicCards } from "./topic-cards";
import { CopyCard } from "./copy-card";
import { PanelCard } from "./panel-card";
import { resolveToolRender, ToolResultCards, type AuraSpec } from "@/lib/tool-render";
import type { AssistantBlock } from "../types";
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
  const stream = useStreamContext();
  const isLoading = stream.isLoading;

  const steps = useMemo(() => {
    // 思考链路完全由消息流派生(通用、与 skill 无关):每个工具调用一步。
    // 工具消息已按回合分组(groupMessages),天然按轮次隔离,不会跨轮泄漏。
    const toolSteps = (toolCalls || [])
      .filter((tc) => tc.name && resolveToolRender(tc.name, tc.args as Record<string, unknown>).aura !== "hidden")
      .map((tc, idx) => {
        const spec = resolveToolRender(tc.name, tc.args as Record<string, unknown>);
        const aura = spec.aura as Exclude<AuraSpec, "hidden">;

        // 异常判定铁律：检测业务级报错
        const hasError =
          tc.result &&
          (tc.result.ok === false ||
            tc.result.error ||
            (typeof tc.result === "object" && "error" in tc.result));
        const isDone = tc.result != null;

        let labelText = "";
        if (isDone) {
          if (hasError) {
            const errorMsg =
              tc.result.error ||
              (typeof tc.result === "object" && tc.result.error) ||
              "未知异常";
            labelText = `执行失败: ${errorMsg}`;
          } else {
            labelText = aura.done({ result: tc.result, name: tc.name });
          }
        } else {
          labelText = aura.running;
        }

        // Gap D: 关键入参摘要(检索词/资源ID/选题方向等),人话化、面向创作者
        const detail = spec.argsSummary?.(tc.args as Record<string, unknown>);

        return {
          key: `${tc.name || "tool"}-${idx}`,
          label: labelText,
          status: isDone ? (hasError ? ("failed" as const) : ("done" as const)) : ("running" as const),
          detail,
        };
      });

    // 中止流兼容：若全局停止了加载，把所有依然是 running 的步骤变更为 interrupted
    return toolSteps.map((s) => {
      if (s.status === "running" && !isLoading) {
        const cleanLabel = s.label.startsWith("正在")
          ? s.label.replace("正在", "已中断:")
          : `已中断: ${s.label}`;
        return {
          ...s,
          status: "interrupted" as const,
          label: cleanLabel,
        };
      }
      return s;
    });
  }, [toolCalls, isLoading]);

  if (steps.length === 0) return null;

  const anyRunning = steps.some((s) => s.status === "running") || status === "running";

  return (
    <div className="mr-auto flex w-full max-w-[460px] flex-col gap-2 py-1 select-none">
      <motion.div
        layout
        transition={{ layout: { duration: 0.3, ease: [0.4, 0, 0.2, 1] } }}
        className="overflow-hidden rounded-2xl border border-coral-light/50 bg-gradient-to-b from-white to-oats-light/30 px-4 py-3 shadow-xs"
      >
        <div className="mb-2.5 flex items-center gap-2">
          <div className="relative flex h-2 w-2">
            {anyRunning && (
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-coral opacity-75" />
            )}
            <span
              className={cn(
                "relative inline-flex h-2 w-2 rounded-full transition-colors duration-500",
                anyRunning ? "bg-coral" : "bg-green-500",
              )}
            />
          </div>
          <span className="font-display text-xs font-bold tracking-tight text-charcoal">
            思考轨迹
          </span>
          {anyRunning && (
            <motion.span
              initial={{ opacity: 0 }}
              animate={{ opacity: [0.4, 1, 0.4] }}
              transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
              className="text-[10px] font-medium text-coral/70"
            >
              思考中
            </motion.span>
          )}
        </div>

        {/* 时间线:节点串在一条竖线上,连续呈现真实推理轨迹 */}
        <div className="relative">
          <motion.span
            layout
            className="absolute top-1 bottom-1 left-[6.5px] w-px bg-gradient-to-b from-coral-light/70 via-coral-light/40 to-coral-light/5"
          />
          <motion.div layout className="flex flex-col gap-2.5">
            <AnimatePresence initial={false}>
              {steps.map((step) => (
                <motion.div
                  key={step.key}
                  layout
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
                  className="relative flex items-start gap-2.5"
                >
                  <span className="relative z-10 mt-px flex size-3.5 shrink-0 items-center justify-center rounded-full bg-white">
                    <AnimatePresence mode="wait" initial={false}>
                      {step.status === "done" && (
                        <motion.span
                          key="done"
                          initial={{ scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ type: "spring", stiffness: 520, damping: 26 }}
                          className="flex size-3.5 items-center justify-center rounded-full bg-green-500 text-[8px] font-bold text-white"
                        >
                          ✓
                        </motion.span>
                      )}
                      {step.status === "running" && (
                        <motion.span
                          key="run"
                          initial={{ opacity: 0 }}
                          animate={{ opacity: 1 }}
                          exit={{ opacity: 0 }}
                          className="relative flex size-3.5 items-center justify-center"
                        >
                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-coral/40" />
                          <LoaderCircle className="relative size-3.5 animate-spin text-coral" />
                        </motion.span>
                      )}
                      {step.status === "failed" && (
                        <motion.span
                          key="failed"
                          initial={{ scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ type: "spring", stiffness: 520, damping: 26 }}
                          className="flex size-3.5 items-center justify-center rounded-full bg-rose-500 text-[8px] font-bold text-white"
                        >
                          ✗
                        </motion.span>
                      )}
                      {step.status === "interrupted" && (
                        <motion.span
                          key="interrupted"
                          initial={{ scale: 0, opacity: 0 }}
                          animate={{ scale: 1, opacity: 1 }}
                          transition={{ type: "spring", stiffness: 520, damping: 26 }}
                          className="flex size-3.5 items-center justify-center rounded-full bg-gray-400 text-[8px] font-bold text-white"
                        >
                          –
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </span>
                  <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
                    <AnimatePresence mode="wait" initial={false}>
                      <motion.span
                        key={step.label}
                        initial={{ opacity: 0, y: 3 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -3 }}
                        transition={{ duration: 0.2 }}
                        className={cn(
                          "text-xs leading-relaxed transition-colors",
                          step.status === "running" && "text-charcoal/60 font-medium",
                          step.status === "done" && "text-charcoal-light",
                          step.status === "failed" && "text-rose-600 font-semibold",
                          step.status === "interrupted" && "text-gray-400",
                        )}
                      >
                        {step.label}
                      </motion.span>
                    </AnimatePresence>
                    {step.detail && (
                      <span
                        title={step.detail}
                        className="max-w-[220px] truncate rounded-md bg-oats-light/60 px-1.5 py-px text-[11px] text-charcoal-light/70"
                      >
                        {step.detail}
                      </span>
                    )}
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </motion.div>
        </div>
      </motion.div>
    </div>
  );
}


/** 渲染一条 ai 文本消息的内容(选题/文案卡片、Markdown、流式占位、自定义 UI)。
 *  每条 ai 消息独立渲染,绝不被同回合后续消息覆盖。 */
function AiContent({ message }: { message: Message }) {
  const thread = useStreamContext();
  const contentString = getContentString(message.content ?? []);
  if (!contentString.length) {
    return <CustomComponent message={message} thread={thread} />;
  }
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
    >
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
          if (seg.kind === "panel") {
            return (
              <PanelCard
                key={i}
                data={seg.data}
                messageId={message.id}
              />
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
      <CustomComponent message={message} thread={thread} />
    </motion.div>
  );
}

export function AssistantMessage({
  blocks = [],
  isLoading,
  handleRegenerate,
  isLastGroup = false,
}: {
  blocks?: AssistantBlock[];
  isLoading: boolean;
  handleRegenerate: (parentCheckpoint: Checkpoint | null | undefined) => void;
  isLastGroup?: boolean;
}) {
  const thread = useStreamContext();
  const threadInterrupt = thread.interrupt;
  const hasNoAIOrToolMessages = !thread.messages.find(
    (m) => m.type === "ai" || m.type === "tool",
  );

  // 操作区(分支切换/重生成/复制)绑定到回合内最后一条 ai 文本消息
  const aiMessages = blocks
    .filter((b): b is { kind: "ai"; message: Message } => b.kind === "ai")
    .map((b) => b.message);
  const primary = aiMessages.length ? aiMessages[aiMessages.length - 1] : undefined;
  const meta = primary ? thread.getMessagesMetadata(primary) : undefined;
  const parentCheckpoint = meta?.firstSeenState?.parent_checkpoint;
  const primaryContent = primary ? getContentString(primary.content ?? []) : "";
  const primaryIsLastMessage = primary
    ? thread.messages[thread.messages.length - 1]?.id === primary.id
    : false;
  // 中断弹窗(HITL)绑定到"当前活跃组":最后一组即当前暂停点,纯工具调用后也能正确显示
  const showInterruptHere = primaryIsLastMessage || isLastGroup;

  const lastBlockIdx = blocks.length - 1;

  // 兜底"思考中"占位:当前组在加载,但还没有可见工具步骤、也没有 AI 文本内容时
  // (如 agent 刚冒出空 AI 消息、模型仍在推理),补一个思考占位,杜绝中间空白。
  const hasVisibleTools = blocks.some(
    (b) => b.kind === "tools" && b.tools.length > 0,
  );
  const hasAiText = blocks.some(
    (b) =>
      b.kind === "ai" &&
      getContentString(b.message.content ?? "").trim().length > 0,
  );
  const showThinkingPlaceholder =
    isLastGroup && isLoading && !hasVisibleTools && !hasAiText;

  return (
    <div className="group mr-auto flex w-full items-start gap-2">
      <div className="flex w-full flex-col gap-2">
        {blocks.map((block, i) => {
          if (block.kind === "tools") {
            // 末尾 tools 块在最后一组且仍加载时为"运行中"(含多轮工具的后续轮次)
            const running = isLoading && isLastGroup && i === lastBlockIdx;
            return (
              <Fragment key={`tools-${i}`}>
                <ThinkingAura
                  toolCalls={block.tools}
                  status={running ? "running" : "done"}
                />
                {/* 工具富卡片(搜索发现等):注册表驱动,与思考链同位、流式/完成都展示 */}
                <ToolResultCards tools={block.tools} />
              </Fragment>
            );
          }
          return (
            <AiContent key={block.message.id || `ai-${i}`} message={block.message} />
          );
        })}

        {showThinkingPlaceholder && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            className="mr-auto flex w-full max-w-[460px] flex-col gap-2 py-1 select-none"
          >
            <div className="border-coral-light/50 flex items-center gap-2.5 rounded-2xl border bg-gradient-to-b from-white to-oats-light/30 p-3.5 shadow-xs">
              <LoaderCircle className="text-coral size-4 animate-spin" />
              <motion.span
                animate={{ opacity: [0.5, 1, 0.5] }}
                transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }}
                className="text-charcoal-light text-xs font-medium"
              >
                正在思考…
              </motion.span>
            </div>
          </motion.div>
        )}

        <Interrupt
          interrupt={threadInterrupt}
          isLastMessage={showInterruptHere}
          hasNoAIOrToolMessages={hasNoAIOrToolMessages}
        />

        {primary && (
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
              content={primaryContent}
              isLoading={isLoading}
              isAiMessage={true}
              handleRegenerate={() => handleRegenerate(parentCheckpoint)}
            />
          </div>
        )}
      </div>
    </div>
  );
}

export function AssistantMessageLoading() {
}
