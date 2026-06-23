import { v4 as uuidv4 } from "uuid";
import { useEffect, useRef, useState, FormEvent, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useStreamContext } from "@/providers/Stream";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import {
  ensureToolCallsHaveResponses,
} from "@/lib/ensure-tool-responses";
import {
  XIcon,
  ChevronLeft,
  ChevronRight,
  Heart,
  Star,
  MessageSquare,
  Plus,
} from "lucide-react";
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
  const [rightTab, setRightTab] = useState<"mock" | "feishu" | "evidence">("mock");
  const [selectedEvidence, setSelectedEvidence] = useState<SourceEvidence | null>(null);
  const [viewMode, setViewMode] = useState<"detail" | "feed">("detail");
  const [isEditingText, setIsEditingText] = useState(false);

  // 当前动态编辑的选题和正文
  const [draftTitle, setDraftTitle] = useState("精致露营「搬家式」装备清单");
  const [draftContent, setDraftContent] = useState("夏天太适合露营啦！⛺但是作为一个精致的搬家式露营玩家，带什么装备去真的大有讲究！今天就给大家盘点一下我私藏的「搬家式」露营好物，少带一件体验感都打折！\n\n👇精致露营必带清单：\n1️⃣ 双顶充气天幕：不仅防雨防晒，最重要是拍照真的超出片！空间很大，容纳8个人也宽敞。");

  // 多图轮播状态
  const [carouselIndex, setCarouselIndex] = useState(0);
  const carouselImages = [
    "https://images.unsplash.com/photo-1504280390367-361c6d9f38f4?auto=format&fit=crop&w=500&q=80",
    "https://images.unsplash.com/photo-1533873984035-25970ab07461?auto=format&fit=crop&w=500&q=80",
    "https://images.unsplash.com/photo-1478131143081-80f7f84ca84d?auto=format&fit=crop&w=500&q=80"
  ];

  // 飞书群组与通知发送状态
  const [feishuChats, setFeishuChats] = useState<{ chat_id: string; name: string }[]>([]);
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

  // 底部点赞收藏状态变量
  const [likeCount, setLikeCount] = useState(1280);
  const [isLiked, setIsLiked] = useState(false);
  const [collectCount, setCollectCount] = useState(342);
  const [isCollected, setIsCollected] = useState(false);
  const [showPlusOne, setShowPlusOne] = useState(false);

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
        const firstLine = lines[0].replace(/^[#\s*✨🍠⛺☕🌿👇📝🌟🔥🚗]*/gu, "").trim();
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
    localStorage.setItem("xhs_autosave_draft", JSON.stringify({ title: draftTitle, content: draftContent }));
    if (lastSavedContent && (draftContent !== lastSavedContent || draftTitle !== lastSavedTitle)) {
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

  const setThreadId = useCallback((id: string | null) => {
    if (isDirty) {
      const ok = window.confirm("您有尚未同步至飞书的本地修改，切换或关闭对话将遗失这些改动。是否确定继续？");
      if (!ok) return;
    }
    _setThreadId(id);
    setIsEditingText(false);
    setView(null);
    setIsDirty(false);
  }, [isDirty, _setThreadId, setView]);

  // 监听 AI 流式更新，实时同步至右侧模拟器预览
  useEffect(() => {
    if (messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.type === "ai" && typeof lastMsg.content === "string") {
        const text = lastMsg.content.trim();
        const lines = text.split("\n");
        if (lines.length > 0) {
          // 智能截取第一行作为手机卡片的标题
          const firstLine = lines[0].replace(/^[#\s*✨🍠⛺☕🌿👇📝🌟🔥🚗]*/gu, "").trim();
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
      }
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
  };

  // 执行 Ctrl+P 智能指令
  const handleExecuteCommand = (cmd: string) => {
    setShowCommandPalette(false);
    if (cmd === "polish") {
      toast.success("执行 [/polish 智能润色] 指令中，流式修改已发送...");
      submitText(`请帮我把右侧这段文案进行智能润色，使标题更吸引眼球，正文增加一些活泼的 Emoji：\n\n${draftContent}`);
    } else if (cmd === "shorten") {
      toast.success("执行 [/shorten 文案瘦身] 指令中...");
      submitText(`请帮我针对以下文案，生成 5 个在小红书极具热度的话题标签：\n\n${draftContent}`);
    } else if (cmd === "tags") {
      toast.success("执行 [/tags 话题推荐] 指令中...");
      submitText(`请帮我针对以下文案，生成 5 个在小红书极具热度的话题标签：\n\n${draftContent}`);
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
        ].join("\n")
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
      ].join("\n")
    );
    setIsFeishuActionPending(true);
    setIsSendingNotification(false);
    toast.success("已交给智能体，等待确认/执行。");
  };

  // Emoji 点选插入
  const handleInsertEmoji = (emoji: string) => {
    const textarea = document.getElementById("edit-body-input") as HTMLTextAreaElement;
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
      }
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
        likeCount,
        setLikeCount,
        isLiked,
        setIsLiked,
        collectCount,
        setCollectCount,
        isCollected,
        setIsCollected,
        showPlusOne,
        setShowPlusOne,
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
        <div className="flex h-screen w-full overflow-hidden bg-oats relative">

          {/* 物理抛物线飞行动效元素 */}
          <AnimatePresence>
            {isFlying && (
              <motion.div
                initial={{ left: "25%", top: "85%", scale: 1.2, opacity: 1 }}
                animate={{
                  left: "78%",
                  top: "15%",
                  scale: 0.35,
                  opacity: 0.15
                }}
                exit={{ opacity: 0 }}
                transition={{
                  left: { duration: 0.8, ease: "linear" },
                  top: { duration: 0.8, ease: [0.15, 0.85, 0.45, 1.0] },
                  scale: { duration: 0.8, ease: "easeInOut" },
                  opacity: { duration: 0.8, ease: "easeIn" }
                }}
                className="absolute z-50 bg-coral text-white text-[11px] px-3.5 py-2 rounded-full font-bold shadow-lg pointer-events-none"
              >
                🍠 正在同步...
              </motion.div>
            )}
          </AnimatePresence>

          {/* Ctrl+P 智能润色工具箱悬浮弹窗 */}
          <AnimatePresence>
            {showCommandPalette && (
              <div className="absolute inset-0 z-50 flex items-center justify-center bg-charcoal-dark/30 backdrop-blur-xs">
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: -20 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: -20 }}
                  className="w-[500px] bg-white border border-coral-light rounded-2xl shadow-2xl p-4 flex flex-col gap-3"
                >
                  <div className="flex items-center gap-2 border-b pb-2">
                    <span className="text-sm bg-coral-light text-coral font-bold px-2 py-0.5 rounded">Ctrl+P</span>
                    <input
                      type="text"
                      placeholder="搜索润色指令 (e.g. /polish, /shorten)..."
                      value={cmdSearch}
                      onChange={(e) => setCmdSearch(e.target.value)}
                      className="flex-1 text-sm border-none outline-none focus:ring-0"
                      autoFocus
                    />
                  </div>
                  <div className="flex flex-col gap-1 text-xs">
                    <button
                      onClick={() => handleExecuteCommand("polish")}
                      className="flex items-center justify-between p-2.5 rounded-xl hover:bg-oats text-left transition-colors cursor-pointer group"
                    >
                      <div>
                        <span className="font-bold text-coral">/polish</span>
                        <span className="text-charcoal-light ml-2">智能精细润色文案</span>
                      </div>
                      <span className="text-[10px] text-gray-400 group-hover:text-coral font-medium">执行 Enter</span>
                    </button>
                    <button
                      onClick={() => handleExecuteCommand("shorten")}
                      className="flex items-center justify-between p-2.5 rounded-xl hover:bg-oats text-left transition-colors cursor-pointer group"
                    >
                      <div>
                        <span className="font-bold text-coral">/shorten</span>
                        <span className="text-charcoal-light ml-2">文案精简瘦身</span>
                      </div>
                      <span className="text-[10px] text-gray-400 group-hover:text-coral font-medium">执行 Enter</span>
                    </button>
                    <button
                      onClick={() => handleExecuteCommand("tags")}
                      className="flex items-center justify-between p-2.5 rounded-xl hover:bg-oats text-left transition-colors cursor-pointer group"
                    >
                      <div>
                        <span className="font-bold text-coral">/tags</span>
                        <span className="text-charcoal-light ml-2">自动匹配热门话题</span>
                      </div>
                      <span className="text-[10px] text-gray-400 group-hover:text-coral font-medium">执行 Enter</span>
                    </button>
                  </div>
                  <div className="flex justify-end text-[10px] text-gray-400 border-t pt-2">
                    按 Esc 键或点击空白关闭
                  </div>
                </motion.div>
              </div>
            )}
          </AnimatePresence>

          {/* 侧边栏 */}
          <div className="relative hidden lg:flex">
            <motion.div
              className="absolute z-20 h-full overflow-hidden border-r bg-sidebar"
              style={{ width: 300 }}
              animate={{ x: chatHistoryOpen ? 0 : -300 }}
              initial={{ x: -300 }}
              transition={isLargeScreen ? { type: "spring", stiffness: 300, damping: 30 } : { duration: 0 }}
            >
              <div className="relative h-full" style={{ width: 300 }}>
                <ThreadHistory onThreadClick={setThreadId} />
              </div>
            </motion.div>
          </div>

          {/* 主画布布局：双视窗分屏展示 */}
          <div
            className={cn(
              "grid w-full transition-all duration-500",
              (chatStarted && !view) ? "grid-cols-[1fr_480px]" : "grid-cols-[1fr_0px]"
            )}
          >
            {/* 左侧：聊天面板 */}
            <motion.div
              className={cn(
                "relative flex min-w-0 flex-1 flex-col overflow-hidden",
                !chatStarted && "grid-rows-[1fr]"
              )}
              layout={isLargeScreen}
              animate={{
                marginLeft: chatHistoryOpen ? (isLargeScreen ? 300 : 0) : 0,
                width: chatHistoryOpen ? (isLargeScreen ? "calc(100% - 300px)" : "100%") : "100%"
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
            <div className="relative flex flex-col border-l border-coral-light/50 bg-white shadow-lg overflow-hidden h-full z-10 w-[480px]">
              {/* Tab 页头 */}
              <div className="flex items-center justify-between border-b border-coral-light/60 bg-oats-light/20 px-3 py-2 shrink-0 select-none">
                <div className="flex bg-oats-dark/60 p-1 rounded-xl gap-1 relative border border-coral-light/40 select-none">
                  <button
                    onClick={() => setRightTab("mock")}
                    className="relative px-2 py-1.5 rounded-lg text-[10px] font-bold transition-all cursor-pointer z-10 border-none bg-transparent outline-none"
                  >
                    {rightTab === "mock" && (
                      <motion.div
                        layoutId="activeTabIndicator"
                        className="absolute inset-0 bg-white rounded-lg shadow-sm z-[-1]"
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    )}
                    <span className={cn("transition-colors duration-200", rightTab === "mock" ? "text-coral" : "text-gray-500 hover:text-charcoal")}>
                      📱 手机预览
                    </span>
                  </button>
                  <button
                    onClick={() => setRightTab("feishu")}
                    className="relative px-2 py-1.5 rounded-lg text-[10px] font-bold transition-all cursor-pointer z-10 border-none bg-transparent outline-none"
                  >
                    {rightTab === "feishu" && (
                      <motion.div
                        layoutId="activeTabIndicator"
                        className="absolute inset-0 bg-white rounded-lg shadow-sm z-[-1]"
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    )}
                    <span className={cn("transition-colors duration-200", rightTab === "feishu" ? "text-coral" : "text-gray-500 hover:text-charcoal")}>
                      🔗 飞书协作
                    </span>
                  </button>
                  <button
                    onClick={() => setRightTab("evidence")}
                    className="relative px-2 py-1.5 rounded-lg text-[10px] font-bold transition-all cursor-pointer z-10 border-none bg-transparent outline-none"
                  >
                    {rightTab === "evidence" && (
                      <motion.div
                        layoutId="activeTabIndicator"
                        className="absolute inset-0 bg-white rounded-lg shadow-sm z-[-1]"
                        transition={{ type: "spring", stiffness: 380, damping: 30 }}
                      />
                    )}
                    <span className={cn("transition-colors duration-200", rightTab === "evidence" ? "text-coral" : "text-gray-500 hover:text-charcoal")}>
                      📊 依据分析
                    </span>
                  </button>
                </div>

                {/* 双视窗预览模式切换（仅在预览 Tab 下可见） */}
                {rightTab === "mock" && (
                  <div className="flex items-center gap-0.5 bg-oats border border-coral-light/60 rounded-xl p-0.5 text-[9px]">
                    <button
                      onClick={() => setViewMode("detail")}
                      className={cn(
                        "px-1.5 py-0.5 rounded-lg font-bold transition-colors cursor-pointer",
                        viewMode === "detail" ? "bg-white text-coral shadow-xs" : "text-gray-500"
                      )}
                    >
                      详情页
                    </button>
                    <button
                      onClick={() => setViewMode("feed")}
                      className={cn(
                        "px-1.5 py-0.5 rounded-lg font-bold transition-colors cursor-pointer",
                        viewMode === "feed" ? "bg-white text-coral shadow-xs" : "text-gray-500"
                      )}
                    >
                      瀑布流
                    </button>
                  </div>
                )}
              </div>

              {/* Tab 视图面板，使用 AnimatePresence 进行平滑滑入淡出过渡 */}
              <div className="flex-grow overflow-hidden relative w-full">
                <AnimatePresence mode="wait">
                  {rightTab === "mock" ? (
                    <motion.div
                      key="mock-tab"
                      initial={{ opacity: 0, x: -12 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 12 }}
                      transition={{ duration: 0.18, ease: "easeOut" }}
                      className="absolute inset-0 flex flex-col overflow-y-auto p-4 bg-oats/30 custom-scrollbar"
                    >
                      <div className="flex justify-center items-start w-full min-h-full">

                        {/* 详情页视窗 (iPhone 模拟器壳) */}
                        {viewMode === "detail" && (
                          <div className="w-[320px] border-[8px] border-charcoal rounded-[36px] bg-white shadow-2xl overflow-hidden relative flex flex-col shrink-0 aspect-[9/18.5] my-1">

                            {/* 刘海 */}
                            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-28 h-5.5 bg-charcoal rounded-b-xl z-20 flex justify-center items-center">
                              <span className="w-1.5 h-1.5 rounded-full bg-charcoal-dark border border-gray-800"></span>
                            </div>

                            {/* 模拟器状态条 */}
                            <div className="pt-7 pb-2 px-3 border-b border-gray-100 flex items-center justify-between bg-white/90 shrink-0 select-none">
                              <ChevronLeft className="size-4.5 text-charcoal cursor-pointer" />
                              <span className="text-xs font-bold">笔记详情</span>
                              <XIcon className="size-4 text-charcoal opacity-0" />
                            </div>

                            {/* 手机内容滚动区 */}
                            <div className="flex-grow overflow-y-auto bg-white flex flex-col relative custom-scrollbar">

                              {/* 多图轮播 */}
                              <div className="w-full aspect-square bg-coral-light flex flex-col items-center justify-center text-center text-coral/80 relative overflow-hidden shrink-0 group">
                                <img
                                  src={carouselImages[carouselIndex]}
                                  alt="露营"
                                  className="w-full h-full object-cover absolute inset-0 transition-all duration-300 outline outline-1 outline-black/5 dark:outline-white/10 outline-offset-[-1px]"
                                />
                                <button
                                  onClick={() => setCarouselIndex((prev) => (prev > 0 ? prev - 1 : carouselImages.length - 1))}
                                  className="absolute left-2.5 top-1/2 -translate-y-1/2 bg-white/70 hover:bg-white text-charcoal p-1.5 rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                                >
                                  <ChevronLeft className="size-3.5" />
                                </button>
                                <button
                                  onClick={() => setCarouselIndex((prev) => (prev < carouselImages.length - 1 ? prev + 1 : 0))}
                                  className="absolute right-2.5 top-1/2 -translate-y-1/2 bg-white/70 hover:bg-white text-charcoal p-1.5 rounded-full shadow-md opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                                >
                                  <ChevronRight className="size-3.5" />
                                </button>
                                <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1.5 z-10">
                                  {carouselImages.map((_, i) => (
                                    <span
                                      key={i}
                                      className={cn(
                                        "w-1.5 h-1.5 rounded-full transition-all",
                                        carouselIndex === i ? "bg-white" : "bg-white/50"
                                      )}
                                    ></span>
                                  ))}
                                </div>
                              </div>

                              {/* 博主信息栏 */}
                              <div className="px-3 py-2 border-b border-gray-50 flex items-center justify-between shrink-0 select-none">
                                <div className="flex items-center gap-2">
                                  <div className="size-6 rounded-full bg-oats-dark text-charcoal font-bold text-xs flex items-center justify-center">Z</div>
                                  <div>
                                    <div className="text-[10px] font-bold text-charcoal">张潇潇 (运营组)</div>
                                    <div className="text-[8px] text-gray-400">
                                      {isFeishuActionPending ? "已交给智能体，等待确认/执行" : "尚未提交飞书操作"}
                                    </div>
                                  </div>
                                </div>
                                <button className="border border-coral text-coral px-2.5 py-0.5 rounded-full text-[9px] font-semibold">关注</button>
                              </div>

                              {/* 动态文本预览区 / 编辑入口 */}
                              {!isEditingText ? (
                                <div
                                  onClick={() => setIsEditingText(true)}
                                  className="p-3 flex-grow cursor-pointer hover:bg-oats/10 transition-colors relative group"
                                >
                                  <div className="absolute top-2 right-2 flex items-center gap-1.5">
                                    {isDirty && (
                                      <span className="relative flex h-2 w-2">
                                        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                                        <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500" title="本地草稿有未同步的修改"></span>
                                      </span>
                                    )}
                                    <div className="text-[9px] text-coral bg-coral-light border border-coral/10 px-1.5 py-0.5 rounded-md opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1 select-none">
                                      <span>原位编辑 ✍️</span>
                                    </div>
                                  </div>
                                  <h3 className="text-xs font-bold text-charcoal mb-2 leading-snug">{draftTitle}</h3>
                                  <p className="text-[10px] text-charcoal-light leading-relaxed whitespace-pre-wrap">{draftContent}</p>
                                </div>
                              ) : (
                                /* 原位富文本编辑器表单 */
                                <div className="p-3 flex flex-col gap-2.5 border-t border-oats-dark bg-oats-light/60 transition-all">
                                  <div className="flex justify-between items-center text-[10px]">
                                    <div className="flex items-center gap-1.5">
                                      <span className="font-bold text-gray-500">✏️ 原位修改文案</span>
                                      {isDirty && (
                                        <span className="relative flex h-2 w-2" title="本地草稿有未同步的修改">
                                          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75"></span>
                                          <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-500"></span>
                                        </span>
                                      )}
                                    </div>
                                    <div
                                      className={cn(
                                        "flex items-center gap-1.5 border px-2 py-0.5 rounded transition-all duration-300",
                                        draftContent.length > 1000
                                          ? "bg-red-50 text-red-700 border-red-200 animate-shake"
                                          : draftContent.length >= 800
                                          ? "bg-amber-50 text-amber-700 border-amber-200"
                                          : "bg-green-50 text-green-700 border-green-200"
                                      )}
                                    >
                                      <svg className="size-3.5 transform -rotate-90 select-none" viewBox="0 0 20 20">
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
                                          initial={{ strokeDashoffset: 50.265 }}
                                          animate={{
                                            strokeDashoffset: 50.265 - (Math.min(draftContent.length, 1000) / 1000) * 50.265
                                          }}
                                          transition={{ type: "spring", stiffness: 120, damping: 15 }}
                                          strokeLinecap="round"
                                        />
                                      </svg>
                                      <span className="text-[9px] font-semibold font-tabular">
                                        字数：{draftContent.length} / 1000 字 {draftContent.length > 1000 && "⚠️"}
                                      </span>
                                    </div>
                                  </div>
                                  <input
                                    type="text"
                                    value={draftTitle}
                                    onChange={(e) => setDraftTitle(e.target.value)}
                                    className="w-full text-[10px] font-bold border border-coral-light/60 rounded-lg p-1.5 bg-white focus:outline-none focus:border-coral"
                                  />
                                  <textarea
                                    ref={textareaRef}
                                    id="edit-body-input"
                                    value={draftContent}
                                    onChange={(e) => setDraftContent(e.target.value)}
                                    onPaste={handleEditBodyPaste}
                                    className="w-full text-[10px] border border-coral-light/60 rounded-lg p-2 bg-white focus:outline-none focus:border-coral resize-none custom-scrollbar transition-[height] duration-100"
                                    style={{ minHeight: "160px" }}
                                  />

                                  {/* 快捷 Emoji 点击 */}
                                  <div className="flex flex-col gap-1">
                                    <span className="text-[8px] text-gray-400 font-semibold select-none">点击快速插入高频 Emoji：</span>
                                    <div className="flex flex-wrap gap-1 bg-white p-1.5 border border-coral-light/40 rounded-lg text-xs select-none">
                                      {["🍠", "⛺", "☕", "✨", "🌿", "👇", "📝", "🔥", "🌟"].map((em) => (
                                        <span
                                          key={em}
                                          onClick={() => handleInsertEmoji(em)}
                                          className="cursor-pointer hover:scale-125 transition-transform p-0.5"
                                        >
                                          {em}
                                        </span>
                                      ))}
                                    </div>
                                  </div>

                                  {/* 话题标签智能推荐 */}
                                  <div className="flex flex-col gap-1">
                                    <span className="text-[8px] text-gray-400 font-semibold select-none">基于爆款规律推荐 Tag：</span>
                                    <div className="flex flex-wrap gap-1">
                                      {["露营分享", "户外美学", "周末去哪玩", "性价比装备"].map((tag) => (
                                        <button
                                          key={tag}
                                          type="button"
                                          onClick={() => handleAppendTag(tag)}
                                          className="text-[8px] bg-sky-50 hover:bg-sky-100 text-sky-700 border border-sky-200 px-2 py-0.5 rounded-full flex items-center gap-0.5 cursor-pointer"
                                        >
                                          <span>#{tag}</span>
                                          <Plus className="size-2" />
                                        </button>
                                      ))}
                                    </div>
                                  </div>

                                  {/* 按钮组 */}
                                  <div className="flex gap-2 justify-end pt-1">
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setDraftTitle(lastSavedTitle);
                                        setDraftContent(lastSavedContent);
                                        setIsEditingText(false);
                                      }}
                                      className="bg-gray-100 hover:bg-gray-200 text-charcoal text-[10px] px-3 py-1 rounded-lg transition-colors cursor-pointer animate-in fade-in-0 duration-200"
                                    >
                                      取消
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setIsEditingText(false)}
                                      className="bg-coral hover:bg-coral-hover text-white text-[10px] px-3.5 py-1 rounded-lg font-semibold shadow-xs transition-colors cursor-pointer"
                                    >
                                      保存
                                    </button>
                                  </div>
                                </div>
                              )}

                            </div>

                            {/* 模拟器底部互动栏 */}
                            <div className="h-10 border-t border-gray-100 flex items-center justify-between px-5 bg-white shrink-0 text-gray-400 select-none relative">

                              {/* Plus One floating animation */}
                              <AnimatePresence>
                                {showPlusOne && (
                                  <motion.span
                                    initial={{ opacity: 0, y: 0 }}
                                    animate={{ opacity: 1, y: -25 }}
                                    exit={{ opacity: 0 }}
                                    className="absolute left-6 text-[10px] font-bold text-coral"
                                  >
                                    +1
                                  </motion.span>
                                )}
                              </AnimatePresence>

                              <button
                                type="button"
                                onClick={() => {
                                  if (!isLiked) {
                                    setShowPlusOne(true);
                                    setTimeout(() => setShowPlusOne(false), 800);
                                  }
                                  setIsLiked(!isLiked);
                                  setLikeCount((c) => isLiked ? c - 1 : c + 1);
                                }}
                                className="flex items-center gap-1 cursor-pointer hover:text-coral transition-colors outline-none border-none bg-transparent"
                              >
                                <motion.div
                                  animate={{ scale: isLiked ? [1, 1.45, 0.9, 1.1, 1] : 1 }}
                                  transition={{ duration: 0.4 }}
                                >
                                  <Heart className={cn("size-3.5 transition-colors", isLiked ? "text-coral fill-coral" : "text-gray-400")} />
                                </motion.div>
                                <span className={cn("text-[8px] font-medium font-tabular", isLiked ? "text-coral" : "text-gray-400")}>
                                  {likeCount >= 1000 ? `${(likeCount / 1000).toFixed(1)}k` : likeCount}
                                </span>
                              </button>

                              <button
                                type="button"
                                onClick={() => {
                                  setIsCollected(!isCollected);
                                  setCollectCount((c) => isCollected ? c - 1 : c + 1);
                                }}
                                className="flex items-center gap-1 cursor-pointer hover:text-coral transition-colors outline-none border-none bg-transparent"
                              >
                                <motion.div
                                  animate={{ scale: isCollected ? [1, 1.45, 0.9, 1.1, 1] : 1 }}
                                  transition={{ duration: 0.4 }}
                                >
                                  <Star className={cn("size-3.5 transition-colors", isCollected ? "text-coral fill-coral" : "text-gray-400")} />
                                </motion.div>
                                <span className={cn("text-[8px] font-medium font-tabular", isCollected ? "text-coral" : "text-gray-400")}>
                                  {collectCount}
                                </span>
                              </button>

                              <div className="flex items-center gap-1 text-gray-400 select-none">
                                <MessageSquare className="size-3.5" />
                                <span className="text-[8px] font-medium font-tabular">88</span>
                              </div>
                            </div>

                          </div>
                        )}

                        {/* 瀑布流网格视图 */}
                        {viewMode === "feed" && (
                          <div className="w-[320px] border-[8px] border-charcoal rounded-[36px] bg-oats/60 shadow-2xl overflow-hidden relative flex flex-col shrink-0 aspect-[9/18.5] my-1">
                            {/* 刘海 */}
                            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-28 h-5.5 bg-charcoal rounded-b-xl z-20 flex justify-center items-center">
                              <span className="w-1.5 h-1.5 rounded-full bg-charcoal-dark border border-gray-800"></span>
                            </div>

                            {/* 发现页头 */}
                            <div className="pt-7 pb-2 px-4 border-b border-gray-100 flex items-center justify-center gap-4 bg-white/95 shrink-0 text-[10px] font-bold select-none">
                              <span className="text-gray-400">关注</span>
                              <span className="text-charcoal border-b border-coral pb-0.5">发现</span>
                              <span className="text-gray-400">附近</span>
                            </div>

                            {/* 瀑布流双列卡片 */}
                            <div className="flex-grow overflow-y-auto p-2 grid grid-cols-2 gap-2 bg-oats-dark/20 custom-scrollbar">

                              {/* 首个卡片：展示当前笔记的高保真预览 */}
                              <div
                                onClick={() => setViewMode("detail")}
                                className="bg-white rounded-lg overflow-hidden shadow-xs flex flex-col border border-gray-100 cursor-pointer hover:scale-[1.01] transition-transform animate-in fade-in-0 duration-200"
                              >
                                <div className="w-full aspect-[3/4] overflow-hidden relative">
                                  <img src={carouselImages[0]} alt="露营" className="w-full h-full object-cover outline outline-1 outline-black/5 dark:outline-white/10 outline-offset-[-1px]" />
                                </div>
                                <div className="p-1.5 flex flex-col gap-1">
                                  <h4 className="text-[9px] font-bold leading-tight text-charcoal h-6 line-clamp-2">{draftTitle}</h4>
                                  <div className="flex justify-between items-center text-[7px] text-gray-400 select-none">
                                    <span className="truncate max-w-[50px]">张潇潇</span>
                                    <div className="flex items-center gap-0.5"><Heart className="size-2 text-gray-400" /><span>1.2k</span></div>
                                  </div>
                                </div>
                              </div>

                              {/* 假卡片 1 */}
                              <div className="bg-white rounded-lg overflow-hidden shadow-xs flex flex-col border border-gray-100 opacity-60">
                                <div className="w-full aspect-[4/5] bg-gray-200"></div>
                                <div className="p-1.5"><div className="h-2 bg-gray-200 rounded w-4/5 mb-1.5"></div><div className="h-1.5 bg-gray-200 rounded w-2/5"></div></div>
                              </div>

                              {/* 假卡片 2 */}
                              <div className="bg-white rounded-lg overflow-hidden shadow-xs flex flex-col border border-gray-100 opacity-60">
                                <div className="w-full aspect-square bg-gray-200"></div>
                                <div className="p-1.5"><div className="h-2 bg-gray-200 rounded w-4/5 mb-1.5"></div><div className="h-1.5 bg-gray-200 rounded w-2/5"></div></div>
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
            </div>

          </div>

        </div>
      </ThreadActionsProvider>
    </ThreadContext.Provider>
  );
}
