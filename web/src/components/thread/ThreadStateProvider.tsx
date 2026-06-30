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
import { useCommandPaletteState } from "./useCommandPaletteState";
import { useWorkbenchTabsState } from "./useWorkbenchTabsState";
import { usePreviewState } from "./usePreviewState";
import { useFeishuWorkspaceState } from "./useFeishuWorkspaceState";

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

  // ── UI 工作台状态变量 ────────────────────────────────────
  const { rightTab, setRightTab, selectedEvidence, setSelectedEvidence } =
    useWorkbenchTabsState();
  const {
    viewMode,
    setViewMode,
    isEditingText,
    setIsEditingText,
    carouselIndex,
    setCarouselIndex,
    carouselImages,
  } = usePreviewState();

  const {
    feishuChats,
    setFeishuChats,
    selectedChatId,
    setSelectedChatId,
    isFetchingChats,
    setIsFetchingChats,
    isSendingNotification,
    setIsSendingNotification,
    isFeishuActionPending,
    setIsFeishuActionPending,
  } = useFeishuWorkspaceState(rightTab);

  // 同步校验进度条状态
  const [syncStepsVisible, setSyncStepsVisible] = useState(false);
  const [syncStep, setSyncStep] = useState<number>(0); // 0=未开始, 1=配置, 2=结构, 3=写入, 4=成功
  const [isSyncing, setIsSyncing] = useState(false);

  // 抛物线飞行动效触发器
  const [isFlying, setIsFlying] = useState(false);

  // 飞书多维表格与知识库跳转链接
  const [bitableUrl, setBitableUrl] = useState<string | null>(null);
  const [wikiUrl, setWikiUrl] = useState<string | null>(null);

  // 原位编辑器 Ref (用于自适应高度)
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 初始化时拉取配置中的 Bitable 与 Wiki 链接
  useEffect(() => {
    fetch("/api/config")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok && data.configs) {
          const appToken = data.configs.FEISHU_BITABLE_APP_TOKEN;
          const tableId = data.configs.FEISHU_BITABLE_TABLE_ID;
          if (appToken && tableId) {
            setBitableUrl(`https://feishu.cn/base/${appToken}?table=${tableId}`);
          }
          const wikiSpaceId = data.configs.FEISHU_WIKI_SPACE_ID;
          if (wikiSpaceId) {
            setWikiUrl(`https://feishu.cn/wiki/space/${wikiSpaceId}`);
          }
        }
      })
      .catch(() => {});
  }, []);

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
  const { showCommandPalette, setShowCommandPalette, cmdSearch, setCmdSearch } =
    useCommandPaletteState();

  // 自适应高度 Editor text area auto grow
  useEffect(() => {
    if (isEditingText && textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.max(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [draftContent, isEditingText]);

  const setThreadId = useCallback(
    (id: string | null) => {
      if (isDirty) {
        const ok = window.confirm(
          "您有尚未同步至飞书的本地修改，切换或关闭对话将遗失这些改动。是否确定继续？",
        );
        if (!ok) return;
      }
      _setThreadId(id);
      setIsEditingText(false);
      setView(null);
      setIsDirty(false);
    },
    [isDirty, _setThreadId, setView, setIsEditingText, setIsDirty],
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
    setShowCommandPalette(false);
    if (cmd === "polish") {
      toast.success("执行 [/polish 智能润色] 指令中，流式修改已发送...");
      submitText(
        `请帮我把右侧这段文案进行智能润色，使标题更吸引眼球，正文增加一些活泼的 Emoji：\n\n${draftContent}`,
      );
    } else if (cmd === "shorten") {
      toast.success("执行 [/shorten 文案瘦身] 指令中...");
      submitText(
        `请帮我针对以下文案，生成 5 个在小红书极具热度的话题标签：\n\n${draftContent}`,
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
    setIsFlying(true);

    setTimeout(() => {
      setIsFlying(false);
      submitText(
        [
          "请调用 sync_copy_to_feishu 工具，把当前右侧文案保存为飞书多维表格草稿。",
          "这是一个写入动作，请先向我确认写入风险 and 目标表，再继续。",
          "",
          `标题：${draftTitle}`,
          "",
          `正文：${draftContent}`,
        ].join("\n"),
      );
      setIsFeishuActionPending(true);
      setSyncStepsVisible(false);
      setSyncStep(0);
      setIsSyncing(false);
      toast.success("已交给智能体，等待确认/执行。");
    }, 800);
  };

  const handleSendNotification = () => {
    if (isSendingNotification || isLoading || !selectedChatId) return;
    setIsSendingNotification(true);

    submitText(
      [
        "请调用 send_review_notification 工具，把当前文案发送到我选择的飞书群用于审核。",
        "这是一个外部发送动作，请先向我确认群聊、标题和正文摘要，再继续。",
        "",
        `chat_id：${selectedChatId}`,
        `标题：${draftTitle}`,
        "",
        `正文：${draftContent}`,
      ].join("\n"),
    );
    setIsFeishuActionPending(true);
    setIsSendingNotification(false);
    toast.success("已交给智能体，等待确认/执行。");
  };

  const handleInsertEmoji = (emoji: string) => {
    const textarea = document.getElementById("edit-body-input") as HTMLTextAreaElement;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    const nextVal = text.substring(0, start) + emoji + text.substring(end);
    setDraftContent(nextVal);

    setTimeout(() => {
      textarea.focus();
      textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
    }, 50);
  };

  const handleAppendTag = (tag: string) => {
    setDraftContent((prev) => prev.trim() + ` #${tag}`);
  };

  const handleEditBodyPaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const text = e.clipboardData.getData("text");
    if (text) {
      e.preventDefault();
      const sanitized = text
        .replace(/\r\n/g, "\n")
        .replace(/\u00A0/g, " ")
        .replace(/\u3000/g, " ");

      const textarea = e.currentTarget;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const val = textarea.value;
      const nextVal = val.substring(0, start) + sanitized + val.substring(end);
      setDraftContent(nextVal);

      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + sanitized.length;
      }, 0);
    }
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
    setIsEditingText(false);
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

        rightTab,
        setRightTab,
        selectedEvidence,
        setSelectedEvidence,
        viewMode,
        setViewMode,
        isEditingText,
        setIsEditingText,
        draftTitle,
        setDraftTitle,
        draftContent,
        setDraftContent,
        carouselIndex,
        setCarouselIndex,
        carouselImages,
        feishuChats,
        setFeishuChats,
        selectedChatId,
        setSelectedChatId,
        isFetchingChats,
        setIsFetchingChats,
        isSendingNotification,
        setIsSendingNotification,
        isFeishuActionPending,
        setIsFeishuActionPending,
        isDirty,
        syncStepsVisible,
        setSyncStepsVisible,
        syncStep,
        setSyncStep,
        isSyncing,
        setIsSyncing,
        isFlying,
        setIsFlying,
        showCommandPalette,
        setShowCommandPalette,
        cmdSearch,
        setCmdSearch,
        bitableUrl,
        wikiUrl,
        lastSavedTitle,
        lastSavedContent,

        handleExecuteCommand,
        handleSyncToFeishu,
        handleSendNotification,
        handleInsertEmoji,
        handleAppendTag,
        handleEditBodyPaste,
        textareaRef,
      }}
    >
      <ThreadActionsProvider value={{ submitText }}>{children}</ThreadActionsProvider>
    </ThreadContext.Provider>
  );
}
