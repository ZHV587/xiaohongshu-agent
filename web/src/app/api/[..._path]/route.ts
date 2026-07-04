import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { AUTH_COOKIE } from "@/lib/constants";

// BFF 同源代理:浏览器只访问同源 /api/*,身份 JWT 存在 httpOnly cookie 里,
// 浏览器 JS 读不到。这里在服务端从 cookie 取出 JWT,作为 Bearer 注入到发往
// LangGraph 后端的请求头中,由后端 auth.py 验签。这样 token 永不暴露给前端 JS,
// 消除 XSS 窃取身份令牌的攻击面。
//
// apiUrl 改读服务端专用的 LANGGRAPH_API_URL(不带 NEXT_PUBLIC_ 前缀,不进浏览器包)。
export const runtime = "nodejs";

const BODY_METHODS = new Set(["POST", "PUT", "PATCH"]);

// 上游透传时需剥除的响应头:hop-by-hop 头(由 fetch/Node 自行管理,透传会破坏连接语义),
// 以及绝不能回传给浏览器的 set-cookie(上游会话 cookie 不应泄漏到前端)。
const STRIPPED_RESPONSE_HEADERS = new Set([
  "set-cookie",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "content-length",
]);

// 本代理是**同源** BFF(浏览器只访问同源 /api/*,见 providers/client.ts):同源请求不需要任何
// CORS 头。此前用 Access-Control-Allow-Origin:* + Allow-Headers:* 是纯多余的攻击面——它让任意
// 站点得以对本代理发起跨源请求并读取响应(注入用户 cookie 的鉴权代理绝不应对外开放)。
// 故不再发任何 ACAO 头;OPTIONS 预检直接 204(无 ACAO,浏览器自然拒绝跨源)。

function upstreamUrl(req: NextRequest): string {
  const apiUrl = process.env.LANGGRAPH_API_URL ?? "http://localhost:2024";
  const path = req.nextUrl.pathname.replace(/^\/?api\//, "");
  const searchParams = new URLSearchParams(req.nextUrl.search);
  searchParams.delete("_path");
  searchParams.delete("nxtP_path");
  const query = searchParams.toString();
  return `${apiUrl.replace(/\/$/, "")}/${path}${query ? `?${query}` : ""}`;
}

async function proxy(req: NextRequest, method: string): Promise<NextResponse> {
  try {
    const headers = new Headers();
    req.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (lower.startsWith("x-") || lower === "authorization") headers.set(key, value);
    });

    const apiKey = process.env.LANGSMITH_API_KEY ?? "";
    if (apiKey) headers.set("x-api-key", apiKey);

    const token = req.cookies.get(AUTH_COOKIE)?.value;
    if (token) headers.set("authorization", `Bearer ${token}`);

    const upstream = await fetch(upstreamUrl(req), {
      method,
      headers,
      body: BODY_METHODS.has(method) ? await req.text() : undefined,
    });

    const responseHeaders = new Headers();
    upstream.headers.forEach((value, key) => {
      if (!STRIPPED_RESPONSE_HEADERS.has(key.toLowerCase())) responseHeaders.set(key, value);
    });

    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "LangGraph proxy failed" },
      { status: 500 },
    );
  }
}

export const GET = (req: NextRequest) => proxy(req, "GET");
export const POST = (req: NextRequest) => proxy(req, "POST");
export const PUT = (req: NextRequest) => proxy(req, "PUT");
export const PATCH = (req: NextRequest) => proxy(req, "PATCH");
export const DELETE = (req: NextRequest) => proxy(req, "DELETE");

export function OPTIONS(): NextResponse {
  // 同源无需 CORS;不发 ACAO,预检对跨源请求自然失败。
  return new NextResponse(null, { status: 204 });
}
