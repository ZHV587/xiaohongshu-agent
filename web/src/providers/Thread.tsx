import { validate } from "uuid";
import { getApiKey } from "@/lib/api-key";
import type { Thread } from "@langchain/langgraph-sdk";
import { useQueryState } from "nuqs";
import { ReactNode, useCallback, useState } from "react";
import { createClient, toBrowserApiUrl } from "./client";
import { ThreadContext } from "./thread-context";

function getThreadSearchMetadata(
  assistantId: string,
): { graph_id: string } | { assistant_id: string } {
  if (validate(assistantId)) {
    return { assistant_id: assistantId };
  } else {
    return { graph_id: assistantId };
  }
}

export function ThreadProvider({ children }: { children: ReactNode }) {
  const envApiUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL;
  const envAssistantId: string | undefined =
    process.env.NEXT_PUBLIC_ASSISTANT_ID;
  const envAuthScheme: string | undefined = process.env.NEXT_PUBLIC_AUTH_SCHEME;

  const [apiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  // 安全:生产忽略 ?apiUrl= 覆盖,固定走同源 /api 代理(对齐 StreamProvider)。
  const finalApiUrl =
    process.env.NODE_ENV === "development" ? apiUrl || envApiUrl : envApiUrl;
  const [assistantId] = useQueryState("assistantId");
  const [authScheme] = useQueryState("authScheme", {
    defaultValue: envAuthScheme || "",
  });
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);

  const makeClient = useCallback(() => {
    const resolvedAssistantId = assistantId || envAssistantId;
    if (!finalApiUrl || !resolvedAssistantId) return null;
    const browserApiUrl = toBrowserApiUrl(finalApiUrl);
    if (!browserApiUrl) return null;
    return createClient(
      browserApiUrl,
      getApiKey() ?? undefined,
      authScheme || undefined,
    );
  }, [finalApiUrl, assistantId, authScheme, envAssistantId]);

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    const resolvedAssistantId = assistantId || envAssistantId;
    const client = makeClient();
    if (!client || !resolvedAssistantId) return [];

    const threads = await client.threads.search({
      metadata: {
        ...getThreadSearchMetadata(resolvedAssistantId),
      },
      limit: 100,
    });

    return threads;
  }, [makeClient, assistantId, envAssistantId]);

  const deleteThread = useCallback(
    async (threadId: string): Promise<void> => {
      const client = makeClient();
      if (!client) throw new Error("无法连接服务,删除失败");
      // 成功后才从本地列表移除(非乐观):delete 抛错则不动 state,由调用方 toast。
      await client.threads.delete(threadId);
      setThreads((prev) => prev.filter((t) => t.thread_id !== threadId));
    },
    [makeClient],
  );

  const value = {
    getThreads,
    deleteThread,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
  };

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}
