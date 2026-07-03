import React, { ReactNode, useState, useEffect } from "react";
import { useQueryState } from "nuqs";
import { Button, Card, Icon, Input } from "@/components/ds";
import { getApiKey } from "@/lib/api-key";
import { isXhsTraceEvent } from "@/lib/agent-trace";
import { useThreads } from "./thread-context";
import { toBrowserApiUrl } from "./client";
import { toast } from "sonner";
import { TraceProvider } from "./trace-context";
import { useTraceContext } from "./trace-store";
import {
  StreamContext,
  isStreamUiEvent,
  reduceUiMessages,
  useTypedStream,
} from "./stream-context";

async function sleep(ms = 4000) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkGraphStatus(
  apiUrl: string,
  apiKey: string | null,
  authScheme?: string,
): Promise<boolean> {
  try {
    const headers = new Headers();
    if (apiKey) headers.set("X-Api-Key", apiKey);
    if (authScheme) headers.set("X-Auth-Scheme", authScheme);

    const res = await fetch(`${apiUrl}/info`, {
      headers,
      credentials: "same-origin",
    });

    return res.ok;
  } catch (e) {
    console.error(e);
    return false;
  }
}

const StreamSession = ({
  children,
  apiKey,
  apiUrl,
  assistantId,
  authScheme,
}: {
  children: ReactNode;
  apiKey: string | null;
  apiUrl: string;
  assistantId: string;
  authScheme?: string;
}) => {
  const [threadId, setThreadId] = useQueryState("threadId");
  const { getThreads, setThreads } = useThreads();
  const { appendTraceEvent } = useTraceContext();
  const streamValue = useTypedStream({
    apiUrl,
    apiKey: apiKey ?? undefined,
    assistantId,
    defaultHeaders: {
      ...(authScheme && { "X-Auth-Scheme": authScheme }),
      // BFF 模式:身份 JWT 在 httpOnly cookie 中,由同源 /api 代理在服务端注入 Bearer。
    },
    threadId: threadId ?? null,
    fetchStateHistory: true,
    onCustomEvent: (event, options) => {
      if (isStreamUiEvent(event)) {
        options.mutate((prev) => {
          const ui = reduceUiMessages(prev.ui, event);
          return { ...prev, ui };
        });
        return;
      }
      if (isXhsTraceEvent(event)) {
        appendTraceEvent(event);
      }
    },
    onThreadId: (id) => {
      setThreadId(id);
      // Refetch threads list when thread ID changes.
      // Wait for some seconds before fetching so we're able to get the new thread that was created.
      sleep().then(() => getThreads().then(setThreads).catch(console.error));
    },
  });

  useEffect(() => {
    checkGraphStatus(apiUrl, apiKey, authScheme).then((ok) => {
      if (!ok) {
        toast.error("无法连接到后端服务", {
          description: () => (
            <p>
              请确认后端服务已在 <code>{apiUrl}</code> 运行
              （若连接的是云端部署，请检查 API Key 是否正确设置）。
            </p>
          ),
          duration: 10000,
          richColors: true,
          closeButton: true,
        });
      }
    });
  }, [apiKey, apiUrl, authScheme]);

  return (
    <StreamContext.Provider value={streamValue}>
      {children}
    </StreamContext.Provider>
  );
};

// Default values for the form
const DEFAULT_API_URL = "http://localhost:2024";
const DEFAULT_ASSISTANT_ID = "agent";
const AGENT_BUILDER_AUTH_SCHEME = "langsmith-api-key";

