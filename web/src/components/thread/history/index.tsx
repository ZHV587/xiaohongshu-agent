// web/src/components/thread/history/index.tsx
import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { Thread } from "@langchain/langgraph-sdk";
import { useEffect, useState } from "react";

import { getContentString } from "../utils";
import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { SquarePen, LogIn, LogOut, Settings, X, Loader2, Check } from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";
import { BRAND } from "@/lib/brand";
import { getCurrentUser, loginWithFeishu, logout, type CurrentUser } from "@/lib/auth";

function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");

  return (
    <div className="flex h-full w-full flex-col items-start gap-1 overflow-y-auto px-2 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border">
      {threads.map((t) => {
        // 优先用首条用户消息作标题;取不到(如失败/空会话)显示友好占位,
        // 不暴露 thread_id 这种 UUID(此前会显示成一长串乱码似的 ID)。
        let itemText = "未命名对话";
        if (
          typeof t.values === "object" &&
          t.values &&
          "messages" in t.values &&
          Array.isArray(t.values.messages) &&
          t.values.messages?.length > 0
        ) {
          const first = getContentString(t.values.messages[0].content).trim();
          if (first) itemText = first;
        }
        const active = t.thread_id === threadId;
        return (
          <button
            key={t.thread_id}
            type="button"
            onClick={(e) => {
              e.preventDefault();
              onThreadClick?.(t.thread_id);
              if (t.thread_id === threadId) return;
              setThreadId(t.thread_id);
            }}
            className={cn(
              "w-full truncate rounded-lg px-3 py-2.5 text-left text-sm transition-all flex items-center justify-between",
              active
                ? "bg-oats text-coral border-l-2 border-coral font-semibold rounded-r-lg rounded-l-none pl-2"
                : "text-charcoal hover:bg-oats/50 rounded-lg",
            )}
          >
            {itemText}
          </button>
        );
      })}
    </div>
  );
}

// 极其精致的系统配置毛玻璃模态框组件
interface ConfigModalProps {
  open: boolean;
  onClose: () => void;
}

