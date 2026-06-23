import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useThread } from "./ThreadContext";
import {
  Database,
  CloudUpload,
  MessageSquare,
  Loader2,
  CheckCircle2,
  Send,
} from "lucide-react";

export function RightInspector() {
  const {
    isFeishuActionPending,
    draftContent,
    syncStepsVisible,
    syncStep,
    handleSyncToFeishu,
    isSyncing,
    isLoading,
    bitableUrl,
    wikiUrl,
    isFetchingChats,
    selectedChatId,
    setSelectedChatId,
    feishuChats,
    handleSendNotification,
    isSendingNotification,
  } = useThread();

  return (
    <motion.div
      key="feishu-tab"
      initial={{ opacity: 0, x: 12 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -12 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className="absolute inset-0 flex flex-col overflow-y-auto p-4 bg-oats/10 gap-4 custom-scrollbar"
    >
      {/* 写入多维表格卡片 */}
      <div className="bg-white border border-coral-light/60 p-4 rounded-xl shadow-xs space-y-3">
        <div className="flex items-center justify-between border-b border-oats-dark pb-2">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-green-50 border border-green-200 text-green-600 flex items-center justify-center">
              <Database className="size-4" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-charcoal">同步到飞书多维表格</h4>
              <p className="text-[8px] text-gray-400">由智能体确认后调用受控工具</p>
            </div>
          </div>
          <span className="bg-green-50 text-green-700 text-[9px] px-2 py-0.5 rounded-full font-semibold border border-green-200">连接可用</span>
        </div>

        <div className="space-y-2 text-[10px]">
          <div className="flex justify-between">
            <span className="text-gray-500">草稿入库状态：</span>
            <span className="font-semibold text-charcoal">
              {isFeishuActionPending ? "已交给智能体，等待确认/执行" : "尚未入库"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">动态映射列：</span>
            <span className="font-semibold text-gray-600">模糊匹配「正文」和「标题」列</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">当前正文字数：</span>
            <span className={cn("font-bold font-tabular", draftContent.length > 1000 ? "text-red-600" : "text-green-600")}>
              {draftContent.length} 字 {draftContent.length > 1000 && "(超限)"}
            </span>
          </div>
        </div>

        {/* 步骤条 */}
        {syncStepsVisible && (
          <div className="border border-coral-light/50 rounded-xl p-2.5 bg-oats-light/40 space-y-1.5 text-[10px] transition-all">
            <div className={cn("flex items-center gap-1.5", syncStep >= 1 ? "text-green-600 font-semibold" : "text-gray-400")}>
              {syncStep === 1 ? <Loader2 className="size-3.5 animate-spin" /> : (syncStep > 1 ? <CheckCircle2 className="size-3.5 text-green-500" /> : <Loader2 className="size-3.5 opacity-20" />)}
              <span>正在验证飞书环境配置...</span>
            </div>
            <div className={cn("flex items-center gap-1.5", syncStep >= 2 ? "text-green-600 font-semibold" : "text-gray-400")}>
              {syncStep === 2 ? <Loader2 className="size-3.5 animate-spin" /> : (syncStep > 2 ? <CheckCircle2 className="size-3.5 text-green-500" /> : <Loader2 className="size-3.5 opacity-20" />)}
              <span>正在读取 Fields 并智能解析空字段映射...</span>
            </div>
            <div className={cn("flex items-center gap-1.5", syncStep >= 3 ? "text-green-600 font-semibold" : "text-gray-400")}>
              {syncStep === 3 ? <Loader2 className="size-3.5 animate-spin" /> : (syncStep > 3 ? <CheckCircle2 className="size-3.5 text-green-500" /> : <Loader2 className="size-3.5 opacity-20" />)}
              <span>正在创建飞书多维表格草稿记录...</span>
            </div>
          </div>
        )}

        <div className="pt-1 flex flex-col gap-2">
          <button
            onClick={handleSyncToFeishu}
            disabled={isSyncing || isLoading}
            className={cn(
              "w-full text-white text-xs py-2 px-3 rounded-xl flex items-center justify-center gap-2 font-medium shadow-md transition-all cursor-pointer bg-coral hover:bg-coral-hover"
            )}
          >
            <CloudUpload className="size-4" />
            <span>提交同步请求至智能体</span>
          </button>
          {bitableUrl && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              className="text-center mt-1 overflow-hidden"
            >
              <a
                href={bitableUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[10px] text-coral hover:underline font-bold transition-all"
              >
                <span>🔗 点击直接打开飞书多维表格 ↗</span>
              </a>
            </motion.div>
          )}
          {wikiUrl && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              className="text-center mt-1 overflow-hidden"
            >
              <a
                href={wikiUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-[10px] text-coral hover:underline font-bold transition-all"
              >
                <span>🔗 点击直接打开飞书知识空间 ↗</span>
              </a>
            </motion.div>
          )}
        </div>
      </div>

      {/* 团队群发通知卡片 */}
      <div className="bg-white border border-coral-light/60 p-4 rounded-xl shadow-xs space-y-3">
        <div className="flex items-center justify-between border-b border-oats-dark pb-2">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-blue-50 border border-blue-200 text-blue-600 flex items-center justify-center">
              <MessageSquare className="size-4" />
            </div>
            <div>
              <h4 className="text-xs font-bold text-charcoal">群发通知与审核卡片</h4>
              <p className="text-[8px] text-gray-400">推送卡片消息到您所在的群聊</p>
            </div>
          </div>
          <span className="bg-blue-50 text-blue-700 text-[9px] px-2 py-0.5 rounded-full font-semibold border border-blue-200">可用</span>
        </div>

        <div className="space-y-3 text-[10px]">
          <div className="flex flex-col gap-1">
            <label className="text-gray-500 font-semibold">选择接收审核通知的飞书群聊：</label>
            {isFetchingChats ? (
              <div className="flex flex-col gap-2 py-1 select-none">
                {[1, 2, 3].map((n) => (
                  <div key={n} className="flex items-center gap-2.5 px-3 py-2 border border-coral-light/20 rounded-xl bg-white">
                    <div className="size-6.5 rounded-full skeleton-shimmer shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-2.5 bg-gray-100 rounded skeleton-shimmer w-3/4" />
                      <div className="h-1.5 bg-gray-100 rounded skeleton-shimmer w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <select
                value={selectedChatId}
                onChange={(e) => setSelectedChatId(e.target.value)}
                className="border border-coral-light rounded-xl px-2 py-1.5 bg-white focus:outline-none focus:border-coral outline-none text-[10px] w-full cursor-pointer"
              >
                {feishuChats.map((c) => (
                  <option key={c.chat_id} value={c.chat_id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        <div className="pt-1">
          <button
            onClick={handleSendNotification}
            disabled={isSendingNotification || isLoading || feishuChats.length === 0}
            className="w-full bg-oats hover:bg-oats-dark text-charcoal border border-coral-light/60 text-xs py-2 px-3 rounded-xl flex items-center justify-center gap-2 font-medium transition-all cursor-pointer"
          >
            {isSendingNotification ? <Loader2 className="size-3.5 animate-spin text-coral" /> : <Send className="size-3.5" />}
            <span>一键发送通知至飞书群聊</span>
          </button>
        </div>
      </div>
    </motion.div>
  );
}
