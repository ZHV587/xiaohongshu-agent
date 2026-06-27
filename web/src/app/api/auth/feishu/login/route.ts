// 飞书登录入口:生成带 CSRF state 的授权 URL 并 302 跳转到飞书授权页。
import { NextRequest, NextResponse } from "next/server";
import crypto from "node:crypto";
import {
  FEISHU_AUTHORIZE_URL,
  STATE_COOKIE,
  getFeishuConfig,
} from "@/lib/server/feishu";
import { FEISHU_OAUTH_SCOPES } from "@/lib/feishu-scopes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  let cfg;
  try {
    cfg = getFeishuConfig();
  } catch (e) {
    return NextResponse.json(
      { error: (e as Error).message },
      { status: 500 },
    );
  }

  // CSRF 防护:随机 state 写入 httpOnly cookie,回调时比对。
  const state = crypto.randomBytes(16).toString("hex");
  // 登录成功后回跳的前端页面(默认根路径),从 ?next= 取并做同源约束。
  const next = req.nextUrl.searchParams.get("next") || "/";

  const origin = getActualOrigin(req);

  const authorizeUrl = new URL(FEISHU_AUTHORIZE_URL);
  authorizeUrl.searchParams.set("client_id", cfg.appId);
  authorizeUrl.searchParams.set("redirect_uri", `${origin}/api/auth/feishu/callback`);
  authorizeUrl.searchParams.set("response_type", "code");
  authorizeUrl.searchParams.set("state", state);

  const scopes = FEISHU_OAUTH_SCOPES;
  authorizeUrl.searchParams.set("scope", scopes.join(" "));

  const res = NextResponse.redirect(authorizeUrl.toString());
  res.cookies.set(STATE_COOKIE, `${state}|${safeNextPath(next)}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: isSecureRequest(req),
    maxAge: 600, // 10 分钟内完成授权
    path: "/",
  });
  return res;
}

function getActualOrigin(req: NextRequest): string {
  if (process.env.XHS_PUBLIC_ORIGIN) return process.env.XHS_PUBLIC_ORIGIN.replace(/\/$/, "");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || "localhost:3000";
  const protocol = req.headers.get("x-forwarded-proto") || "http";
  const actualHost = host.split(",")[0].trim();
  return `${protocol}://${actualHost}`;
}

// 与 callback 一致:Secure 按实际对外协议判定(TLS 上游终止时 req.nextUrl 是 http)。
function isSecureRequest(req: NextRequest): boolean {
  if (process.env.XHS_PUBLIC_ORIGIN) return process.env.XHS_PUBLIC_ORIGIN.startsWith("https:");
  return (req.headers.get("x-forwarded-proto") || req.nextUrl.protocol.replace(":", "")) === "https";
}

// 只接受站内绝对路径,挡掉开放重定向(//evil.com / /\evil.com)。
function safeNextPath(value: string | undefined): string {
  if (!value || !value.startsWith("/")) return "/";
  if (value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}
