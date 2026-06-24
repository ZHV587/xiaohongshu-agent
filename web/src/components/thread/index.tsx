import { v4 as uuidv4 } from "uuid";
import { useEffect, useRef, useState, FormEvent, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import * as Dialog from "@radix-ui/react-dialog";
import { cn } from "@/lib/utils";
import { useStreamContext } from "@/providers/stream-context";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import { ensureToolCallsHaveResponses } from "@/lib/ensure-tool-responses";
import { XIcon, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useQueryState, parseAsBoolean } from "nuqs";
import ThreadHistory from "./history";
import { LlmConfigPage } from "./history/LlmConfigPage";
import { FeishuConfigPage } from "./history/FeishuConfigPage";
import { RuntimeFactsPage } from "./history/RuntimeFactsPage";
import { toast } from "sonner";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { ThreadActionsProvider } from "@/lib/thread-actions";
import { useFileUpload } from "@/hooks/use-file-upload";
import { SourceEvidence } from "./types";
import { ThreadContext } from "./ThreadContext";
import { ChatTimeline } from "./ChatTimeline";
import { EvidenceInspector } from "./EvidenceInspector";
import { RightInspector } from "./RightInspector";

export function Thread() {
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
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");

  const stream = useStreamContext();
  const messages = stream.messages;
  const isLoading = stream.isLoading;

  const lastError = useRef<string | undefined>(undefined);

  // ── UI 工作台状态变量 ────────────────────────────────────
  const [rightTab, setRightTab] = useState<"mock" | "feishu" | "evidence">(
    "mock",
  );
  const [selectedEvidence, setSelectedEvidence] =
    useState<SourceEvidence | null>(null);
  const [viewMode, setViewMode] = useState<"detail" | "feed">("detail");
  const [isEditingText, setIsEditingText] = useState(false);

  // 当前动态编辑的选题和正文
  const [draftTitle, setDraftTitle] = useState("精致露营「搬家式」装备清单");
  const [draftContent, setDraftContent] = useState(
    "夏天太适合露营啦！⛺但是作为一个精致的搬家式露营玩家，带什么装备去真的大有讲究！今天就给大家盘点一下我私藏的「搬家式」露营好物，少带一件体验感都打折！\n\n👇精致露营必带清单：\n1️⃣ 双顶充气天幕：不仅防雨防晒，最重要是拍照真的超出片！空间很大，容纳8个人也宽敞。",
  );

  // 多图轮播状态
  const [carouselIndex, setCarouselIndex] = useState(0);
  const carouselImages = [
    "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=500&q=80",
    "https://images.unsplash.com/photo-1533873984035-25970ab07461?auto=format&fit=crop&w=500&q=80",
    "https://images.unsplash.com/photo-1478131143081-80f7f84ca84d?auto=format&fit=crop&w=500&q=80",
  ];

  // 飞书群组与通知发送状态
  const [feishuChats, setFeishuChats] = useState<
    { chat_id: string; name: string }[]
  >([]);
  const [selectedChatId, setSelectedChatId] = useState("");
  const [isFetchingChats, setIsFetchingChats] = useState(false);
  const [isSendingNotification, setIsSendingNotification] = useState(false);
  const [isFeishuActionPending, setIsFeishuActionPending] = useState(false);

  // 同步校验进度条状态
  const [syncStepsVisible, setSyncStepsVisible] = useState(false);
  const [syncStep, setSyncStep] = useState<number>(0); // 0=未开始, 1=配置, 2=结构, 3=写入, 4=成功
  const [isSyncing, setIsSyncing] = useState(false);

  // 抛物线飞行动效触发器
  const [isFlying, setIsFlying] = useState(false);

  // Ctrl+P 智能润色工具箱弹窗
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [cmdSearch, setCmdSearch] = useState("");

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
            setBitableUrl(
              `https://feishu.cn/base/${appToken}?table=${tableId}`,
            );
          }
          const wikiSpaceId = data.configs.FEISHU_WIKI_SPACE_ID;
          if (wikiSpaceId) {
            setWikiUrl(`https://feishu.cn/wiki/space/${wikiSpaceId}`);
          }
        }
      })
      .catch(() => {});
  }, []);

  // Load autosaved draft on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("xhs_autosave_draft");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.title) setDraftTitle(parsed.title);
        if (parsed.content) setDraftContent(parsed.content);
      }
    } catch (e) {
      console.error("加载本地草稿失败", e);
    }
  }, []);

  const [isDirty, setIsDirty] = useState(false);
  const [lastSavedContent, setLastSavedContent] = useState("");
  const [lastSavedTitle, setLastSavedTitle] = useState("");

  // Initialize lastSaved state when AI generates new draft
  useEffect(() => {
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.type === "ai" && typeof lastMsg.content === "string") {
        setLastSavedContent(lastMsg.content);
        const lines = lastMsg.content.trim().split("\n");
        const firstLine = lines[0]
          .replace(/^[#\s*✨🍠⛺☕🌿👇📝🌟🔥🚗]*/gu, "")
          .trim();
        if (firstLine && firstLine.length < 40) {
          setLastSavedTitle(firstLine);
        } else {
          setLastSavedTitle("小红书爆款文案");
        }
        setIsDirty(false);
      }
    }
  }, [messages]);

  // Autosave to localStorage and track changes
  useEffect(() => {
    localStorage.setItem(
      "xhs_autosave_draft",
      JSON.stringify({ title: draftTitle, content: draftContent }),
    );
    if (
      lastSavedContent &&
      (draftContent !== lastSavedContent || draftTitle !== lastSavedTitle)
    ) {
      setIsDirty(true);
    } else {
      setIsDirty(false);
    }
  }, [draftTitle, draftContent, lastSavedContent, lastSavedTitle]);

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
    [isDirty, _setThreadId, setView],
  );

  // 监听 AI 流式更新，实时同步至右侧模拟器预览
  useEffect(() => {
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.type === "ai" && typeof lastMsg.content === "string") {
        const text = lastMsg.content.trim();
        const lines = text.split("\n");
        if (lines.length > 0) {
          // 智能截取第一行作为手机卡片的标题
          const firstLine = lines[0]
            .replace(/^[#\s*✨🍠⛺☕🌿👇📝🌟🔥🚗]*/gu, "")
            .trim();
          if (firstLine && firstLine.length < 40) {
            setDraftTitle(firstLine);
            setDraftContent(text);
          } else {
            setDraftContent(text);
          }
        }
      }
    }
  }, [messages]);

  // 当切换到飞书 Tab 时，拉取真实群聊列表
  useEffect(() => {
    if (rightTab === "feishu" && feishuChats.length === 0) {
      setIsFetchingChats(true);
      fetch("/api/feishu/chats")
        .then((res) => {
          if (res.ok) return res.json();
          throw new Error("Unauthorized");
        })
        .then((data) => {
          if (data.ok && data.chats) {
            setFeishuChats(data.chats);
            if (data.chats.length > 0) {
              setSelectedChatId(data.chats[0].chat_id);
            }
          }
        })
        .catch((err) => {
          toast.error("获取飞书群聊列表失败，请检查授权状态");
          setFeishuChats([]);
        })
        .finally(() => {
          setIsFetchingChats(false);
        });
    }
  }, [rightTab, feishuChats.length]);

  // 监听 Ctrl+P 热键，阻断默认打印行为
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "p") {
        e.preventDefault();
        setShowCommandPalette((prev) => !prev);
      }
      if (e.key === "Escape") {
        setShowCommandPalette(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const submitText = (text: string) => {
    if (!text.trim() || isLoading) return;
    setFirstTokenReceived(false);
    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: text as Message["content"],
    };
    const toolMessages = ensureToolCallsHaveResponses(stream.messages);

    // 原位编辑的文案自动附带在 context 字段中，实现与 Agent 状态的无缝对齐
    const context = {
      current_draft: {
        title: draftTitle,
        content: draftContent,
        record_id: null,
      },
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
          messages: [
            ...(prev.messages ?? []),
            ...toolMessages,
            newHumanMessage,
          ],
        }),
      },
    );
  };

  // 执行 Ctrl+P 智能指令
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

  // 将飞书写入意图交给 Agent，由 HITL 确认后执行。
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

  // 将群通知意图交给 Agent，由 HITL 确认后执行。
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

  // Emoji 点选插入
  const handleInsertEmoji = (emoji: string) => {
    const textarea = document.getElementById(
      "edit-body-input",
    ) as HTMLTextAreaElement;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = textarea.value;
    const nextVal = text.substring(0, start) + emoji + text.substring(end);
    setDraftContent(nextVal);

    // 重设焦点与光标位置
    setTimeout(() => {
      textarea.focus();
      textarea.selectionStart = textarea.selectionEnd = start + emoji.length;
    }, 50);
  };

  // Tag 智能追加
  const handleAppendTag = (tag: string) => {
    setDraftContent((prev) => prev.trim() + ` #${tag}`);
  };

  // 粘贴文本净化处理器
  const handleEditBodyPaste = (
    e: React.ClipboardEvent<HTMLTextAreaElement>,
  ) => {
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
        textarea.selectionStart = textarea.selectionEnd =
          start + sanitized.length;
      }, 0);
    }
  };

  useEffect(() => {
    if (!stream.error) {
      lastError.current = undefined;
      return;
    }
    try {
      const message = (stream.error as any).message ?? "";
      const isThreadGone =
        /thread\b.*\bnot found/i.test(message) ||
        (/\b404\b/.test(message) && /thread/i.test(message));
      if (isThreadGone) {
        lastError.current = message;
        setThreadId(null);
        toast.info("该会话已失效，已为你开启新对话。", {
          richColors: true,
          closeButton: true,
        });
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

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if ((input.trim().length === 0 && contentBlocks.length === 0) || isLoading)
      return;
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
      current_draft: {
        title: draftTitle,
        content: draftContent,
        record_id: null,
      },
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
          messages: [
            ...(prev.messages ?? []),
            ...toolMessages,
            newHumanMessage,
          ],
        }),
      },
    );

    setInput("");
    setContentBlocks([]);
  };

  const handleRegenerate = (
    parentCheckpoint: Checkpoint | null | undefined,
  ) => {
    prevMessageLength.current = prevMessageLength.current - 1;
    setFirstTokenReceived(false);
    stream.submit(undefined, {
      checkpoint: parentCheckpoint,
      streamMode: ["values"],
      streamSubgraphs: true,
      streamResumable: true,
    });
  };

  const chatStarted = !!threadId || !!messages.length;
  const rightWorkbenchVisible = chatStarted && !view;

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

        // Workstation states
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

        // Actions
        handleSyncToFeishu,
        handleSendNotification,
        handleInsertEmoji,
        handleAppendTag,
        handleEditBodyPaste,
        textareaRef,
      }}
    >
      <ThreadActionsProvider value={{ submitText }}>
        <div className="bg-oats relative flex h-screen w-full overflow-hidden">
          {/* 物理抛物线飞行动效元素 */}
          <AnimatePresence>
            {isFlying && (
              <motion.div
                initial={{ left: "25%", top: "85%", scale: 1.2, opacity: 1 }}
                animate={{
                  left: "78%",
                  top: "15%",
                  scale: 0.35,
                  opacity: 0.15,
                }}
                exit={{ opacity: 0 }}
                transition={{
                  left: { duration: 0.8, ease: "linear" },
                  top: { duration: 0.8, ease: [0.15, 0.85, 0.45, 1.0] },
                  scale: { duration: 0.8, ease: "easeInOut" },
                  opacity: { duration: 0.8, ease: "easeIn" },
                }}
                className="bg-coral pointer-events-none absolute z-50 rounded-full px-3.5 py-2 text-[11px] font-bold text-white shadow-lg"
              >
                🍠 正在同步...
              </motion.div>
            )}
          </AnimatePresence>

          {/* Ctrl+P 智能润色工具箱悬浮弹窗 */}
          <Dialog.Root
            open={showCommandPalette}
            onOpenChange={setShowCommandPalette}
          >
            <Dialog.Portal>
              <Dialog.Overlay className="bg-charcoal-dark/30 data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 fixed inset-0 z-50 backdrop-blur-xs" />
              <Dialog.Content
                aria-modal="true"
                className="border-coral-light data-[state=closed]:animate-out data-[state=open]:animate-in data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-1/2 left-1/2 z-50 flex max-h-[min(70vh,520px)] w-[min(500px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 flex-col gap-3 overflow-hidden rounded-2xl border bg-white p-4 shadow-2xl outline-none"
              >
                <Dialog.Title className="sr-only">智能润色工具箱</Dialog.Title>
                <Dialog.Description className="sr-only">
                  搜索并执行小红书文案润色、精简和话题推荐指令。
                </Dialog.Description>
                <div className="flex items-center gap-2 border-b pb-2">
                  <span className="bg-coral-light text-coral rounded px-2 py-1 text-sm font-bold">
                    Ctrl+P
                  </span>
                  <input
                    type="text"
                    placeholder="搜索润色指令 (e.g. /polish, /shorten)..."
                    value={cmdSearch}
                    onChange={(e) => setCmdSearch(e.target.value)}
                    className="min-h-12 flex-1 border-none text-sm outline-none focus:ring-0"
                    autoFocus
                  />
                </div>
                <div className="flex flex-col gap-1 overflow-y-auto text-xs">
                  <button
                    type="button"
                    onClick={() => handleExecuteCommand("polish")}
                    className="group hover:bg-oats flex min-h-12 cursor-pointer items-center justify-between rounded-xl p-3 text-left transition-colors"
                  >
                    <span>
                      <span className="text-coral font-bold">/polish</span>
                      <span className="text-charcoal-light ml-2">
                        智能精细润色文案
                      </span>
                    </span>
                    <span className="group-hover:text-coral text-[10px] font-medium text-gray-400">
                      执行 Enter
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleExecuteCommand("shorten")}
                    className="group hover:bg-oats flex min-h-12 cursor-pointer items-center justify-between rounded-xl p-3 text-left transition-colors"
                  >
                    <span>
                      <span className="text-coral font-bold">/shorten</span>
                      <span className="text-charcoal-light ml-2">
                        文案精简瘦身
                      </span>
                    </span>
                    <span className="group-hover:text-coral text-[10px] font-medium text-gray-400">
                      执行 Enter
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => handleExecuteCommand("tags")}
                    className="group hover:bg-oats flex min-h-12 cursor-pointer items-center justify-between rounded-xl p-3 text-left transition-colors"
                  >
                    <span>
                      <span className="text-coral font-bold">/tags</span>
                      <span className="text-charcoal-light ml-2">
                        自动匹配热门话题
                      </span>
                    </span>
                    <span className="group-hover:text-coral text-[10px] font-medium text-gray-400">
                      执行 Enter
                    </span>
                  </button>
                </div>
                <div className="flex justify-end border-t pt-2 text-[10px] text-gray-400">
                  按 Esc 键或点击空白关闭
                </div>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>

          {/* 侧边栏 */}
          <div className="relative hidden lg:flex">
            <motion.div
              className="bg-sidebar absolute z-20 h-full overflow-hidden border-r"
              aria-hidden={!chatHistoryOpen}
              inert={!chatHistoryOpen ? true : undefined}
              style={{ width: 300 }}
              animate={{ x: chatHistoryOpen ? 0 : -300 }}
              initial={{ x: -300 }}
              transition={
                isLargeScreen
                  ? { type: "spring", stiffness: 300, damping: 30 }
                  : { duration: 0 }
              }
            >
              <div
                className="relative h-full"
                style={{ width: 300 }}
              >
                <ThreadHistory onThreadClick={setThreadId} />
              </div>
            </motion.div>
          </div>

          {/* 主画布布局：双视窗分屏展示 */}
          <main
            aria-label="创作工作台"
            className={cn(
              "grid w-full min-w-0 grid-cols-[minmax(0,1fr)] transition-all duration-500",
              rightWorkbenchVisible && "lg:grid-cols-[minmax(0,1fr)_480px]",
            )}
          >
            {/* 左侧：聊天面板 */}
            <motion.div
              className={cn(
                "relative flex min-w-0 flex-1 flex-col overflow-hidden",
                !chatStarted && "grid-rows-[1fr]",
              )}
              layout={isLargeScreen}
              animate={{
                marginLeft: chatHistoryOpen ? (isLargeScreen ? 300 : 0) : 0,
                width: chatHistoryOpen
                  ? isLargeScreen
                    ? "calc(100% - 300px)"
                    : "100%"
                  : "100%",
              }}
            >
              {view === "llm" ? (
                <LlmConfigPage onClose={() => setView(null)} />
              ) : view === "feishu" ? (
                <FeishuConfigPage onClose={() => setView(null)} />
              ) : view === "runtime-facts" ? (
                <RuntimeFactsPage onClose={() => setView(null)} />
              ) : (
                <ChatTimeline />
              )}
            </motion.div>

            {/* 右侧：iPhone 模拟器与飞书协作工作台 */}
            {rightWorkbenchVisible && (
              <aside
                aria-label="预览与协作工作台"
                className="border-coral-light/50 relative z-10 hidden h-full w-[480px] flex-col overflow-hidden border-l bg-white shadow-lg lg:flex"
              >
                {/* Tab 页头 */}
                <div className="border-coral-light/60 bg-oats-light/20 flex shrink-0 items-center justify-between border-b px-3 py-2 select-none">
                  <div className="bg-oats-dark/60 border-coral-light/40 relative flex gap-1 rounded-xl border p-1 select-none">
                    <button
                      onClick={() => setRightTab("mock")}
                      className="relative z-10 min-h-11 cursor-pointer rounded-lg border-none bg-transparent px-3 py-2 text-[10px] font-bold transition-all outline-none"
                    >
                      {rightTab === "mock" && (
                        <motion.div
                          layoutId="activeTabIndicator"
                          className="absolute inset-0 z-[-1] rounded-lg bg-white shadow-sm"
                          transition={{
                            type: "spring",
                            stiffness: 380,
                            damping: 30,
                          }}
                        />
                      )}
                      <span
                        className={cn(
                          "transition-colors duration-200",
                          rightTab === "mock"
                            ? "text-coral"
                            : "hover:text-charcoal text-gray-500",
                        )}
                      >
                        📱 手机预览
                      </span>
                    </button>
                    <button
                      onClick={() => setRightTab("feishu")}
                      className="relative z-10 min-h-11 cursor-pointer rounded-lg border-none bg-transparent px-3 py-2 text-[10px] font-bold transition-all outline-none"
                    >
                      {rightTab === "feishu" && (
                        <motion.div
                          layoutId="activeTabIndicator"
                          className="absolute inset-0 z-[-1] rounded-lg bg-white shadow-sm"
                          transition={{
                            type: "spring",
                            stiffness: 380,
                            damping: 30,
                          }}
                        />
                      )}
                      <span
                        className={cn(
                          "transition-colors duration-200",
                          rightTab === "feishu"
                            ? "text-coral"
                            : "hover:text-charcoal text-gray-500",
                        )}
                      >
                        🔗 飞书协作
                      </span>
                    </button>
                    <button
                      onClick={() => setRightTab("evidence")}
                      className="relative z-10 min-h-11 cursor-pointer rounded-lg border-none bg-transparent px-3 py-2 text-[10px] font-bold transition-all outline-none"
                    >
                      {rightTab === "evidence" && (
                        <motion.div
                          layoutId="activeTabIndicator"
                          className="absolute inset-0 z-[-1] rounded-lg bg-white shadow-sm"
                          transition={{
                            type: "spring",
                            stiffness: 380,
                            damping: 30,
                          }}
                        />
                      )}
                      <span
                        className={cn(
                          "transition-colors duration-200",
                          rightTab === "evidence"
                            ? "text-coral"
                            : "hover:text-charcoal text-gray-500",
                        )}
                      >
                        📊 依据分析
                      </span>
                    </button>
                  </div>

                  {/* 双视窗预览模式切换（仅在预览 Tab 下可见） */}
                  {rightTab === "mock" && (
                    <div className="bg-oats border-coral-light/60 flex items-center gap-0.5 rounded-xl border p-0.5 text-[9px]">
                      <button
                        onClick={() => setViewMode("detail")}
                        className={cn(
                          "min-h-11 cursor-pointer rounded-lg px-3 py-2 font-bold transition-colors",
                          viewMode === "detail"
                            ? "text-coral bg-white shadow-xs"
                            : "text-gray-500",
                        )}
                      >
                        详情页
                      </button>
                      <button
                        onClick={() => setViewMode("feed")}
                        className={cn(
                          "min-h-11 cursor-pointer rounded-lg px-3 py-2 font-bold transition-colors",
                          viewMode === "feed"
                            ? "text-coral bg-white shadow-xs"
                            : "text-gray-500",
                        )}
                      >
                        瀑布流
                      </button>
                    </div>
                  )}
                </div>

                {/* Tab 视图面板，使用 AnimatePresence 进行平滑滑入淡出过渡 */}
                <div className="relative w-full flex-grow overflow-hidden">
                  <AnimatePresence mode="wait">
                    {rightTab === "mock" ? (
                      <motion.div
                        key="mock-tab"
                        initial={{ opacity: 0, x: -12 }}
                        animate={{ opacity: 1, x: 0 }}
                        exit={{ opacity: 0, x: 12 }}
                        transition={{ duration: 0.18, ease: "easeOut" }}
                        className="bg-oats/30 custom-scrollbar absolute inset-0 flex flex-col overflow-y-auto p-4"
                      >
                        <div className="flex min-h-full w-full items-start justify-center">
                          {/* 详情页视窗 (iPhone 模拟器壳) */}
                          {viewMode === "detail" && (
                            <div className="border-charcoal relative my-1 flex aspect-[9/18.5] w-[320px] shrink-0 flex-col overflow-hidden rounded-[36px] border-[8px] bg-white shadow-2xl">
                              {/* 刘海 */}
                              <div className="bg-charcoal absolute top-0 left-1/2 z-20 flex h-5.5 w-28 -translate-x-1/2 items-center justify-center rounded-b-xl">
                                <span className="bg-charcoal-dark h-1.5 w-1.5 rounded-full border border-gray-800"></span>
                              </div>

                              {/* 模拟器状态条 */}
                              <div className="flex shrink-0 items-center justify-between border-b border-gray-100 bg-white/90 px-3 pt-7 pb-2 select-none">
                                <ChevronLeft className="text-charcoal size-4.5 cursor-pointer" />
                                <span className="text-xs font-bold">
                                  笔记详情
                                </span>
                                <XIcon className="text-charcoal size-4 opacity-0" />
                              </div>

                              {/* 手机内容滚动区 */}
                              <div className="custom-scrollbar relative flex flex-grow flex-col overflow-y-auto bg-white">
                                {/* 多图轮播 */}
                                <div className="bg-coral-light text-coral/80 group relative flex aspect-square w-full shrink-0 flex-col items-center justify-center overflow-hidden text-center">
                                  <img
                                    src={carouselImages[carouselIndex]}
                                    alt="露营"
                                    className="absolute inset-0 h-full w-full object-cover outline outline-1 outline-offset-[-1px] outline-black/5 transition-all duration-300 dark:outline-white/10"
                                  />
                                  <button
                                    onClick={() =>
                                      setCarouselIndex((prev) =>
                                        prev > 0
                                          ? prev - 1
                                          : carouselImages.length - 1,
                                      )
                                    }
                                    className="text-charcoal absolute top-1/2 left-2.5 flex size-11 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full bg-white/70 opacity-0 shadow-md transition-opacity group-hover:opacity-100 hover:bg-white"
                                  >
                                    <ChevronLeft className="size-3.5" />
                                  </button>
                                  <button
                                    onClick={() =>
                                      setCarouselIndex((prev) =>
                                        prev < carouselImages.length - 1
                                          ? prev + 1
                                          : 0,
                                      )
                                    }
                                    className="text-charcoal absolute top-1/2 right-2.5 flex size-11 -translate-y-1/2 cursor-pointer items-center justify-center rounded-full bg-white/70 opacity-0 shadow-md transition-opacity group-hover:opacity-100 hover:bg-white"
                                  >
                                    <ChevronRight className="size-3.5" />
                                  </button>
                                  <div className="absolute bottom-2 left-1/2 z-10 flex -translate-x-1/2 gap-1.5">
                                    {carouselImages.map((_, i) => (
                                      <span
                                        key={i}
                                        className={cn(
                                          "h-1.5 w-1.5 rounded-full transition-all",
                                          carouselIndex === i
                                            ? "bg-white"
                                            : "bg-white/50",
                                        )}
                                      ></span>
                                    ))}
                                  </div>
                                </div>

                                {/* 博主信息栏 */}
                                <div className="flex shrink-0 items-center justify-between border-b border-gray-50 px-3 py-2 select-none">
                                  <div className="flex items-center gap-2">
                                    <div className="bg-oats-dark text-charcoal flex size-6 items-center justify-center rounded-full text-xs font-bold">
                                      Z
                                    </div>
                                    <div>
                                      <div className="text-charcoal text-[10px] font-bold">
                                        张潇潇 (运营组)
                                      </div>
                                      <div className="text-[8px] text-gray-400">
                                        {isFeishuActionPending
                                          ? "已交给智能体，等待确认/执行"
                                          : "尚未提交飞书操作"}
                                      </div>
                                    </div>
                                  </div>
                                </div>

                                {/* 动态文本预览区 / 编辑入口 */}
                                {!isEditingText ? (
                                  <button
                                    type="button"
                                    onClick={() => setIsEditingText(true)}
                                    className="group hover:bg-oats/10 relative flex-grow cursor-pointer p-3 text-left transition-colors"
                                  >
                                    <div className="absolute top-2 right-2 flex items-center gap-1.5">
                                      {isDirty && (
                                        <span className="relative flex h-2 w-2">
                                          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"></span>
                                          <span
                                            className="relative inline-flex h-2 w-2 rounded-full bg-amber-500"
                                            title="本地草稿有未同步的修改"
                                          ></span>
                                        </span>
                                      )}
                                      <div className="text-coral bg-coral-light border-coral/10 flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[9px] opacity-0 transition-opacity select-none group-hover:opacity-100">
                                        <span>原位编辑 ✍️</span>
                                      </div>
                                    </div>
                                    <span className="text-charcoal mb-2 block text-xs leading-snug font-bold">
                                      {draftTitle}
                                    </span>
                                    <span className="text-charcoal-light block text-[10px] leading-relaxed whitespace-pre-wrap">
                                      {draftContent}
                                    </span>
                                  </button>
                                ) : (
                                  /* 原位富文本编辑器表单 */
                                  <div className="border-oats-dark bg-oats-light/60 flex flex-col gap-2.5 border-t p-3 transition-all">
                                    <div className="flex items-center justify-between text-[10px]">
                                      <div className="flex items-center gap-1.5">
                                        <span className="font-bold text-gray-500">
                                          ✏️ 原位修改文案
                                        </span>
                                        {isDirty && (
                                          <span
                                            className="relative flex h-2 w-2"
                                            title="本地草稿有未同步的修改"
                                          >
                                            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75"></span>
                                            <span className="relative inline-flex h-2 w-2 rounded-full bg-amber-500"></span>
                                          </span>
                                        )}
                                      </div>
                                      <div
                                        className={cn(
                                          "flex items-center gap-1.5 rounded border px-2 py-0.5 transition-all duration-300",
                                          draftContent.length > 1000
                                            ? "animate-shake border-red-200 bg-red-50 text-red-700"
                                            : draftContent.length >= 800
                                              ? "border-amber-200 bg-amber-50 text-amber-700"
                                              : "border-green-200 bg-green-50 text-green-700",
                                        )}
                                      >
                                        <svg
                                          className="size-3.5 -rotate-90 transform select-none"
                                          viewBox="0 0 20 20"
                                        >
                                          <circle
                                            cx="10"
                                            cy="10"
                                            r="8"
                                            fill="none"
                                            stroke={
                                              draftContent.length > 1000
                                                ? "#FCA5A5"
                                                : draftContent.length >= 800
                                                  ? "#FDE68A"
                                                  : "#A7F3D0"
                                            }
                                            strokeWidth="2.5"
                                            className="opacity-40"
                                          />
                                          <motion.circle
                                            cx="10"
                                            cy="10"
                                            r="8"
                                            fill="none"
                                            stroke={
                                              draftContent.length > 1000
                                                ? "#EF4444"
                                                : draftContent.length >= 800
                                                  ? "#F59E0B"
                                                  : "#10B981"
                                            }
                                            strokeWidth="2.5"
                                            strokeDasharray="50.265"
                                            initial={{
                                              strokeDashoffset: 50.265,
                                            }}
                                            animate={{
                                              strokeDashoffset:
                                                50.265 -
                                                (Math.min(
                                                  draftContent.length,
                                                  1000,
                                                ) /
                                                  1000) *
                                                  50.265,
                                            }}
                                            transition={{
                                              type: "spring",
                                              stiffness: 120,
                                              damping: 15,
                                            }}
                                            strokeLinecap="round"
                                          />
                                        </svg>
                                        <span className="font-tabular text-[9px] font-semibold">
                                          字数：{draftContent.length} / 1000 字{" "}
                                          {draftContent.length > 1000 && "⚠️"}
                                        </span>
                                      </div>
                                    </div>
                                    <input
                                      type="text"
                                      value={draftTitle}
                                      onChange={(e) =>
                                        setDraftTitle(e.target.value)
                                      }
                                      className="border-coral-light/60 focus:border-coral w-full rounded-lg border bg-white p-1.5 text-[10px] font-bold focus:outline-none"
                                    />
                                    <textarea
                                      ref={textareaRef}
                                      id="edit-body-input"
                                      value={draftContent}
                                      onChange={(e) =>
                                        setDraftContent(e.target.value)
                                      }
                                      onPaste={handleEditBodyPaste}
                                      className="border-coral-light/60 focus:border-coral custom-scrollbar w-full resize-none rounded-lg border bg-white p-2 text-[10px] transition-[height] duration-100 focus:outline-none"
                                      style={{ minHeight: "160px" }}
                                    />

                                    {/* 快捷 Emoji 点击 */}
                                    <div className="flex flex-col gap-1">
                                      <span className="text-[8px] font-semibold text-gray-400 select-none">
                                        点击快速插入高频 Emoji：
                                      </span>
                                      <div className="border-coral-light/40 flex flex-wrap gap-1 rounded-lg border bg-white p-1.5 text-xs select-none">
                                        {[
                                          "🍠",
                                          "⛺",
                                          "☕",
                                          "✨",
                                          "🌿",
                                          "👇",
                                          "📝",
                                          "🔥",
                                          "🌟",
                                        ].map((em) => (
                                          <button
                                            key={em}
                                            type="button"
                                            onClick={() =>
                                              handleInsertEmoji(em)
                                            }
                                            aria-label={`插入 ${em}`}
                                            className="flex min-h-7 min-w-7 cursor-pointer items-center justify-center rounded-md p-0.5 transition-transform hover:scale-125"
                                          >
                                            {em}
                                          </button>
                                        ))}
                                      </div>
                                    </div>

                                    {/* 话题标签智能推荐 */}
                                    <div className="flex flex-col gap-1">
                                      <span className="text-[8px] font-semibold text-gray-400 select-none">
                                        基于爆款规律推荐 Tag：
                                      </span>
                                      <div className="flex flex-wrap gap-1">
                                        {[
                                          "露营分享",
                                          "户外美学",
                                          "周末去哪玩",
                                          "性价比装备",
                                        ].map((tag) => (
                                          <button
                                            key={tag}
                                            type="button"
                                            onClick={() => handleAppendTag(tag)}
                                            className="flex cursor-pointer items-center gap-0.5 rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-[8px] text-sky-700 hover:bg-sky-100"
                                          >
                                            <span>#{tag}</span>
                                            <Plus className="size-2" />
                                          </button>
                                        ))}
                                      </div>
                                    </div>

                                    {/* 按钮组 */}
                                    <div className="flex justify-end gap-2 pt-1">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          setDraftTitle(lastSavedTitle);
                                          setDraftContent(lastSavedContent);
                                          setIsEditingText(false);
                                        }}
                                        className="text-charcoal animate-in fade-in-0 cursor-pointer rounded-lg bg-gray-100 px-3 py-1 text-[10px] transition-colors duration-200 hover:bg-gray-200"
                                      >
                                        取消
                                      </button>
                                      <button
                                        type="button"
                                        onClick={() => setIsEditingText(false)}
                                        className="bg-coral hover:bg-coral-hover cursor-pointer rounded-lg px-3.5 py-1 text-[10px] font-semibold text-white shadow-xs transition-colors"
                                      >
                                        保存
                                      </button>
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          )}

                          {/* 瀑布流网格视图 */}
                          {viewMode === "feed" && (
                            <div className="border-charcoal bg-oats/60 relative my-1 flex aspect-[9/18.5] w-[320px] shrink-0 flex-col overflow-hidden rounded-[36px] border-[8px] shadow-2xl">
                              {/* 刘海 */}
                              <div className="bg-charcoal absolute top-0 left-1/2 z-20 flex h-5.5 w-28 -translate-x-1/2 items-center justify-center rounded-b-xl">
                                <span className="bg-charcoal-dark h-1.5 w-1.5 rounded-full border border-gray-800"></span>
                              </div>

                              {/* 发现页头 */}
                              <div className="flex shrink-0 items-center justify-center border-b border-gray-100 bg-white/95 px-4 pt-7 pb-2 text-[10px] font-bold select-none">
                                <span className="text-charcoal border-coral border-b pb-0.5">
                                  发现
                                </span>
                              </div>

                              {/* 瀑布流双列卡片 */}
                              <div className="bg-oats-dark/20 custom-scrollbar grid flex-grow grid-cols-2 gap-2 overflow-y-auto p-2">
                                {/* 首个卡片：展示当前笔记的高保真预览 */}
                                <button
                                  type="button"
                                  onClick={() => setViewMode("detail")}
                                  className="animate-in fade-in-0 flex cursor-pointer flex-col overflow-hidden rounded-lg border border-gray-100 bg-white text-left shadow-xs transition-transform duration-200 hover:scale-[1.01]"
                                >
                                  <div className="relative aspect-[3/4] w-full overflow-hidden">
                                    <img
                                      src={carouselImages[0]}
                                      alt="露营"
                                      className="h-full w-full object-cover outline outline-1 outline-offset-[-1px] outline-black/5 dark:outline-white/10"
                                    />
                                  </div>
                                  <div className="flex flex-col gap-1 p-1.5">
                                    <h4 className="text-charcoal line-clamp-2 h-6 text-[9px] leading-tight font-bold">
                                      {draftTitle}
                                    </h4>
                                    <div className="text-[7px] text-gray-400 select-none">
                                      <span className="max-w-[50px] truncate">
                                        张潇潇
                                      </span>
                                    </div>
                                  </div>
                                </button>

                                {/* 假卡片 1 */}
                                <div className="flex flex-col overflow-hidden rounded-lg border border-gray-100 bg-white opacity-60 shadow-xs">
                                  <div className="aspect-[4/5] w-full bg-gray-200"></div>
                                  <div className="p-1.5">
                                    <div className="mb-1.5 h-2 w-4/5 rounded bg-gray-200"></div>
                                    <div className="h-1.5 w-2/5 rounded bg-gray-200"></div>
                                  </div>
                                </div>

                                {/* 假卡片 2 */}
                                <div className="flex flex-col overflow-hidden rounded-lg border border-gray-100 bg-white opacity-60 shadow-xs">
                                  <div className="aspect-square w-full bg-gray-200"></div>
                                  <div className="p-1.5">
                                    <div className="mb-1.5 h-2 w-4/5 rounded bg-gray-200"></div>
                                    <div className="h-1.5 w-2/5 rounded bg-gray-200"></div>
                                  </div>
                                </div>
                              </div>
                            </div>
                          )}
                        </div>
                      </motion.div>
                    ) : rightTab === "feishu" ? (
                      <RightInspector />
                    ) : (
                      <EvidenceInspector />
                    )}
                  </AnimatePresence>
                </div>
              </aside>
            )}
          </main>
        </div>
      </ThreadActionsProvider>
    </ThreadContext.Provider>
  );
}
