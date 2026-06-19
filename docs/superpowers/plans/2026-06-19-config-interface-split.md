# 大模型与飞书配置界面拆分及多模态适配 部署实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将系统设置彻底拆分为大模型配置（对齐 LobeChat 手风琴样式并支持测试连接自动获取模型列表）与飞书同步配置两个独立的全屏界面，同时后端支持动态 Provider 路由以支持多模态原生调用。

**Architecture:** 
1. 后端 `models.py` 从 `.env` 读取 `LLM_PROVIDER` 动态采用原生的 `langchain_anthropic` (Claude) 或 `langchain_google_genai` (Gemini)，其余继续走 `ChatOpenAI` 归一化。
2. 前端通过 `nuqs` 的 `view` 查询参数控制右侧聊天画面的切换（`/?view=llm` 与 `/?view=feishu`）。
3. 侧边栏右上角并排渲染 `Sparkles` 与 `SlidersHorizontal` 按钮分别触发视图切换。
4. 测试连接 API 成功后会自动发起 GET 请求获取 `/v1/models` 清单，前端将输入框渲染为下拉切换菜单。

**Tech Stack:** React, Next.js (App Router), Tailwind CSS, Lucide icons, nuqs, LangChain (langchain-openai, langchain-anthropic, langchain-google-genai)

---

### Task 1: 后端底层模型层多模态适配

**Files:**
- Modify: `e:/小红书智能体/models.py`

- [ ] **Step 1: 修改 models.py 动态加载不同模型提供商**
  修改 `_build_chat_model` 的实现，从环境变量 `LLM_PROVIDER` 中读取参数并动态实例化：
  
  ```python
  def _build_chat_model(model_id: str, base_url: str, api_key: str) -> BaseChatModel:
      """根据环境变量 LLM_PROVIDER 动态构造对应的原生多模态模型实例"""
      provider = os.environ.get("LLM_PROVIDER", "openai").strip().lower()
      
      if provider == "anthropic":
          from langchain_anthropic import ChatAnthropic
          return ChatAnthropic(
              model=model_id,
              api_key=api_key,
              temperature=0.7,
              timeout=60,
              max_retries=2,
          )
      elif provider == "google_genai":
          from langchain_google_genai import ChatGoogleGenerativeAI
          return ChatGoogleGenerativeAI(
              model=model_id,
              api_key=api_key,
              temperature=0.7,
              timeout=60,
              max_retries=2,
          )
      else:
          # 默认使用 OpenAI 兼容协议
          return init_chat_model(
              model=model_id,
              model_provider="openai",
              base_url=base_url,
              api_key=api_key,
              temperature=0.7,
              timeout=60,
              max_retries=2,
          )
  ```

- [ ] **Step 2: 验证语法无误**
  运行: `.\.venv\Scripts\python.exe -m py_compile models.py`
  Expected: 无语法错误返回。

- [ ] **Step 3: 提交代码**
  运行: `git add models.py`
  运行: `git commit -m "backend: support dynamic model provider routing for multimodal in models.py"`

---

### Task 2: 重构连接测试接口以支持模型列表发现

**Files:**
- Modify: `e:/小红书智能体/web/src/app/api/config/test/route.ts`

- [ ] **Step 1: 修改 API 连接测试端点以连带获取 /v1/models**
  在 `POST` 函数中，若 `/chat/completions` 通路测试成功，自动发起一个 GET 请求到 `baseUrl/models` 获取可用模型列表：
  
  ```typescript
  // 在获取到 latency 后，继续向 baseUrl/models 获取模型列表
  let models: string[] = [];
  try {
    const modelsUrl = `${baseUrl.replace(/\/$/, "")}/models`;
    const modelsResp = await fetch(modelsUrl, {
      method: "GET",
      headers: {
        "Authorization": `Bearer ${apiKey}`
      },
      signal: controller.signal
    });
    if (modelsResp.status === 200) {
      const data = await modelsResp.json();
      if (data && Array.isArray(data.data)) {
        models = data.data.map((m: any) => m.id).filter(Boolean);
      }
    }
  } catch (err) {
    console.warn("Failed to discover models from target endpoint:", err);
  }

  if (resp.status === 200) {
    return NextResponse.json({ ok: true, latency, models });
  }
  ```

