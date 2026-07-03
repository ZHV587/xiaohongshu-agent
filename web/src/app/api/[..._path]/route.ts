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

function corsHeaders(): Record<string, string> {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Expose-Headers": "content-location",
  };
}

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

    const responseHeaders = new Headers(corsHeaders());
    upstream.headers.forEach((value, key) => responseHeaders.set(key, value));
    Object.entries(corsHeaders()).forEach(([key, value]) => responseHeaders.set(key, value));

    return new NextResponse(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "LangGraph proxy failed" },
      { status: 500, headers: corsHeaders() },
    );
  }
}

export const GET = (req: NextRequest) => proxy(req, "GET");
export const POST = (req: NextRequest) => proxy(req, "POST");
export const PUT = (req: NextRequest) => proxy(req, "PUT");
export const PATCH = (req: NextRequest) => proxy(req, "PATCH");
export const DELETE = (req: NextRequest) => proxy(req, "DELETE");

export function OPTIONS(): NextResponse {
  return new NextResponse(null, { status: 204, headers: corsHeaders() });
}
