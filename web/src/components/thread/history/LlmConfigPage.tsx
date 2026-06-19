import { useState, useEffect } from "react";
import { Sparkles, Loader2, Check, ArrowLeft, ChevronDown, ChevronRight, Play, Server, Cpu, Key, Activity, ListRestart, HelpCircle, ShieldCheck, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PasswordInput } from "@/components/ui/password-input";
import { Label } from "@/components/ui/label";

interface ProviderInfo {
  id: string;
  name: string;
  emoji: string;
  defaultUrl: string;
  defaultModel: string;
  providerVal: "openai" | "anthropic" | "google_genai";
  envKey: string;
  placeholderKey: string;
}

const PROVIDERS: ProviderInfo[] = [
  {
    id: "deepseek",
    name: "DeepSeek (深度求索)",
    emoji: "🇨🇳",
    defaultUrl: "https://api.deepseek.com/v1",
    defaultModel: "deepseek-chat",
    providerVal: "openai",
    envKey: "DEEPSEEK_API_KEY",
    placeholderKey: "sk-...",
  },
  {
    id: "kimi",
    name: "Kimi / Moonshot (月之暗面)",
    emoji: "🌙",
    defaultUrl: "https://api.moonshot.cn/v1",
    defaultModel: "moonshot-v1-8k",
    providerVal: "openai",
    envKey: "KIMI_API_KEY",
    placeholderKey: "sk-...",
  },
  {
    id: "openai",
    name: "OpenAI (GPT)",
    emoji: "🤖",
    defaultUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-4o",
    providerVal: "openai",
    envKey: "OPENAI_API_KEY",
    placeholderKey: "sk-...",
  },
  {
    id: "anthropic",
    name: "Anthropic (Claude)",
    emoji: "🎨",
    defaultUrl: "https://api.anthropic.com",
    defaultModel: "claude-3-5-sonnet-latest",
    providerVal: "anthropic",
    envKey: "ANTHROPIC_API_KEY",
    placeholderKey: "sk-ant-...",
  },
  {
    id: "gemini",
    name: "Google Gemini",
    emoji: "♊",
    defaultUrl: "https://generativelanguage.googleapis.com",
    defaultModel: "gemini-2.5-flash",
    providerVal: "google_genai",
    envKey: "GEMINI_API_KEY",
    placeholderKey: "AIzaSy...",
  },
  {
    id: "custom",
    name: "自定义中转代理 (One API 等)",
    emoji: "⚙️",
    defaultUrl: "",
    defaultModel: "",
    providerVal: "openai",
    envKey: "CUSTOM_API_KEY",
    placeholderKey: "请输入自定义密钥",
  },
];

interface ProviderConfig {
  apiKey: string;
  baseUrl: string;
  model: string;
}