function ConfigModal({ open, onClose }: ConfigModalProps) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showToast, setShowToast] = useState(false);
  const [provider, setProvider] = useState("deepseek");
  const [showBackupKeys, setShowBackupKeys] = useState(false);
  const [configs, setConfigs] = useState({
    FEISHU_APP_ID: "",
    FEISHU_APP_SECRET: "",
    FEISHU_BITABLE_APP_TOKEN: "",
    FEISHU_BITABLE_TABLE_ID: "",
    LLM_API_KEY: "",
    LLM_BASE_URL: "",
    LLM_MODEL: "",
    OPENAI_API_KEY: "",
    ANTHROPIC_API_KEY: "",
    GEMINI_API_KEY: "",
    KIMI_API_KEY: "",
    DEEPSEEK_API_KEY: "",
  });

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetch("/api/config")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok && data.configs) {
          const loadedConfigs = data.configs;
          setConfigs(loadedConfigs);
          
          // 根据 LLM_MODEL 和 LLM_BASE_URL 智能判断服务商
          const modelLower = (loadedConfigs.LLM_MODEL || "").toLowerCase();
          const urlLower = (loadedConfigs.LLM_BASE_URL || "").toLowerCase();
          
          if (modelLower.includes("deepseek") || urlLower.includes("deepseek")) {
            setProvider("deepseek");
          } else if (modelLower.includes("moonshot") || modelLower.includes("kimi") || urlLower.includes("moonshot")) {
            setProvider("kimi");
          } else if (modelLower.includes("gemini") || urlLower.includes("googleapis")) {
            setProvider("gemini");
          } else if (modelLower.includes("claude") || urlLower.includes("anthropic")) {
            setProvider("anthropic");
          } else if (modelLower.includes("gpt") || modelLower.includes("o1") || modelLower.includes("o3") || urlLower.includes("openai")) {
            setProvider("openai");
          } else if (loadedConfigs.LLM_MODEL || loadedConfigs.LLM_API_KEY) {
            setProvider("custom");
          } else {
            setProvider("deepseek");
          }
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [open]);

  const handleProviderChange = (newProvider: string) => {
    setProvider(newProvider);
    
    let defaultModel = "";
    let defaultUrl = "";
    
    switch (newProvider) {
      case "openai":
        defaultModel = "gpt-4o";
        defaultUrl = "https://api.openai.com/v1";
        break;
      case "anthropic":
        defaultModel = "claude-3-5-sonnet-latest";
        defaultUrl = "https://api.anthropic.com";
        break;
      case "gemini":
        defaultModel = "gemini-2.5-flash";
        defaultUrl = "https://generativelanguage.googleapis.com";
        break;
      case "kimi":
        defaultModel = "moonshot-v1-8k";
        defaultUrl = "https://api.moonshot.cn/v1";
        break;
      case "deepseek":
        defaultModel = "deepseek-chat";
        defaultUrl = "https://api.deepseek.com/v1";
        break;
      default:
        break;
    }
    
    setConfigs(prev => ({
      ...prev,
      LLM_MODEL: defaultModel,
      LLM_BASE_URL: defaultUrl,
    }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ configs }),
      });
      if (res.ok) {
        setShowToast(true);
        setTimeout(() => setShowToast(false), 2000);
        setTimeout(onClose, 800);
      } else {
        alert("保存配置失败，请检查密钥是否正确");
      }
    } catch (err) {
      console.error(err);
      alert("配置网络请求异常");
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4 animate-in fade-in duration-200">
      <div className="bg-white/95 border border-border/80 shadow-2xl rounded-2xl max-w-lg w-full flex flex-col relative overflow-hidden animate-in fade-in zoom-in-95 duration-200 max-h-[90vh]">
        
        {/* Header */}
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2">
            <Settings className="size-5 text-coral animate-pulse" />
            <h2 className="text-base font-semibold text-charcoal">系统参数配置</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-coral transition-colors p-1 rounded-full hover:bg-gray-100"
          >
            <X className="size-4" />
          </button>
        </div>

        {/* Form body */}
        <form onSubmit={handleSave} className="flex-1 overflow-y-auto p-6 space-y-5 text-left">
          {loading ? (
            <div className="space-y-4 py-8">
              <div className="h-4 bg-gray-100 rounded animate-pulse w-1/3" />
              <div className="h-10 bg-gray-100 rounded animate-pulse w-full" />
              <div className="h-4 bg-gray-100 rounded animate-pulse w-1/4" />
              <div className="h-10 bg-gray-100 rounded animate-pulse w-full" />
            </div>
          ) : (
            <>
              {/* 飞书自建应用凭证 */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-coral tracking-wider uppercase">飞书自建应用凭证</h3>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-500">App ID</label>
                    <input
                      type="text"
                      value={configs.FEISHU_APP_ID}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_APP_ID: e.target.value })}
                      placeholder="cli_xxx"
                      className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-500">App Secret</label>
                    <input
                      type="password"
                      value={configs.FEISHU_APP_SECRET}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_APP_SECRET: e.target.value })}
                      placeholder="••••••••••••••••"
                      className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    />
                  </div>
                </div>
                <p className="text-[10px] text-gray-400">来自飞书开放平台企业自建应用。请确保已在后台添加协作人或授予多维表格 API 权限。</p>
              </div>

              <hr className="border-gray-100" />

              {/* 多维表格爆款库定位 */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-coral tracking-wider uppercase">多维表格爆款库</h3>
                <div className="space-y-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-500">Bitable App Token</label>
                    <input
                      type="text"
                      value={configs.FEISHU_BITABLE_APP_TOKEN}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_APP_TOKEN: e.target.value })}
                      placeholder="V8Kub8gg8afB7RsllZWc4iSRnAc"
                      className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-500">Bitable Table ID</label>
                    <input
                      type="text"
                      value={configs.FEISHU_BITABLE_TABLE_ID}
                      onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_TABLE_ID: e.target.value })}
                      placeholder="tbl24vSVeLvz45ig"
                      className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    />
                  </div>
                </div>
                <p className="text-[10px] text-gray-400">表格浏览器 URL 包含定位，格式形如 `base/&#123;AppToken&#125;?table=&#123;TableID&#125;`。</p>
              </div>

              <hr className="border-gray-100" />

              {/* 大语言模型 API 设置 */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-coral tracking-wider uppercase">大模型配置</h3>
                
                {/* 模型服务商选择 */}
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-500">大模型服务商</label>
                  <select
                    value={provider}
                    onChange={(e) => handleProviderChange(e.target.value)}
                    className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                  >
                    <option value="deepseek">深度求索 (DeepSeek)</option>
                    <option value="kimi">月之暗面 (Kimi / Moonshot)</option>
                    <option value="openai">OpenAI (GPT)</option>
                    <option value="anthropic">Anthropic (Claude)</option>
                    <option value="gemini">Google Gemini</option>
                    <option value="custom">自定义中转 (如 One API / 聚合通道)</option>
                  </select>
                </div>

                <div className="space-y-3">
                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-500">API 密钥 (API Key)</label>
                    <input
                      type="password"
                      value={configs.LLM_API_KEY}
                      onChange={(e) => setConfigs({ ...configs, LLM_API_KEY: e.target.value })}
                      placeholder={
                        provider === "deepseek" ? "请输入 DeepSeek 官方密钥 (sk-...)" :
                        provider === "kimi" ? "请输入 Kimi 官方密钥 (sk-...)" :
                        provider === "openai" ? "请输入 OpenAI 官方密钥 (sk-...)" :
                        provider === "anthropic" ? "请输入 Claude 官方密钥 (sk-...)" :
                        provider === "gemini" ? "请输入 Gemini 官方密钥" :
                        "请输入 API 密钥"
                      }
                      className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-500">模型名称 (Model)</label>
                    <input
                      type="text"
                      value={configs.LLM_MODEL}
                      onChange={(e) => setConfigs({ ...configs, LLM_MODEL: e.target.value })}
                      placeholder="例如: deepseek-chat"
                      className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    />
                    <p className="text-[10px] text-gray-400">
                      {provider === "deepseek" && "提示：默认使用 deepseek-chat 模型，速度极快且极便宜。"}
                      {provider === "kimi" && "提示：默认使用 moonshot-v1-8k 模型，长文本分析能力出色。"}
                      {provider === "openai" && "提示：推荐使用 gpt-4o 或 gpt-4o-mini 等官方模型。"}
                      {provider === "anthropic" && "提示：推荐使用 claude-3-5-sonnet-latest 官方模型。"}
                      {provider === "gemini" && "提示：推荐使用 gemini-2.5-flash 或 gemini-2.5-pro 官方模型。"}
                      {provider === "custom" && "提示：请填写您的中转平台支持的具体模型标识符。"}
                    </p>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-medium text-gray-500">接口地址 (Base URL)</label>
                    <input
                      type="text"
                      value={configs.LLM_BASE_URL}
                      onChange={(e) => setConfigs({ ...configs, LLM_BASE_URL: e.target.value })}
                      placeholder="官方默认或您的中转地址"
                      className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    />
                    <p className="text-[10px] text-gray-400">
                      {provider !== "custom" ? "系统已根据选定的服务商自动填写官方默认地址，使用中转时可以手动修改。" : "提示：填入第三方中转网关的统一入口（如 One API / 代理地址）。"}
                    </p>
                  </div>

                  {/* 折叠备用灾备 Key 区域 */}
                  <div className="border border-gray-100 rounded-xl overflow-hidden mt-4">
                    <button
                      type="button"
                      onClick={() => setShowBackupKeys(!showBackupKeys)}
                      className="w-full flex items-center justify-between px-4 py-3 bg-gray-50/50 hover:bg-gray-50 text-xs font-semibold text-charcoal transition-all border-b border-gray-100/50"
                    >
                      <span className="flex items-center gap-1.5 text-coral">
                        🛡️ 备用灾备模型密钥配置 (多 Key 智能容灾)
                      </span>
                      <span className="text-gray-400 text-[10px]">
                        {showBackupKeys ? "收起" : "展开配置"}
                      </span>
                    </button>
                    
                    {showBackupKeys && (
                      <div className="p-4 space-y-3 bg-white border-t border-gray-100 animate-in fade-in slide-in-from-top-2 duration-200">
                        <p className="text-[10px] text-gray-400 leading-relaxed mb-1">
                          提示：当主渠道因限流、欠费等报错无法使用时，智能体将按照 **Kimi ➔ DeepSeek ➔ GPT ➔ Gemini ➔ Claude** 的优先级，智能顺延重试已填入密钥的可用模型。
                        </p>
                        
                        <div className="space-y-1">
                          <label className="text-xs font-medium text-gray-500">DeepSeek 备用密钥 (DEEPSEEK_API_KEY)</label>
                          <input
                            type="password"
                            value={configs.DEEPSEEK_API_KEY || ""}
                            onChange={(e) => setConfigs({ ...configs, DEEPSEEK_API_KEY: e.target.value })}
                            placeholder="sk-..."
                            className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-1.5 text-xs rounded-lg outline-none transition-all"
                          />
                        </div>

                        <div className="space-y-1">
                          <label className="text-xs font-medium text-gray-500">Kimi 备用密钥 (KIMI_API_KEY)</label>
                          <input
                            type="password"
                            value={configs.KIMI_API_KEY || ""}
                            onChange={(e) => setConfigs({ ...configs, KIMI_API_KEY: e.target.value })}
                            placeholder="sk-..."
                            className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-1.5 text-xs rounded-lg outline-none transition-all"
                          />
                        </div>

                        <div className="space-y-1">
                          <label className="text-xs font-medium text-gray-500">GPT / OpenAI 备用密钥 (OPENAI_API_KEY)</label>
                          <input
                            type="password"
                            value={configs.OPENAI_API_KEY || ""}
                            onChange={(e) => setConfigs({ ...configs, OPENAI_API_KEY: e.target.value })}
                            placeholder="sk-..."
                            className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-1.5 text-xs rounded-lg outline-none transition-all"
                          />
                        </div>

                        <div className="space-y-1">
                          <label className="text-xs font-medium text-gray-500">Gemini 备用密钥 (GEMINI_API_KEY)</label>
                          <input
                            type="password"
                            value={configs.GEMINI_API_KEY || ""}
                            onChange={(e) => setConfigs({ ...configs, GEMINI_API_KEY: e.target.value })}
                            placeholder="Google AI Key..."
                            className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-1.5 text-xs rounded-lg outline-none transition-all"
                          />
                        </div>

                        <div className="space-y-1">
                          <label className="text-xs font-medium text-gray-500">Claude 备用密钥 (ANTHROPIC_API_KEY)</label>
                          <input
                            type="password"
                            value={configs.ANTHROPIC_API_KEY || ""}
                            onChange={(e) => setConfigs({ ...configs, ANTHROPIC_API_KEY: e.target.value })}
                            placeholder="sk-ant-..."
                            className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-1.5 text-xs rounded-lg outline-none transition-all"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </>
          )/* End loading */ }
        </form>

        {/* Footer */}
        <div className="border-t px-6 py-4 flex items-center justify-end gap-2 bg-gray-50">
          <Button
            type="button"
            variant="ghost"
            disabled={saving}
            onClick={onClose}
            className="text-xs"
          >
            取消
          </Button>
          <Button
            type="submit"
            disabled={loading || saving}
            onClick={handleSave}
            className="bg-primary text-primary-foreground hover:bg-primary/90 min-w-[80px] text-xs flex items-center gap-1.5"
          >
            {saving ? (
              <>
                <Loader2 className="size-3 animate-spin" />
                正在保存
              </>
            ) : (
              "保存配置"
            )}
          </Button>
        </div>

        {/* Toast */}
        {showToast && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-green-500 text-white text-xs px-4 py-2 rounded-full shadow-lg flex items-center gap-1.5 animate-in fade-in slide-in-from-top-4 duration-300">
            <Check className="size-3" />
            配置热更新成功，即时生效
          </div>
        )}

      </div>
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex w-full flex-col gap-1 px-2">
      {Array.from({ length: 12 }).map((_, i) => (
        <Skeleton key={i} className="h-9 w-full" />
      ))}
    </div>
  );
}