- [ ] **Step 2: 提交代码**
  运行: `git add web/src/app/api/config/test/route.ts`
  运行: `git commit -m "api: support dynamic models list discovery in connection test api"`

---

### Task 3: 实现 FeishuConfigPage 全屏配置页面

**Files:**
- Create: `e:/小红书智能体/web/src/components/thread/history/FeishuConfigPage.tsx`

- [ ] **Step 1: 新建飞书独立全屏配置页面组件**
  新建文件，包含独立的 App ID、App Secret 以及 Bitable Token、Table ID 表单输入：
  
  ```typescript
  import { useState, useEffect } from "react";
  import { SlidersHorizontal, Loader2, Check, ArrowLeft } from "lucide-react";
  import { Button } from "@/components/ui/button";

  export function FeishuConfigPage({ onClose }: { onClose: () => void }) {
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [showToast, setShowToast] = useState(false);
    const [configs, setConfigs] = useState<any>({
      FEISHU_APP_ID: "",
      FEISHU_APP_SECRET: "",
      FEISHU_BITABLE_APP_TOKEN: "",
      FEISHU_BITABLE_TABLE_ID: "",
    });

    useEffect(() => {
      setLoading(true);
      fetch("/api/config")
        .then((res) => res.json())
        .then((data) => {
          if (data.ok && data.configs) {
            setConfigs(data.configs);
          }
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    }, []);

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
          alert("保存配置失败，请检查输入项");
        }
      } catch (err) {
        console.error(err);
        alert("网络请求异常");
      } finally {
        setSaving(false);
      }
    };

    return (
      <div className="flex flex-col h-full w-full bg-white p-6 overflow-y-auto text-left">
        <div className="flex justify-between items-center border-b pb-4 mb-6">
          <div>
            <h2 className="text-lg font-bold text-charcoal flex items-center gap-2">
              <SlidersHorizontal className="size-5 text-coral animate-pulse" />
              飞书同步与多维表格配置
            </h2>
            <p className="text-xs text-gray-400 mt-1">配置飞书开放平台应用凭证与同步存放小红书文案的多维表格参数</p>
          </div>
          <Button variant="outline" size="sm" onClick={onClose} className="text-xs flex items-center gap-1">
            <ArrowLeft className="size-3" /> 返回会话
          </Button>
        </div>

        {loading ? (
          <div className="space-y-4 py-8">
            <div className="h-4 bg-gray-100 rounded animate-pulse w-1/3" />
            <div className="h-10 bg-gray-100 rounded animate-pulse w-full" />
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-6 max-w-2xl">
            <div className="space-y-4">
              <h3 className="text-xs font-bold text-coral tracking-wider uppercase border-b pb-1">飞书自建应用资质</h3>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-500">App ID</label>
                  <input
                    type="text"
                    value={configs.FEISHU_APP_ID || ""}
                    onChange={(e) => setConfigs({ ...configs, FEISHU_APP_ID: e.target.value })}
                    placeholder="cli_xxx"
                    className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-500">App Secret</label>
                  <input
                    type="password"
                    value={configs.FEISHU_APP_SECRET || ""}
                    onChange={(e) => setConfigs({ ...configs, FEISHU_APP_SECRET: e.target.value })}
                    placeholder="••••••••••••••••"
                    className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    required
                  />
                </div>
              </div>
              <p className="text-[10px] text-gray-400">请确保在飞书开放平台后台授予该应用“云文档 ➔ 多维表格”的读取和写入权限。</p>
            </div>

            <div className="space-y-4 pt-4">
              <h3 className="text-xs font-bold text-coral tracking-wider uppercase border-b pb-1">爆款库多维表格坐标</h3>
              <div className="space-y-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-500">Bitable App Token</label>
                  <input
                    type="text"
                    value={configs.FEISHU_BITABLE_APP_TOKEN || ""}
                    onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_APP_TOKEN: e.target.value })}
                    placeholder="bascnxxxxxxxxxxxx"
                    className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    required
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-gray-500">Bitable Table ID (数据表 ID)</label>
                  <input
                    type="text"
                    value={configs.FEISHU_BITABLE_TABLE_ID || ""}
                    onChange={(e) => setConfigs({ ...configs, FEISHU_BITABLE_TABLE_ID: e.target.value })}
                    placeholder="tblxxxxxxxxx"
                    className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-sm rounded-lg outline-none transition-all"
                    required
                  />
                </div>
              </div>
              <p className="text-[10px] text-gray-400">App Token 位于表格 URL 中 `base/` 后面的一长串字符，Table ID 对应具体数据表的子 ID。</p>
            </div>

            <div className="flex items-center justify-end gap-2 border-t pt-4 mt-6">
              <button
                type="submit"
                disabled={saving}
                className="bg-coral text-white hover:bg-coral/95 active:scale-95 disabled:opacity-50 px-5 py-2 text-sm font-medium rounded-xl flex items-center gap-1.5 shadow-md shadow-coral/10 transition-all"
              >
                {saving && <Loader2 className="size-4 animate-spin" />}
                {saving ? "保存中..." : "保存配置"}
              </button>
            </div>
          </form>
        )}

        {showToast && (
          <div className="fixed bottom-6 right-6 bg-gray-900/95 text-white px-4 py-2.5 rounded-xl text-xs flex items-center gap-1.5 shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-300 z-50">
            <Check className="size-4 text-emerald-400" />
            <span>飞书配置热更新成功，即时生效。</span>
          </div>
        )}
      </div>
    );
  }
  ```