function FieldLabel({
  htmlFor,
  children,
}: {
  htmlFor: string;
  children: ReactNode;
}) {
  return (
    <label
      htmlFor={htmlFor}
      style={{
        fontSize: "var(--text-xs)",
        fontWeight: 700,
        color: "var(--text-body)",
      }}
    >
      {children}
    </label>
  );
}

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  // Get environment variables
  const envApiUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL;
  const envAssistantId: string | undefined =
    process.env.NEXT_PUBLIC_ASSISTANT_ID;
  const envAuthScheme: string | undefined = process.env.NEXT_PUBLIC_AUTH_SCHEME;

  // Use URL params with env var fallbacks
  const [apiUrl, setApiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  const [assistantId, setAssistantId] = useQueryState("assistantId", {
    defaultValue: envAssistantId || "",
  });
  const [authScheme, setAuthScheme] = useQueryState("authScheme", {
    defaultValue: envAuthScheme || "",
  });
  const [isAgentBuilder, setIsAgentBuilder] = useState(
    () =>
      (authScheme || envAuthScheme || "").toLowerCase() ===
      AGENT_BUILDER_AUTH_SCHEME,
  );

  // For API key, use localStorage with env var fallback
  const [apiKey, _setApiKey] = useState(() => {
    const storedKey = getApiKey();
    return storedKey || "";
  });

  const setApiKey = (key: string) => {
    window.localStorage.setItem("lg:chat:apiKey", key);
    _setApiKey(key);
  };

  // Determine final values to use.
  // 安全:apiUrl 在生产固定为同源 env 值(/api),忽略 ?apiUrl= query 覆盖,
  // 防止绕过 BFF 代理直连任意后端(身份令牌注入只在代理服务端发生)。
  // 仅开发环境保留 query 覆盖,便于本地联调直连。
  const finalApiUrl =
    process.env.NODE_ENV === "development" ? apiUrl || envApiUrl : envApiUrl;
  const browserApiUrl = toBrowserApiUrl(finalApiUrl);
  const finalAssistantId = assistantId || envAssistantId;
  const finalAuthScheme = authScheme || envAuthScheme || "";

  // Show the form if we: don't have an API URL, or don't have an assistant ID
  if (!browserApiUrl || !finalAssistantId) {
    return (
      <div
        style={{
          minHeight: "100vh",
          width: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "var(--space-4)",
          background: "var(--background)",
        }}
      >
        <Card
          padding="none"
          style={{ width: "min(720px, 96vw)", overflow: "hidden" }}
        >
          <div
            style={{
              padding: "var(--space-6)",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-2)",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "var(--space-3)",
              }}
            >
              <span
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: "var(--radius-lg)",
                  background: "var(--coral-brand)",
                  color: "#fff",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 22,
                  boxShadow: "var(--shadow-coral)",
                }}
              >
                🍠
              </span>
              <h1
                style={{
                  margin: 0,
                  fontFamily: "var(--font-display)",
                  fontSize: "var(--text-xl)",
                  fontWeight: 800,
                  letterSpacing: "var(--tracking-tight)",
                }}
              >
                小红书文案助手
              </h1>
            </div>
            <p
              style={{
                margin: 0,
                color: "var(--text-muted)",
                fontSize: "var(--text-sm)",
                lineHeight: "var(--leading-relaxed)",
              }}
            >
              连接你的 LangGraph 服务后即可开始。请填写部署地址与图/助手 ID。
            </p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();

              const form = e.target as HTMLFormElement;
              const formData = new FormData(form);
              const apiUrl = formData.get("apiUrl") as string;
              const assistantId = formData.get("assistantId") as string;
              const apiKey = formData.get("apiKey") as string;

              setApiUrl(apiUrl);
              setApiKey(apiKey);
              setAssistantId(assistantId);
              setAuthScheme(isAgentBuilder ? AGENT_BUILDER_AUTH_SCHEME : "");

              form.reset();
            }}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-6)",
              padding: "var(--space-6)",
              background: "var(--surface-raised)",
            }}
          >
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-2)",
              }}
            >
              <FieldLabel htmlFor="apiUrl">
                部署地址<span style={{ color: "var(--primary)" }}>*</span>
              </FieldLabel>
              <p
                style={{
                  margin: 0,
                  color: "var(--text-muted)",
                  fontSize: "var(--text-sm)",
                }}
              >
                你的 LangGraph 服务地址，可以是本地或线上部署。
              </p>
              <Input
                id="apiUrl"
                name="apiUrl"
                defaultValue={apiUrl || DEFAULT_API_URL}
                required
              />
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-2)",
              }}
            >
              <FieldLabel htmlFor="assistantId">
                图 / 助手 ID<span style={{ color: "var(--primary)" }}>*</span>
              </FieldLabel>
              <p
                style={{
                  margin: 0,
                  color: "var(--text-muted)",
                  fontSize: "var(--text-sm)",
                }}
              >
                用于拉取会话并触发执行的图 ID（可填图名）或助手 ID。
              </p>
              <Input
                id="assistantId"
                name="assistantId"
                defaultValue={assistantId || DEFAULT_ASSISTANT_ID}
                required
              />
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-2)",
              }}
            >
              <FieldLabel htmlFor="apiKey">LangSmith API Key</FieldLabel>
              <p
                style={{
                  margin: 0,
                  color: "var(--text-muted)",
                  fontSize: "var(--text-sm)",
                }}
              >
                使用本地 LangGraph 服务时<strong>无需填写</strong>
                。该值仅保存在浏览器本地，用于向你的 LangGraph
                服务发起鉴权请求。
              </p>
              <Input
                id="apiKey"
                name="apiKey"
                type="password"
                defaultValue={apiKey ?? ""}
                placeholder="lsv2_pt_..."
              />
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-3)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "var(--space-4)",
                }}
              >
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 3 }}
                >
                  <FieldLabel htmlFor="agentBuilderEnabled">
                    使用 Agent Builder 构建
                  </FieldLabel>
                  <p
                    style={{
                      margin: 0,
                      color: "var(--text-muted)",
                      fontSize: "var(--text-sm)",
                    }}
                  >
                    Agent Builder 部署时开启此项。
                  </p>
                </div>
                <button
                  type="button"
                  id="agentBuilderEnabled"
                  role="switch"
                  aria-checked={isAgentBuilder}
                  onClick={() => setIsAgentBuilder((value) => !value)}
                  style={{
                    width: 46,
                    height: 26,
                    borderRadius: "var(--radius-full)",
                    border: `1px solid ${isAgentBuilder ? "var(--primary)" : "var(--border)"}`,
                    background: isAgentBuilder
                      ? "var(--primary)"
                      : "var(--oats-dark)",
                    padding: 2,
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: isAgentBuilder ? "flex-end" : "flex-start",
                    transition: "all var(--dur-fast) var(--ease-out)",
                  }}
                >
                  <span
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: "var(--radius-full)",
                      background: "#fff",
                      boxShadow: "var(--shadow-xs)",
                    }}
                  />
                </button>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <Button
                type="submit"
                size="lg"
                rightIcon={
                  <Icon
                    name="arrow-right"
                    size={18}
                  />
                }
              >
                继续
              </Button>
            </div>
          </form>
        </Card>
      </div>
    );
  }

  return (
    <TraceProvider>
      <StreamSession
        apiKey={apiKey}
        apiUrl={browserApiUrl}
        assistantId={finalAssistantId}
        authScheme={finalAuthScheme || undefined}
      >
        {children}
      </StreamSession>
    </TraceProvider>
  );
};

export default StreamContext;
