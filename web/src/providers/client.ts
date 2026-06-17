import { Client } from "@langchain/langgraph-sdk";
import { getAuthToken } from "@/lib/auth";

export function createClient(
  apiUrl: string,
  apiKey: string | undefined,
  authScheme: string | undefined,
) {
  const token = getAuthToken();
  return new Client({
    apiKey,
    apiUrl,
    defaultHeaders: {
      ...(authScheme && { "X-Auth-Scheme": authScheme }),
      // 真飞书 OAuth:把身份 JWT 作为 Bearer 传给后端 auth.py 验签。
      ...(token && { Authorization: `Bearer ${token}` }),
    },
  });
}