- [ ] **Step 2: 提交代码**
  运行: `git add web/src/components/thread/history/FeishuConfigPage.tsx`
  运行: `git commit -m "frontend: create FeishuConfigPage component for full-screen configuration"`

---

### Task 4: 实现 LlmConfigPage LobeChat 风格手风琴配置页面

**Files:**
- Create: `e:/小红书智能体/web/src/components/thread/history/LlmConfigPage.tsx`

- [ ] **Step 1: 新建大模型配置页面组件**
  新建文件，实现 LobeChat 风格的 Accordion 列表，内置测试连接及从接口同步模型列表下拉选择的能力：
  
  ```typescript
  import { useState, useEffect } from "react";
  import { Sparkles, Loader2, Check, ArrowLeft, ChevronDown, ChevronRight, Play } from "lucide-react";
  import { Button } from "@/components/ui/button";

  const PROVIDERS = [
    { id: "deepseek", name: "DeepSeek", emoji: "🇨🇳", defaultUrl: "https://api.deepseek.com/v1", defaultModel: "deepseek-chat", providerVal: "openai" },
    { id: "kimi", name: "Kimi (Moonshot)", emoji: "🌙", defaultUrl: "https://api.moonshot.cn/v1", defaultModel: "moonshot-v1-8k", providerVal: "openai" },
    { id: "openai", name: "OpenAI (ChatGPT)", emoji: "🤖", defaultUrl: "https://api.openai.com/v1", defaultModel: "gpt-4o", providerVal: "openai" },
    { id: "anthropic", name: "Anthropic Claude", emoji: "🎨", defaultUrl: "https://api.anthropic.com", defaultModel: "claude-3-5-sonnet-latest", providerVal: "anthropic" },
    { id: "gemini", name: "Google Gemini", emoji: "♊", defaultUrl: "https://generativelanguage.googleapis.com", defaultModel: "gemini-2.5-flash", providerVal: "google_genai" },
    { id: "custom", name: "中转代理 / 其他", emoji: "⚙️", defaultUrl: "", defaultModel: "", providerVal: "openai" }
  ];

  export function LlmConfigPage({ onClose }: { onClose: () => void }) {
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [expandedProvider, setExpandedProvider] = useState<string>("deepseek");
    const [primaryProvider, setPrimaryProvider] = useState<string>("deepseek");
    
    // 延迟测试与模型下拉缓存
    const [testingId, setTestingId] = useState<string | null>(null);
    const [testResults, setTestResults] = useState<Record<string, { ok: boolean; msg: string }>>({});
    const [discoveredModels, setDiscoveredModels] = useState<Record<string, string[]>>({});
    const [showToast, setShowToast] = useState(false);

    const [configs, setConfigs] = useState<any>({
      LLM_PROVIDER: "openai",
      LLM_API_KEY: "",
      LLM_BASE_URL: "",
      LLM_MODEL: "",
      DEEPSEEK_API_KEY: "",
      KIMI_API_KEY: "",
      OPENAI_API_KEY: "",
      ANTHROPIC_API_KEY: "",
      GEMINI_API_KEY: "",
      CUSTOM_API_KEY: "",
      CUSTOM_BASE_URL: "",
      CUSTOM_MODEL: "",
    });

    useEffect(() => {
      setLoading(true);
      fetch("/api/config")
        .then((res) => res.json())
        .then((data) => {
          if (data.ok && data.configs) {
            const c = data.configs;
            setConfigs(c);
            
            // 自动推断当前选中的主提供商
            const providerEnv = (c.LLM_PROVIDER || "openai").toLowerCase();
            const modelLower = (c.LLM_MODEL || "").toLowerCase();
            const urlLower = (c.LLM_BASE_URL || "").toLowerCase();
            
            let current = "deepseek";
            if (providerEnv === "anthropic") {
              current = "anthropic";
            } else if (providerEnv === "google_genai") {
              current = "gemini";
            } else if (modelLower.includes("deepseek")) {
              current = "deepseek";
            } else if (modelLower.includes("moonshot") || modelLower.includes("kimi")) {
              current = "kimi";
            } else if (modelLower.includes("gpt") || modelLower.includes("o1") || modelLower.includes("o3")) {
              current = "openai";
            } else if (c.LLM_BASE_URL && !c.LLM_BASE_URL.includes("deepseek") && !c.LLM_BASE_URL.includes("moonshot") && !c.LLM_BASE_URL.includes("openai")) {
              current = "custom";
            }
            setPrimaryProvider(current);
            setExpandedProvider(current);
          }
        })
        .catch(console.error)
        .finally(() => setLoading(false));
    }, []);

    const handleTest = async (providerId: string, apiKey: string, baseUrl: string, currentModel: string) => {
      if (!apiKey || !baseUrl) {
        alert("请先填写该渠道的 API Key 和代理地址");
        return;
      }
      setTestingId(providerId);
      try {
        const res = await fetch("/api/config/test", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ apiKey, baseUrl, model: currentModel || "ping" })
        });
        const data = await res.json();
        if (data.ok) {
          setTestResults(prev => ({ ...prev, [providerId]: { ok: true, msg: `连接成功 (${data.latency}ms)` } }));
          if (data.models && data.models.length > 0) {
            setDiscoveredModels(prev => ({ ...prev, [providerId]: data.models }));
          }
        } else {
          setTestResults(prev => ({ ...prev, [providerId]: { ok: false, msg: `连接失败: ${data.error}` } }));
        }
      } catch (err: any) {
        setTestResults(prev => ({ ...prev, [providerId]: { ok: false, msg: `异常: ${err.message}` } }));
      } finally {
        setTestingId(null);
      }
    };

    const handleSave = async (e: React.FormEvent) => {
      e.preventDefault();
      setSaving(true);

      const target = PROVIDERS.find(p => p.id === primaryProvider)!;
      const updatedConfigs = { ...configs };
      updatedConfigs.LLM_PROVIDER = target.providerVal;
      
      // 提取主渠道配置值
      if (primaryProvider === "custom") {
        updatedConfigs.LLM_API_KEY = configs.CUSTOM_API_KEY;
        updatedConfigs.LLM_BASE_URL = configs.CUSTOM_BASE_URL;
        updatedConfigs.LLM_MODEL = configs.CUSTOM_MODEL;
      } else {
        const keyMapping: Record<string, string> = {
          deepseek: "DEEPSEEK_API_KEY",
          kimi: "KIMI_API_KEY",
          openai: "OPENAI_API_KEY",
          anthropic: "ANTHROPIC_API_KEY",
          gemini: "GEMINI_API_KEY"
        };
        const keyVal = configs[keyMapping[primaryProvider]];
        updatedConfigs.LLM_API_KEY = keyVal;
        updatedConfigs.LLM_BASE_URL = target.defaultUrl;
        updatedConfigs.LLM_MODEL = configs.LLM_MODEL || target.defaultModel;
      }

      try {
        const res = await fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ configs: updatedConfigs }),
        });
        if (res.ok) {
          setShowToast(true);
          setTimeout(() => setShowToast(false), 2000);
          setTimeout(onClose, 800);
        } else {
          alert("保存配置失败，请检查输入项");
        }
      } catch (err) {
        console.error(err);
        alert("网络请求异常");
      } finally {
        setSaving(false);
      }
    };

    const updateProviderKey = (providerId: string, val: string) => {
      if (providerId === "custom") {
        setConfigs((prev: any) => ({ ...prev, CUSTOM_API_KEY: val }));
      } else {
        const keyMapping: Record<string, string> = {
          deepseek: "DEEPSEEK_API_KEY",
          kimi: "KIMI_API_KEY",
          openai: "OPENAI_API_KEY",
          anthropic: "ANTHROPIC_API_KEY",
          gemini: "GEMINI_API_KEY"
        };
        setConfigs((prev: any) => ({ ...prev, [keyMapping[providerId]]: val }));
      }
    };

    const getProviderKey = (providerId: string) => {
      if (providerId === "custom") return configs.CUSTOM_API_KEY || "";
      const keyMapping: Record<string, string> = {
        deepseek: "DEEPSEEK_API_KEY",
        kimi: "KIMI_API_KEY",
        openai: "OPENAI_API_KEY",
        anthropic: "ANTHROPIC_API_KEY",
        gemini: "GEMINI_API_KEY"
      };
      return configs[keyMapping[providerId]] || "";
    };

    return (
      <div className="flex flex-col h-full w-full bg-white p-6 overflow-y-auto text-left">
        <div className="flex justify-between items-center border-b pb-4 mb-6">
          <div>
            <h2 className="text-lg font-bold text-charcoal flex items-center gap-2">
              <Sparkles className="size-5 text-coral animate-pulse" />
              语言大模型 (LLM) 引擎配置
            </h2>
            <p className="text-xs text-gray-400 mt-1">管理您智能体使用的大语言模型接口参数，可一键展开、配置并独立测试网络连通性。</p>
          </div>
          <Button variant="outline" size="sm" onClick={onClose} className="text-xs flex items-center gap-1">
            <ArrowLeft className="size-3" /> 返回会话
          </Button>
        </div>

        {loading ? (
          <div className="space-y-4 py-8">
            <div className="h-4 bg-gray-100 rounded animate-pulse w-1/3" />
            <div className="h-10 bg-gray-100 rounded animate-pulse w-full" />
          </div>
        ) : (
          <form onSubmit={handleSave} className="space-y-6 max-w-3xl">
            <div className="space-y-3">
              {PROVIDERS.map((provider) => {
                const isExpanded = expandedProvider === provider.id;
                const isPrimary = primaryProvider === provider.id;
                const apiKey = getProviderKey(provider.id);
                const baseUrl = provider.id === "custom" ? (configs.CUSTOM_BASE_URL || "") : provider.defaultUrl;
                const currentModel = provider.id === "custom" ? (configs.CUSTOM_MODEL || "") : (isPrimary ? (configs.LLM_MODEL || provider.defaultModel) : provider.defaultModel);
                const testRes = testResults[provider.id];
                const modelList = discoveredModels[provider.id] || [];

                return (
                  <div key={provider.id} className={`border rounded-xl transition-all overflow-hidden ${isPrimary ? "border-coral/50 shadow-sm" : "border-gray-200"}`}>
                    {/* Header */}
                    <div 
                      onClick={() => setExpandedProvider(isExpanded ? "" : provider.id)}
                      className={`flex justify-between items-center p-4 cursor-pointer select-none transition-colors ${isPrimary ? "bg-coral/[0.02] hover:bg-coral/[0.04]" : "bg-gray-50/50 hover:bg-gray-50"}`}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-xl">{provider.emoji}</span>
                        <span className={`font-semibold text-sm ${isPrimary ? "text-coral font-bold" : "text-charcoal"}`}>{provider.name}</span>
                        {isPrimary && <span className="bg-coral text-white text-[9px] px-2 py-0.5 rounded-full font-bold scale-90">当前主引擎</span>}
                        {!isPrimary && apiKey && <span className="bg-gray-100 text-gray-500 text-[9px] px-2 py-0.5 rounded-full scale-90">已配密钥</span>}
                      </div>

                      <div className="flex items-center gap-4" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          onClick={() => {
                            setPrimaryProvider(provider.id);
                            if (provider.id === "custom") {
                              setConfigs((p: any) => ({ ...p, LLM_MODEL: p.CUSTOM_MODEL }));
                            } else {
                              setConfigs((p: any) => ({ ...p, LLM_MODEL: provider.defaultModel }));
                            }
                          }}
                          className={`text-xs px-2.5 py-1 rounded-md border font-semibold transition-all ${
                            isPrimary ? "bg-coral text-white border-coral" : "bg-white text-gray-500 hover:border-gray-300"
                          }`}
                        >
                          {isPrimary ? "使用中" : "设为主引擎"}
                        </button>
                        <div onClick={() => setExpandedProvider(isExpanded ? "" : provider.id)} className="text-gray-400 hover:text-coral p-1">
                          {isExpanded ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
                        </div>
                      </div>
                    </div>

                    {/* Accordion Expanded Body */}
                    {isExpanded && (
                      <div className="p-4 border-t border-gray-100 bg-white space-y-4 animate-in slide-in-from-top-2 duration-150">
                        <div className="space-y-1">
                          <label className="text-xs font-semibold text-gray-500">API 密钥 (API Key)</label>
                          <input
                            type="password"
                            value={apiKey}
                            onChange={(e) => updateProviderKey(provider.id, e.target.value)}
                            placeholder={`请输入 ${provider.name} 的接入密钥`}
                            className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-xs rounded-lg outline-none transition-all"
                            required={isPrimary}
                          />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-gray-500">接口代理地址 (Base URL)</label>
                            <input
                              type="text"
                              value={baseUrl}
                              onChange={(e) => {
                                if (provider.id === "custom") {
                                  setConfigs((p: any) => ({ ...p, CUSTOM_BASE_URL: e.target.value }));
                                }
                              }}
                              readOnly={provider.id !== "custom"}
                              placeholder="https://api.openai.com/v1"
                              className={`w-full border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-xs rounded-lg outline-none transition-all ${
                                provider.id === "custom" ? "bg-background border-border" : "bg-gray-50 border-gray-100 text-gray-400 cursor-not-allowed"
                              }`}
                            />
                          </div>

                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-gray-500">模型名称 (Model)</label>
                            {modelList.length > 0 ? (
                              <select
                                value={currentModel}
                                onChange={(e) => {
                                  if (provider.id === "custom") {
                                    setConfigs((p: any) => ({ ...p, CUSTOM_MODEL: e.target.value }));
                                  } else if (isPrimary) {
                                    setConfigs((p: any) => ({ ...p, LLM_MODEL: e.target.value }));
                                  }
                                }}
                                className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-xs rounded-lg outline-none transition-all"
                              >
                                {modelList.map(m => (
                                  <option key={m} value={m}>{m}</option>
                                ))}
                                <option value="custom-input">➕ 自定义输入...</option>
                              </select>
                            ) : (
                              <input
                                type="text"
                                value={currentModel}
                                onChange={(e) => {
                                  if (provider.id === "custom") {
                                    setConfigs((p: any) => ({ ...p, CUSTOM_MODEL: e.target.value }));
                                  } else if (isPrimary) {
                                    setConfigs((p: any) => ({ ...p, LLM_MODEL: e.target.value }));
                                  }
                                }}
                                placeholder="例如: deepseek-chat"
                                className="w-full bg-background border border-border focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-xs rounded-lg outline-none transition-all"
                              />
                            )}
                          </div>
                        </div>

                        {/* Test connection row */}
                        <div className="bg-gray-50 rounded-xl p-3.5 flex items-center justify-between border border-gray-100/50">
                          <div>
                            <span className="text-xs font-semibold text-charcoal">通道连通性与模型探测</span>
                            <p className="text-[10px] text-gray-400 mt-0.5">连通后将自动为您拉取中转或官方支持的模型供下拉切换</p>
                          </div>
                          <button
                            type="button"
                            disabled={testingId !== null || !apiKey || !baseUrl}
                            onClick={() => handleTest(provider.id, apiKey, baseUrl, currentModel)}
                            className="bg-white text-gray-600 hover:text-coral border border-gray-200 hover:border-coral/40 px-3.5 py-1.5 text-xs font-medium rounded-lg shadow-sm flex items-center gap-1.5 transition-all disabled:opacity-50"
                          >
                            {testingId === provider.id ? <Loader2 className="size-3 animate-spin text-coral" /> : <Play className="size-3 text-coral fill-coral" />}
                            {testingId === provider.id ? "测试中..." : "测试连接并拉取模型"}
                          </button>
                        </div>

                        {testRes && (
                          <div className={`p-3 rounded-lg text-xs flex items-center gap-1.5 ${
                            testRes.ok ? "bg-emerald-50 text-emerald-700 border border-emerald-100" : "bg-rose-50 text-rose-700 border border-rose-100"
                          }`}>
                            <span className="text-sm">{testRes.ok ? "✅" : "❌"}</span>
                            <span className="font-semibold">{testRes.msg}</span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className="flex items-center justify-end gap-2 border-t pt-4 mt-6">
              <button
                type="submit"
                disabled={saving}
                className="bg-coral text-white hover:bg-coral/95 active:scale-95 disabled:opacity-50 px-6 py-2.5 text-sm font-semibold rounded-xl flex items-center gap-1.5 shadow-md shadow-coral/10 transition-all"
              >
                {saving && <Loader2 className="size-4 animate-spin" />}
                {saving ? "应用中..." : "应用大模型配置"}
              </button>
            </div>
          </form>
        )}

        {showToast && (
          <div className="fixed bottom-6 right-6 bg-gray-900/95 text-white px-4 py-2.5 rounded-xl text-xs flex items-center gap-1.5 shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-300 z-50">
            <Check className="size-4 text-emerald-400" />
            <span>配置更新成功！大模型引擎已无缝热加载生效。</span>
          </div>
        )}
      </div>
    );
  }
  ```

