import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { useThread } from "./ThreadContext";

export function PhoneSimulator() {
  const {
    viewMode,
    setViewMode,
    carouselImages,
    carouselIndex,
    setCarouselIndex,
    isFeishuActionPending,
    isEditingText,
    setIsEditingText,
    isDirty,
    draftTitle,
    setDraftTitle,
    draftContent,
    setDraftContent,
    lastSavedTitle,
    lastSavedContent,
    handleInsertEmoji,
    handleAppendTag,
    handleEditBodyPaste,
    textareaRef,
  } = useThread();

  return (
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
  );
}
