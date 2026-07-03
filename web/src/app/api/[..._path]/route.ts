import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";
import type { NextRequest } from "next/server";
import { AUTH_COOKIE } from "@/lib/constants";

// BFF 同源代理:浏览器只访问同源 /api/*,身份 JWT 存在 httpOnly cookie 里,
// 浏览器 JS 读不到。这里在服务端从 cookie 取出 JWT,作为 Bearer 注入到发往
// LangGraph 后端的请求头中,由后端 auth.py 验签。这样 token 永不暴露给前端 JS,
// 消除 XSS 窃取身份令牌的攻击面。
//
// apiUrl 改读服务端专用的 LANGGRAPH_API_URL(不带 NEXT_PUBLIC_ 前缀,不进浏览器包)。
export const { GET, POST, PUT, PATCH, DELETE, OPTIONS, runtime } =
  initApiPassthrough({
    apiUrl: process.env.LANGGRAPH_API_URL ?? "http://localhost:2024",
    apiKey: process.env.LANGSMITH_API_KEY ?? undefined,
    disableWarningLog: true,
    runtime: "edge", // default
    headers: (req: NextRequest): Record<string, string> => {
      const token = req.cookies.get(AUTH_COOKIE)?.value;
      return token ? { Authorization: `Bearer ${token}` } : {};
    },
  });