- [ ] **Step 2: 提交代码**
  运行: `git add web/src/components/thread/history/LlmConfigPage.tsx`
  运行: `git commit -m "frontend: create LlmConfigPage component with LobeChat style accordions and dynamic dropdowns"`

---

### Task 5: 侧边栏与主画布切换集成

**Files:**
- Modify: `e:/小红书智能体/web/src/components/thread/history/index.tsx`
- Modify: `e:/小红书智能体/web/src/components/thread/index.tsx`

- [ ] **Step 1: 重构 sidebar/history/index.tsx 的按钮布局**
  更新 `SidebarBody` 的 Props 结构与头部按钮渲染。将原有的单个配置齿轮按钮替换为并排的两个 `Sparkles` 和 `SlidersHorizontal` 图标按钮：
  
  ```typescript
  // 修改 SidebarBody 签名接收 onLlmConfigOpen 和 onFeishuConfigOpen
  function SidebarBody({
    onLlmConfigOpen,
    onFeishuConfigOpen,
  }: {
    onLlmConfigOpen: () => void;
    onFeishuConfigOpen: () => void;
  }) {
    // ...
  ```
  
  在 Sidebar 品牌头部的右侧并排渲染两个按钮：
  
  ```typescript
  {/* 品牌区 */}
  <div className="flex items-center justify-between px-4 pt-4 pb-3">
    <div className="flex items-center gap-2">
      <span className="bg-primary text-primary-foreground flex size-7 items-center justify-center rounded-lg text-sm">
        {BRAND.mark}
      </span>
      <span className="text-foreground text-[15px] font-semibold">{BRAND.name}</span>
    </div>
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        title="大模型配置"
        onClick={onLlmConfigOpen}
        className="size-8 text-gray-400 hover:text-coral transition-colors"
      >
        <Sparkles className="size-4" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        title="飞书同步配置"
        onClick={onFeishuConfigOpen}
        className="size-8 text-gray-400 hover:text-coral transition-colors"
      >
        <SlidersHorizontal className="size-4" />
      </Button>
    </div>
  </div>
  ```
  
  同时，重构 `ThreadHistory` 主入口，将底部的 `ConfigModal` 彻底移除。不再在此处渲染任何弹窗：
  
  ```typescript
  export default function ThreadHistory() {
    const isLargeScreen = useMediaQuery("(min-width: 1024px)");
    const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
      "chatHistoryOpen",
      parseAsBoolean.withDefault(false),
    );
    const [, setView] = useQueryState("view");

    return (
      <>
        <div className="hidden h-screen w-[300px] shrink-0 flex-col border-r lg:flex">
          <SidebarBody 
            onLlmConfigOpen={() => setView("llm")} 
            onFeishuConfigOpen={() => setView("feishu")} 
          />
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
              <SidebarBody 
                onLlmConfigOpen={() => setView("llm")} 
                onFeishuConfigOpen={() => setView("feishu")} 
              />
            </SheetContent>
          </Sheet>
        </div>
      </>
    );
  }
  ```

