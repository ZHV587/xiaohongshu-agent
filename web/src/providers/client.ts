import { Client } from "@langchain/langgraph-sdk";

export function toBrowserApiUrl(
  apiUrl: string | undefined,
): string | undefined {
  if (!apiUrl) return apiUrl;
  if (apiUrl.startsWith("/") && typeof window !== "undefined") {
    return `${window.location.origin}${apiUrl}`;
  }
  return apiUrl;
}

// BFF 模式:apiUrl 指向同源 /api 代理。浏览器自动携带 httpOnly cookie,
// 由代理在服务端注入 Authorization Bearer。前端不再持有或注入 token。
export function createClient(
  apiUrl: string,
  apiKey: string | undefined,
  authScheme: string | undefined,
) {
  return new Client({
    apiKey,
    apiUrl,
    defaultHeaders: {
      ...(authScheme && { "X-Auth-Scheme": authScheme }),
    },
  });
}