function UserArea() {
  // 客户端读 cookie 里的身份 JWT,展示当前飞书用户 / 登录入口。
  const [user, setUser] = useState<CurrentUser | null>(null);
  useEffect(() => {
    setUser(getCurrentUser());
  }, []);

  if (!user) {
    return (
      <div className="border-border mt-auto border-t px-2 py-3 text-left">
        <Button
          variant="ghost"
          className="text-foreground/80 hover:bg-secondary w-full justify-start gap-2"
          onClick={() => loginWithFeishu(window.location.pathname + window.location.search)}
        >
          <LogIn className="size-4" />
          用飞书登录
        </Button>
      </div>
    );
  }

  const display = user.name || user.openId;
  return (
    <div className="border-oats-dark mt-auto flex items-center justify-between border-t p-4 text-left">
      <div className="flex items-center gap-2.5">
        <span className="bg-coral-light text-coral flex size-8 shrink-0 items-center justify-center rounded-lg font-bold text-xs">
          {display.slice(0, 1).toUpperCase()}
        </span>
        <span className="text-charcoal font-semibold flex-1 truncate text-xs max-w-[150px]" title={display}>
          {display}
        </span>
      </div>
      <button
        type="button"
        onClick={logout}
        title="退出登录"
        className="text-gray-400 hover:text-coral shrink-0 transition-colors cursor-pointer"
      >
        <LogOut className="size-4" />
      </button>
    </div>
  );
}

