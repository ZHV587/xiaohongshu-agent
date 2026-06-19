import { useState, useEffect } from "react";
import { Sparkles, Loader2, Check, ArrowLeft, ChevronDown, ChevronRight, Play, Server, Cpu, Key, Activity, ListRestart } from "lucide-react";
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
          const modelLower = (c.LLM_MODEL || "").toLowerCase();
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
              model: current === "deepseek" ? c.LLM_MODEL : "deepseek-chat",
            };

            // Kimi
            next.kimi = {
              apiKey: c.KIMI_API_KEY || (current === "kimi" ? c.LLM_API_KEY : ""),
              baseUrl: current === "kimi" ? c.LLM_BASE_URL : "https://api.moonshot.cn/v1",
              model: current === "kimi" ? c.LLM_MODEL : "moonshot-v1-8k",
            };

            // OpenAI
            next.openai = {
              apiKey: c.OPENAI_API_KEY || (current === "openai" ? c.LLM_API_KEY : ""),
              baseUrl: current === "openai" ? c.LLM_BASE_URL : "https://api.openai.com/v1",
              model: current === "openai" ? c.LLM_MODEL : "gpt-4o",
            };

            // Anthropic
            next.anthropic = {
              apiKey: c.ANTHROPIC_API_KEY || (current === "anthropic" ? c.LLM_API_KEY : ""),
              baseUrl: current === "anthropic" ? c.LLM_BASE_URL : "https://api.anthropic.com",
              model: current === "anthropic" ? c.LLM_MODEL : "claude-3-5-sonnet-latest",
            };

            // Gemini
            next.gemini = {
              apiKey: c.GEMINI_API_KEY || (current === "gemini" ? c.LLM_API_KEY : ""),
              baseUrl: current === "gemini" ? c.LLM_BASE_URL : "https://generativelanguage.googleapis.com",
              model: current === "gemini" ? c.LLM_MODEL : "gemini-2.5-flash",
            };

            // Custom
            next.custom = {
              apiKey: current === "custom" ? c.LLM_API_KEY : "",
              baseUrl: current === "custom" ? c.LLM_BASE_URL : "",
              model: current === "custom" ? c.LLM_MODEL : "",
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
      LLM_MODEL: activeConfig.model?.trim() || "",

      // Back up keys for fallback and disaster recovery
      DEEPSEEK_API_KEY: providerConfigs.deepseek.apiKey?.trim() || "",
      KIMI_API_KEY: providerConfigs.kimi.apiKey?.trim() || "",
      OPENAI_API_KEY: providerConfigs.openai.apiKey?.trim() || "",
      ANTHROPIC_API_KEY: providerConfigs.anthropic.apiKey?.trim() || "",
      GEMINI_API_KEY: providerConfigs.gemini.apiKey?.trim() || "",
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
        <form onSubmit={handleSave} className="space-y-6 max-w-3xl">
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
                              模型名称 (Model)
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
                                  placeholder={provider.defaultModel || "请输入模型名称，如 gpt-4o"}
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