export function LlmConfigPage({ onClose }: { onClose: () => void }) {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showToast, setShowToast] = useState(false);

  const [configs, setConfigs] = useState<any>({});
  const [primaryProvider, setPrimaryProvider] = useState<string>("deepseek");
  const [expandedProvider, setExpandedProvider] = useState<string>("deepseek");

  // Keep track of configs per provider locally
  const [providerConfigs, setProviderConfigs] = useState<Record<string, ProviderConfig>>({
    deepseek: { apiKey: "", baseUrl: "https://api.deepseek.com/v1", model: "deepseek-chat" },
    kimi: { apiKey: "", baseUrl: "https://api.moonshot.cn/v1", model: "moonshot-v1-8k" },
    openai: { apiKey: "", baseUrl: "https://api.openai.com/v1", model: "gpt-4o" },
    anthropic: { apiKey: "", baseUrl: "https://api.anthropic.com", model: "claude-3-5-sonnet-latest" },
    gemini: { apiKey: "", baseUrl: "https://generativelanguage.googleapis.com", model: "gemini-2.5-flash" },
    custom: { apiKey: "", baseUrl: "", model: "" },
  });

  // Track latency test results and list of discovered models
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; latency?: number; error?: string } | undefined>>({});
  const [discoveredModels, setDiscoveredModels] = useState<Record<string, string[]>>({});
  // If true, shows the select dropdown, otherwise shows raw text input
  const [modelDropdownModes, setModelDropdownModes] = useState<Record<string, boolean>>({});

  useEffect(() => {
    setLoading(true);
    fetch("/api/config")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok && data.configs) {
          const c = data.configs;
          setConfigs(c);

          // Infer active primary provider
          const providerEnv = (c.LLM_PROVIDER || "openai").toLowerCase();
          const qualityModels = c.LLM_QUALITY_MODELS || c.LLM_MODEL || "";
          const modelLower = qualityModels.toLowerCase();
          const urlLower = (c.LLM_BASE_URL || "").toLowerCase();

          let current = "deepseek";
          if (providerEnv === "anthropic") {
            current = "anthropic";
          } else if (providerEnv === "google_genai") {
            current = "gemini";
          } else if (modelLower.includes("deepseek") || urlLower.includes("deepseek")) {
            current = "deepseek";
          } else if (modelLower.includes("moonshot") || modelLower.includes("kimi") || urlLower.includes("moonshot")) {
            current = "kimi";
          } else if (modelLower.includes("gpt") || modelLower.includes("o1") || modelLower.includes("o3") || urlLower.includes("openai")) {
            current = "openai";
          } else if (c.LLM_BASE_URL && c.LLM_API_KEY) {
            current = "custom";
          }

          setPrimaryProvider(current);
          setExpandedProvider(current);

          // Map initial values into separate providerConfigs state
          setProviderConfigs((prev) => {
            const next = { ...prev };
            
            // DeepSeek
            next.deepseek = {
              apiKey: c.DEEPSEEK_API_KEY || (current === "deepseek" ? c.LLM_API_KEY : ""),
              baseUrl: current === "deepseek" ? c.LLM_BASE_URL : "https://api.deepseek.com/v1",
              model: current === "deepseek" ? qualityModels : "deepseek-chat",
            };

            // Kimi
            next.kimi = {
              apiKey: c.KIMI_API_KEY || (current === "kimi" ? c.LLM_API_KEY : ""),
              baseUrl: current === "kimi" ? c.LLM_BASE_URL : "https://api.moonshot.cn/v1",
              model: current === "kimi" ? qualityModels : "moonshot-v1-8k",
            };

            // OpenAI
            next.openai = {
              apiKey: c.OPENAI_API_KEY || (current === "openai" ? c.LLM_API_KEY : ""),
              baseUrl: current === "openai" ? c.LLM_BASE_URL : "https://api.openai.com/v1",
              model: current === "openai" ? qualityModels : "gpt-4o",
            };

            // Anthropic
            next.anthropic = {
              apiKey: c.ANTHROPIC_API_KEY || (current === "anthropic" ? c.LLM_API_KEY : ""),
              baseUrl: current === "anthropic" ? c.LLM_BASE_URL : "https://api.anthropic.com",
              model: current === "anthropic" ? qualityModels : "claude-3-5-sonnet-latest",
            };

            // Gemini
            next.gemini = {
              apiKey: c.GEMINI_API_KEY || (current === "gemini" ? c.LLM_API_KEY : ""),
              baseUrl: current === "gemini" ? c.LLM_BASE_URL : "https://generativelanguage.googleapis.com",
              model: current === "gemini" ? qualityModels : "gemini-2.5-flash",
            };

            // Custom
            next.custom = {
              apiKey: current === "custom" ? c.LLM_API_KEY : "",
              baseUrl: current === "custom" ? c.LLM_BASE_URL : "",
              model: current === "custom" ? qualityModels : "",
            };

            return next;
          });
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleTest = async (providerId: string) => {
    const targetConfig = providerConfigs[providerId];
    const apiKey = targetConfig.apiKey?.trim();
    const baseUrl = targetConfig.baseUrl?.trim();
    
    let model = targetConfig.model?.trim();
    // Default model fallback if empty during test
    if (!model) {
      const info = PROVIDERS.find((p) => p.id === providerId);
      model = info?.defaultModel || "gpt-4o";
    }

    if (!apiKey) {
      alert("请输入 API 密钥后再进行连接测试");
      return;
    }
    if (!baseUrl) {
      alert("请输入接口代理地址 (Base URL) 后再进行连接测试");
      return;
    }

    setTestingId(providerId);
    setTestResults((prev) => ({ ...prev, [providerId]: undefined }));

    try {
      const res = await fetch("/api/config/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ apiKey, baseUrl, model }),
      });
      const data = await res.json();
      if (data.ok) {
        setTestResults((prev) => ({
          ...prev,
          [providerId]: { ok: true, latency: data.latency },
        }));

        if (data.models && Array.isArray(data.models) && data.models.length > 0) {
          setDiscoveredModels((prev) => ({ ...prev, [providerId]: data.models }));
          setModelDropdownModes((prev) => ({ ...prev, [providerId]: true }));
        }
      } else {
        setTestResults((prev) => ({
          ...prev,
          [providerId]: { ok: false, error: data.error || "连接测试失败" },
        }));
      }
    } catch (err: any) {
      setTestResults((prev) => ({
        ...prev,
        [providerId]: { ok: false, error: err.message || "请求异常" },
      }));
    } finally {
      setTestingId(null);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);

    const activeConfig = providerConfigs[primaryProvider];
    const targetInfo = PROVIDERS.find((p) => p.id === primaryProvider)!;

    const finalConfigs = {
      // Keep existing Feishu configs
      FEISHU_APP_ID: configs.FEISHU_APP_ID || "",
      FEISHU_APP_SECRET: configs.FEISHU_APP_SECRET || "",
      FEISHU_BITABLE_APP_TOKEN: configs.FEISHU_BITABLE_APP_TOKEN || "",
      FEISHU_BITABLE_TABLE_ID: configs.FEISHU_BITABLE_TABLE_ID || "",

      // Set primary model settings
      LLM_PROVIDER: targetInfo.providerVal,
      LLM_API_KEY: activeConfig.apiKey?.trim() || "",
      LLM_BASE_URL: activeConfig.baseUrl?.trim() || "",
      LLM_QUALITY_MODELS:
        activeConfig.model
          ?.split(",")
          .map((item) => item.trim())
          .filter(Boolean)
          .join(",") || "",
    };

    try {
      const res = await fetch("/api/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ configs: finalConfigs }),
      });
      if (res.ok) {
        setShowToast(true);
        setTimeout(() => {
          setShowToast(false);
          onClose();
        }, 1500);
      } else {
        alert("保存配置失败，请检查输入项");
      }
    } catch (err) {
      console.error(err);
      alert("网络请求异常，保存配置失败");
    } finally {
      setSaving(false);
    }
  };

  const updateProviderConfig = (providerId: string, updates: Partial<ProviderConfig>) => {
    setProviderConfigs((prev) => ({
      ...prev,
      [providerId]: {
        ...prev[providerId],
        ...updates,
      },
    }));
  };

  return (
    <div className="flex flex-col h-full w-full bg-oats p-6 overflow-y-auto text-left custom-scrollbar">
      {/* Header */}
      <div className="flex justify-between items-center border-b border-border/80 pb-4 mb-6">
        <div>
          <h2 className="text-lg font-bold text-charcoal flex items-center gap-2">
            <Sparkles className="size-5 text-coral animate-pulse" />
            AI 模型引擎与灾备配置
          </h2>
          <p className="text-xs text-charcoal-light mt-1">
            配置您的各个大模型服务商 API 密钥与网关。当主引擎发生限流/报错时，系统将自动顺延重试备用密钥。
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onClose} className="text-xs flex items-center gap-1 bg-white hover:bg-oats-dark border-border/60 text-charcoal">
          <ArrowLeft className="size-3" /> 返回会话
        </Button>
      </div>

      {loading ? (
        <div className="space-y-4 py-8">
          <div className="h-6 bg-oats-dark rounded animate-pulse w-1/4" />
          <div className="h-20 bg-oats-dark rounded animate-pulse w-full" />
          <div className="h-20 bg-oats-dark rounded animate-pulse w-full" />
        </div>
      ) : (
        <form onSubmit={handleSave} className="w-full max-w-7xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] xl:grid-cols-[1fr_400px] gap-8 items-start">
            {/* 左侧：核心配置面板 */}
            <div className="space-y-6 bg-white/40 p-5 rounded-2xl border border-border/30 backdrop-blur-xs">
              {/* LobeChat style Accordion List */}
              <div className="space-y-3.5">
            {PROVIDERS.map((provider) => {
              const isExpanded = expandedProvider === provider.id;
              const isPrimary = primaryProvider === provider.id;
              const config = providerConfigs[provider.id] || { apiKey: "", baseUrl: "", model: "" };
              const test = testResults[provider.id];
              const modelsList = discoveredModels[provider.id] || [];
              const isDropdownMode = modelDropdownModes[provider.id] && modelsList.length > 0;

              return (
                <div
                  key={provider.id}
                  className={`bg-white border rounded-xl overflow-hidden transition-all duration-200 ${
                    isPrimary
                      ? "border-coral/40 shadow-[0_4px_12px_rgba(255,36,66,0.04)] ring-1 ring-coral/10"
                      : "border-oats-dark/80 shadow-sm hover:border-coral/20"
                  }`}
                >
                  {/* Accordion Trigger/Header */}
                  <div
                    onClick={() => setExpandedProvider(isExpanded ? "" : provider.id)}
                    className={`flex justify-between items-center px-4 py-3.5 cursor-pointer select-none transition-colors ${
                      isPrimary ? "bg-coral-light/20 hover:bg-coral-light/35" : "bg-white hover:bg-oats-light/50"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-xl shrink-0">{provider.emoji}</span>
                      <div className="flex flex-col">
                        <span className={`font-semibold text-sm ${isPrimary ? "text-coral" : "text-charcoal"}`}>
                          {provider.name}
                        </span>
                        {config.apiKey && !isPrimary && (
                          <span className="text-[10px] text-gray-400 mt-0.5">备用通道已配置</span>
                        )}
                      </div>
                      {isPrimary && (
                        <span className="bg-coral text-white text-[9px] px-2 py-0.5 rounded-full font-bold scale-90">
                          当前主引擎
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
                      <button
                        type="button"
                        onClick={() => {
                          setPrimaryProvider(provider.id);
                          setExpandedProvider(provider.id);
                        }}
                        className={`text-xs px-2.5 py-1 rounded-lg border font-medium transition-all active:scale-95 cursor-pointer ${
                          isPrimary
                            ? "bg-coral text-white border-coral shadow-sm shadow-coral/15"
                            : "bg-white text-charcoal hover:border-coral/40 border-border/80"
                        }`}
                      >
                        {isPrimary ? "使用中" : "设为主引擎"}
                      </button>
                      <div
                        onClick={() => setExpandedProvider(isExpanded ? "" : provider.id)}
                        className="text-charcoal-light hover:text-coral p-1 rounded-md transition-colors"
                      >
                        {isExpanded ? <ChevronDown className="size-4 rotate-180 transition-transform duration-200" /> : <ChevronDown className="size-4 transition-transform duration-200" />}
                      </div>
                    </div>
                  </div>

                  {/* Accordion Body */}
                  {isExpanded && (
                    <div className="p-5 border-t border-oats-dark/60 bg-white space-y-4 animate-in slide-in-from-top-2 duration-150">
                      {/* API Key */}
                      <div className="space-y-1.5">
                        <Label htmlFor={`api-key-${provider.id}`} className="text-xs font-semibold text-charcoal-light flex items-center gap-1">
                          <Key className="size-3.5 text-coral/80" />
                          API 密钥 (API Key) {isPrimary && <span className="text-coral font-bold">*</span>}
                        </Label>
                        <PasswordInput
                          id={`api-key-${provider.id}`}
                          value={config.apiKey}
                          onChange={(e) => updateProviderConfig(provider.id, { apiKey: e.target.value })}
                          placeholder={provider.placeholderKey}
                          required={isPrimary}
                          className="bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 rounded-lg text-xs"
                        />
                      </div>

                      {/* Base URL & Model */}
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Base URL */}
                        <div className="space-y-1.5">
                          <Label htmlFor={`base-url-${provider.id}`} className="text-xs font-semibold text-charcoal-light flex items-center gap-1">
                            <Server className="size-3.5 text-coral/80" />
                            接口代理地址 (Base URL)
                          </Label>
                          <Input
                            id={`base-url-${provider.id}`}
                            type="text"
                            value={config.baseUrl}
                            onChange={(e) => {
                              if (provider.id === "custom") {
                                updateProviderConfig(provider.id, { baseUrl: e.target.value });
                              }
                            }}
                            readOnly={provider.id !== "custom"}
                            placeholder="官方通道使用默认地址"
                            className={`rounded-lg text-xs ${
                              provider.id === "custom"
                                ? "bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20"
                                : "bg-oats-light/20 border-oats-dark text-gray-400 cursor-not-allowed select-none"
                            }`}
                          />
                        </div>

                        {/* Model */}
                        <div className="space-y-1.5">
                          <Label htmlFor={`model-${provider.id}`} className="text-xs font-semibold text-charcoal-light flex items-center justify-between">
                            <span className="flex items-center gap-1">
                              <Cpu className="size-3.5 text-coral/80" />
                              高质量模型池 (LLM_QUALITY_MODELS)
                            </span>
                            {isDropdownMode && (
                              <button
                                type="button"
                                onClick={() => setModelDropdownModes((prev) => ({ ...prev, [provider.id]: false }))}
                                className="text-[10px] text-coral hover:underline flex items-center gap-0.5"
                              >
                                手动输入
                              </button>
                            )}
                          </Label>
                          <div className="relative">
                            {isDropdownMode ? (
                              <select
                                id={`model-${provider.id}`}
                                value={config.model}
                                onChange={(e) => {
                                  if (e.target.value === "__custom__") {
                                    setModelDropdownModes((prev) => ({ ...prev, [provider.id]: false }));
                                  } else {
                                    updateProviderConfig(provider.id, { model: e.target.value });
                                  }
                                }}
                                className="w-full bg-oats-light/40 border border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 px-3 py-2 text-xs rounded-lg outline-none transition-all cursor-pointer"
                              >
                                {modelsList.map((m) => (
                                  <option key={m} value={m}>
                                    {m}
                                  </option>
                                ))}
                                <option value="__custom__">➕ 自定义输入...</option>
                              </select>
                            ) : (
                              <div className="flex gap-2">
                                <Input
                                  id={`model-${provider.id}`}
                                  type="text"
                                  value={config.model}
                                  onChange={(e) => updateProviderConfig(provider.id, { model: e.target.value })}
                                  placeholder="请输入模型 ID，多个模型用英文逗号分隔，如 gpt-4o,claude-sonnet-4-6"
                                  className="bg-oats-light/40 border-border/60 focus:border-coral focus:ring-1 focus:ring-coral/20 rounded-lg text-xs flex-1"
                                />
                                {modelsList.length > 0 && (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    onClick={() => setModelDropdownModes((prev) => ({ ...prev, [provider.id]: true }))}
                                    title="恢复下拉列表"
                                    className="p-2 border border-border/60 hover:bg-oats-dark/60 rounded-lg"
                                  >
                                    <ListRestart className="size-3.5 text-charcoal-light" />
                                  </Button>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Connection Test Section */}
                      <div className="bg-oats-light/35 border border-border/40 rounded-xl p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 mt-3">
                        <div className="flex items-start gap-2.5">
                          <Activity className="size-4.5 text-coral shrink-0 mt-0.5" />
                          <div>
                            <span className="text-xs font-bold text-charcoal">通道连通性测试</span>
                            <p className="text-[10px] text-gray-400 mt-0.5">
                              一键测试网络延迟，成功后会自动拉取网关支持的所有模型名称列表。
                            </p>
                          </div>
                        </div>

                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          disabled={testingId !== null || !config.apiKey}
                          onClick={() => handleTest(provider.id)}
                          className="text-xs font-semibold text-charcoal-light hover:text-coral border border-border bg-white hover:bg-oats-light flex items-center gap-1.5 shrink-0 self-end sm:self-auto cursor-pointer disabled:opacity-50"
                        >
                          {testingId === provider.id ? (
                            <Loader2 className="size-3.5 animate-spin text-coral" />
                          ) : (
                            <Play className="size-3.5 text-coral fill-coral" />
                          )}
                          {testingId === provider.id ? "测试中..." : "测试连接并拉取模型"}
                        </Button>
                      </div>

                      {/* Connection Test Status Output */}
                      {test && (
                        <div
                          className={`p-3 rounded-xl border text-xs flex items-center gap-2 transition-all ${
                            test.ok
                              ? "bg-emerald-50/60 border-emerald-100/80 text-emerald-800"
                              : "bg-rose-50/60 border-rose-100/80 text-rose-800"
                          }`}
                        >
                          <span className="text-sm shrink-0">{test.ok ? "🟢" : "🔴"}</span>
                          <div className="flex-1 min-w-0">
                            {test.ok ? (
                              <span className="font-semibold">
                                连接成功！网络延迟: <span className="underline decoration-wavy font-bold">{test.latency}ms</span>
                                {modelsList.length > 0 && `，已为您解锁 ${modelsList.length} 个可用模型进行下拉切换。`}
                              </span>
                            ) : (
                              <span className="font-semibold break-words">
                                无法连接到服务商: {test.error}
                              </span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

              {/* Form Actions Footer */}
              <div className="flex items-center justify-end gap-3 border-t border-border/80 pt-5 mt-8">
                <Button
                  type="button"
                  variant="ghost"
                  disabled={saving}
                  onClick={onClose}
                  className="text-xs hover:bg-oats-dark/60 rounded-xl"
                >
                  取消
                </Button>
                <Button
                  type="submit"
                  disabled={saving}
                  className="bg-coral hover:bg-coral-hover text-white active:scale-95 disabled:opacity-50 px-6 py-2.5 text-sm font-semibold rounded-xl flex items-center gap-1.5 shadow-md shadow-coral/10 transition-all cursor-pointer border-none"
                >
                  {saving && <Loader2 className="size-4 animate-spin" />}
                  {saving ? "正在应用..." : "应用大模型配置"}
                </Button>
              </div>
            </div>

            {/* 右侧：高级面板/指南 */}
            <div className="hidden lg:flex flex-col gap-6 sticky top-0">
              {/* 灾备重试机制说明卡片 */}
              <div className="bg-white border border-border/60 rounded-2xl p-5 space-y-4 shadow-sm text-xs">
                <h3 className="font-bold text-charcoal flex items-center gap-1.5 border-b pb-2">
                  <RefreshCw className="size-4 text-coral animate-spin animate-duration-3000" style={{ animationDuration: '6s' }} />
                  自动灾备重试机制
                </h3>
                <p className="text-charcoal-light leading-relaxed">
                  系统采用<strong>主备容灾路由</strong>设计。当您的主引擎（当前选中的主通道）在产出文案时遇到服务超限、接口报错或网络超时，系统将无缝顺延重试您已配置了密钥的备用提供商，确保生产环境的业务连续性。
                </p>

                {/* 精致的流程微图 */}
                <div className="flex items-center justify-between bg-oats-light/40 border border-border/30 rounded-xl p-3 text-[10px] select-none">
                  <div className="flex flex-col items-center gap-1 flex-1">
                    <span className="bg-coral/10 text-coral font-bold size-5 flex items-center justify-center rounded-full">1</span>
                    <span className="font-semibold text-charcoal text-center">主引擎调用</span>
                  </div>
                  <div className="text-coral/50 font-bold shrink-0">➔</div>
                  <div className="flex flex-col items-center gap-1 flex-1">
                    <span className="bg-coral/10 text-coral font-bold size-5 flex items-center justify-center rounded-full">2</span>
                    <span className="font-semibold text-charcoal text-center">失败防灾检测</span>
                  </div>
                  <div className="text-coral/50 font-bold shrink-0">➔</div>
                  <div className="flex flex-col items-center gap-1 flex-1">
                    <span className="bg-emerald-100 text-emerald-700 font-bold size-5 flex items-center justify-center rounded-full">3</span>
                    <span className="font-semibold text-charcoal text-center">备用重接托管</span>
                  </div>
                </div>
              </div>

              {/* 最佳实践说明 */}
              <div className="bg-white border border-border/60 rounded-2xl p-5 space-y-3.5 shadow-sm text-xs">
                <h3 className="font-bold text-charcoal flex items-center gap-1.5 border-b pb-2">
                  <HelpCircle className="size-4 text-coral" />
                  配置最佳实践
                </h3>
                <ul className="space-y-2.5 text-charcoal-light list-disc list-inside leading-relaxed">
                  <li>
                    <strong className="text-charcoal">多模态图片理解：</strong>
                    为了从上传的露营、穿搭、护肤等小红书商品图里深度理解画面细节并提炼卖点，建议配置支持 Vision 的模型（如 <code className="bg-oats/60 px-1 py-0.5 rounded text-[10px]">claude-3-5-sonnet-latest</code> 或 <code className="bg-oats/60 px-1 py-0.5 rounded text-[10px]">gemini-2.5-flash</code>）。
                  </li>
                  <li>
                    <strong className="text-charcoal">一键智能测速：</strong>
                    在左侧填入密钥并点击“测试连接并拉取模型”后，系统不仅会测试网络连通时间，还会动态请求网关支持的模型列表，点击下拉菜单即可极速切换。
                  </li>
                </ul>
              </div>

              {/* 安全承诺 */}
              <div className="bg-white border border-border/60 rounded-2xl p-5 space-y-2 shadow-sm text-[10px] text-charcoal-light flex items-start gap-2">
                <ShieldCheck className="size-4 text-emerald-500 shrink-0 mt-0.5" />
                <div>
                  <span className="font-semibold text-charcoal block mb-0.5">端到端存储隐私安全</span>
                  所有的 API 密钥仅保存在您本地部署的专属私有服务端（系统配置环境变量），仅在向官方 API 发送文案生成请求时动态透传，绝不向任何云端汇总上传。
                </div>
              </div>
            </div>
          </div>
        </form>
      )}

      {/* Toast Notification */}
      {showToast && (
        <div className="fixed bottom-6 right-6 bg-charcoal text-white px-4 py-2.5 rounded-xl text-xs flex items-center gap-1.5 shadow-xl animate-in fade-in slide-in-from-bottom-2 duration-300 z-50 border border-border/10">
          <Check className="size-4 text-emerald-400" />
          <span>大模型配置更新成功，已即时热重载生效！</span>
        </div>
      )}
    </div>
  );
}