function SidebarBody({ onConfigOpen }: { onConfigOpen: () => void }) {
  const [, setThreadId] = useQueryState("threadId");
  const { getThreads, threads, setThreads, threadsLoading, setThreadsLoading } =
    useThreads();

  useEffect(() => {
    if (typeof window === "undefined") return;
    setThreadsLoading(true);
    getThreads()
      .then(setThreads)
      .catch(console.error)
      .finally(() => setThreadsLoading(false));
  }, []);

  return (
    <div className="flex h-full w-full flex-col">
      {/* 品牌区 */}
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <div className="flex items-center gap-2">
          <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-lg text-sm">
            {BRAND.mark}
          </span>
          <span className="text-foreground text-[15px] font-semibold">{BRAND.name}</span>
        </div>
        <Button
          variant="ghost"
          size="icon"
          title="系统配置"
          onClick={onConfigOpen}
          className="size-8 text-gray-400 hover:text-coral transition-colors"
        >
          <Settings className="size-4" />
        </Button>
      </div>
      {/* 新对话 */}
      <div className="px-2 pb-2 text-left">
        <Button
          className="bg-primary text-primary-foreground hover:bg-primary/90 w-full justify-start gap-2"
          onClick={() => setThreadId(null)}
        >
          <SquarePen className="size-4" />
          新对话
        </Button>
      </div>
      <div className="text-muted-foreground px-4 pt-2 pb-1 text-xs tracking-wide text-left">最近</div>
      <div className="min-h-0 flex-1">
        {threadsLoading ? <ThreadHistoryLoading /> : <ThreadList threads={threads} />}
      </div>
      {/* 用户区:飞书登录态 */}
      <UserArea />
    </div>
  );
}

export default function ThreadHistory() {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );
  const [configOpen, setConfigOpen] = useState(false);

  return (
    <>
      <div className="hidden h-screen w-[300px] shrink-0 flex-col border-r lg:flex">
        <SidebarBody onConfigOpen={() => setConfigOpen(true)} />
      </div>
      <div className="lg:hidden">
        <Sheet
          open={!!chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (isLargeScreen) return;
            setChatHistoryOpen(open);
          }}
        >
          <SheetContent side="left" className="flex w-[300px] p-0 lg:hidden">
            <SheetHeader className="sr-only">
              <SheetTitle>会话历史</SheetTitle>
            </SheetHeader>
            <SidebarBody onConfigOpen={() => setConfigOpen(true)} />
          </SheetContent>
        </Sheet>
      </div>

      <ConfigModal open={configOpen} onClose={() => setConfigOpen(false)} />
    </>
  );
}
