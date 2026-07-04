"use client";

// ThreadStateProvider — the workbench state/wiring extracted from the old
// Thread() three-pane component, with the JSX UI removed. It owns ALL the
// real production wiring (LangGraph stream, draft autosave, Feishu HITL,
// Ctrl+P commands, evidence/preview state) and exposes it via ThreadContext
// + ThreadActionsProvider, rendering {children}. The new 创作运营工作室 shell
// mounts inside it; nothing about the data layer changed — only the UI moved.

import { v4 as uuidv4 } from "uuid";
import { useEffect, useRef, useState, FormEvent, useCallback, type ReactNode } from "react";
import { useStreamContext } from "@/providers/stream-context";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import { ensureToolCallsHaveResponses } from "@/lib/ensure-tool-responses";
import { useQueryState, parseAsBoolean } from "nuqs";
import { toast } from "sonner";
import { ThreadActionsProvider } from "@/lib/thread-actions";
import { useFileUpload } from "@/hooks/use-file-upload";
import { ThreadContext } from "./ThreadContext";
import { useThreadDraftState } from "./useThreadDraftState";

export function ThreadStateProvider({ children }: { children: ReactNode }) {
  const [threadId, _setThreadId] = useQueryState("threadId");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );
  const [view, setView] = useQueryState("view");
  const [input, setInput] = useState("");
  const {
    contentBlocks,
    setContentBlocks,
    handleFileUpload,
    dropRef,
    removeBlock,
    resetBlocks: _resetBlocks,
    dragOver,
    handlePaste,
  } = useFileUpload();
  const [firstTokenReceived, setFirstTokenReceived] = useState(false);

  const stream = useStreamContext();
  const messages = stream.messages;
  const isLoading = stream.isLoading;

  const lastError = useRef<string | undefined>(undefined);

  // 提交守卫:防止飞书同步动作重复触发。
  const [isSyncing, setIsSyncing] = useState(false);

  const {
    draftTitle,
    setDraftTitle,
    draftContent,
    setDraftContent,
    isDirty,
    setIsDirty,
    lastSavedTitle,
    lastSavedContent,
    resetForThreadSwitch,
  } = useThreadDraftState(threadId, messages);

  const setThreadId = useCallback(
    (id: string | null) => {
      if (isDirty) {
        const ok = window.confirm(
          "您有尚未同步至飞书的本地修改，切换或关闭对话将遗失这些改动。是否确定继续？",
        );
        if (!ok) return;
      }
      _setThreadId(id);
      setView(null);
      setIsDirty(false);
    },
    [isDirty, _setThreadId, setView, setIsDirty],
  );

  const submitText = (text: string, stateUpdate?: Record<string, unknown>) => {
    if (!text.trim() || isLoading) return;
    setFirstTokenReceived(false);
    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: text as Message["content"],
    };
    const toolMessages = ensureToolCallsHaveResponses(stream.messages);

    const context = {
      current_draft: { title: draftTitle, content: draftContent, record_id: null },
    };

    const patch = stateUpdate ?? {};

    stream.submit(
      { messages: [...toolMessages, newHumanMessage], context, ...patch },
      {
        streamMode: ["values"],
        streamSubgraphs: true,
        streamResumable: true,
        optimisticValues: (prev) => ({
          ...prev,
          context,
          ...patch,
          messages: [...(prev.messages ?? []), ...toolMessages, newHumanMessage],
        }),
      },
    );
  };

  const handleExecuteCommand = (cmd: string) => {
    if (cmd === "polish") {
      toast.success("执行 [/polish 智能润色] 指令中，流式修改已发送...");
      submitText(
        [
          "请帮我把右侧这段文案进行智能润色：使标题更吸引眼球，正文增加一些活泼的 Emoji，保持原意不变。",
          "",
          `标题：${draftTitle}`,
          "",
          `正文：${draftContent}`,
        ].join("\n"),
      );
    } else if (cmd === "shorten") {
      toast.success("执行 [/shorten 文案瘦身] 指令中...");
      submitText(
        [
          "请帮我针对以下文案做「瘦身」：在保留核心信息、钩子和情绪的前提下精简篇幅，删掉冗余表达，让正文更紧凑易读，不要新增话题标签。",
          "",
          `标题：${draftTitle}`,
          "",
          `正文：${draftContent}`,
        ].join("\n"),
      );
    } else if (cmd === "tags") {
      toast.success("执行 [/tags 话题推荐] 指令中...");
      submitText(
        `请帮我针对以下文案，生成 5 个在小红书极具热度的话题标签：\n\n${draftContent}`,
      );
    }
  };

  const handleSyncToFeishu = () => {
    if (isSyncing || isLoading) return;
    setIsSyncing(true);
    setTimeout(() => {
      submitText(
        [
          "请调用 sync_copy_to_feishu 工具，把当前右侧文案保存为飞书多维表格草稿。",
          "这是一个写入动作，请先向我确认写入风险和目标表，再继续。",
          "",
          `标题：${draftTitle}`,
          "",
          `正文：${draftContent}`,
        ].join("\n"),
      );
      setIsSyncing(false);
      toast.success("已交给智能体，等待确认/执行。");
    }, 800);
  };

  useEffect(() => {
    if (!stream.error) {
      lastError.current = undefined;
      return;
    }
    try {
      const message = (stream.error as { message?: string }).message ?? "";
      const isThreadGone =
        /thread\b.*\bnot found/i.test(message) ||
        (/\b404\b/.test(message) && /thread/i.test(message));
      if (isThreadGone) {
        lastError.current = message;
        setThreadId(null);
        toast.info("该会话已失效，已为你开启新对话。", { richColors: true, closeButton: true });
        return;
      }

      if (!message || lastError.current === message) return;
      lastError.current = message;
      toast.error("出错了，请重试。", {
        description: (
          <p>
            <strong>错误：</strong> <code>{message}</code>
          </p>
        ),
        richColors: true,
        closeButton: true,
      });
    } catch {
      // no-op
    }
  }, [stream.error, setThreadId]);

  const prevMessageLength = useRef(0);
  useEffect(() => {
    if (
      messages.length !== prevMessageLength.current &&
      messages?.length &&
      messages[messages.length - 1].type === "ai"
    ) {
      setFirstTokenReceived(true);
    }
    prevMessageLength.current = messages.length;
  }, [messages]);

  // 会话切换:重置会话级本地状态 + 载入该会话独立草稿。
  const prevThreadIdRef = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const prev = prevThreadIdRef.current;
    prevThreadIdRef.current = threadId;
    if (prev === null && threadId != null) return; // 新建对话首次拿到 id,非切换
    prevMessageLength.current = 0;
    setFirstTokenReceived(false);
    setInput("");
    setContentBlocks([]);
    resetForThreadSwitch(threadId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if ((input.trim().length === 0 && contentBlocks.length === 0) || isLoading) return;
    setFirstTokenReceived(false);

    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: [
        ...(input.trim().length > 0 ? [{ type: "text", text: input }] : []),
        ...contentBlocks,
      ] as Message["content"],
    };

    const toolMessages = ensureToolCallsHaveResponses(stream.messages);
    const context = {
      current_draft: { title: draftTitle, content: draftContent, record_id: null },
    };

    stream.submit(
      { messages: [...toolMessages, newHumanMessage], context },
      {
        streamMode: ["values"],
        streamSubgraphs: true,
        streamResumable: true,
        optimisticValues: (prev) => ({
          ...prev,
          context,
          messages: [...(prev.messages ?? []), ...toolMessages, newHumanMessage],
        }),
      },
    );

    setInput("");
    setContentBlocks([]);
  };

  const handleRegenerate = (parentCheckpoint: Checkpoint | null | undefined) => {
    prevMessageLength.current = prevMessageLength.current - 1;
    setFirstTokenReceived(false);
    stream.submit(undefined, {
      checkpoint: parentCheckpoint,
      streamMode: ["values"],
      streamSubgraphs: true,
      streamResumable: true,
    });
  };

  return (
    <ThreadContext.Provider
      value={{
        threadId,
        setThreadId,
        chatHistoryOpen,
        setChatHistoryOpen,
        view,
        setView,
        input,
        setInput,
        contentBlocks,
        setContentBlocks,
        isLoading,
        isStreaming: firstTokenReceived,
        error: stream.error,
        setFirstTokenReceived,
        submitText,
        handleSubmit,
        handleRegenerate,
        handleFileUpload,
        dropRef,
        removeBlock,
        dragOver,
        handlePaste,
        messages,

        draftTitle,
        setDraftTitle,
        draftContent,
        setDraftContent,
        isDirty,
        isSyncing,
        setIsSyncing,
        lastSavedTitle,
        lastSavedContent,

        handleExecuteCommand,
        handleSyncToFeishu,
      }}
    >
      <ThreadActionsProvider value={{ submitText }}>{children}</ThreadActionsProvider>
    </ThreadContext.Provider>
  );
}