- [ ] **Step 2: 重构 web/src/components/thread/index.tsx 实现全屏页面平滑切换**
  在主视图中引入 `view` query state。当 `view === "llm"` 时，替换主面板（聊天窗口）为 `<LlmConfigPage />`；当 `view === "feishu"` 时，替换主面板为 `<FeishuConfigPage />`。并且，当点击最近会话或新对话时，自动清空 `view` 切回聊天：
  
  ```typescript
  // 1. 引入 LlmConfigPage 和 FeishuConfigPage
  import { LlmConfigPage } from "./history/LlmConfigPage";
  import { FeishuConfigPage } from "./history/FeishuConfigPage";
  
  // 2. 在 Thread 组件内部：
  const [view, setView] = useQueryState("view");
  
  // 3. 在聊天面板的 motion.div 内：
  <motion.div
    className={cn(
      "relative flex min-w-0 flex-1 flex-col overflow-hidden",
      !chatStarted && "grid-rows-[1fr]"
    )}
    // ...
  >
    {view === "llm" ? (
      <LlmConfigPage onClose={() => setView(null)} />
    ) : view === "feishu" ? (
      <FeishuConfigPage onClose={() => setView(null)} />
    ) : (
      // 原有的正常聊天渲染...
      <>
        {!chatStarted && (
           // ...
        )}
        {chatStarted && (
           // ...
        )}
        <StickToBottom className="relative flex-1 overflow-hidden">
           // ...
        </StickToBottom>
      </>
    )}
  </motion.div>
  ```
  
  确保在 `setThreadId`（选择新对话或点击切换历史对话）触发时，自动调用 `setView(null)` 清空配置页，平滑切回对话状态。

- [ ] **Step 3: 进行编译与类型验证**
  在 `web` 目录下运行: `npx tsc --noEmit`
  Expected: PASS, 无 TypeScript 报错。

- [ ] **Step 4: 提交代码**
  运行: `git add web/src/components/thread/history/index.tsx web/src/components/thread/index.tsx`
  运行: `git commit -m "frontend: integrate full-page configuration views switching with sidebar buttons"`

---

### Task 6: 部署部署并在线联调验证

**Files:**
- None (执行部署命令)

- [ ] **Step 1: 运行腾讯云自动部署脚本**
  在项目根目录下运行: `uv run python tools/deploy.py`
  Expected: 部署脚本运行成功，PM2 进程显示在线且配置成功重启同步。

- [ ] **Step 2: 验证线上时延探测与下拉选择**
  打开网页，点击 🤖 图标切换到大模型配置界面，在 DeepSeek 面板填入 API Key 并点击 `测试连接并拉取模型`。
  Expected: 返回延迟（如 80ms），并且右侧的 Model 文本框自动变成了下拉菜单，能够正常选择。

- [ ] **Step 3: 验证飞书表格同步写入**
  点击 ⚙️ 图标切换到飞书同步界面，修改 Table ID 并点击保存。
  Expected: 配置热同步成功，重新打开页面能正确读回修改后的值，且 `.env` 中大模型 Key 未受损。
