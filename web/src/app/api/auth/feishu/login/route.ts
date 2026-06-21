// 飞书登录入口:生成带 CSRF state 的授权 URL 并 302 跳转到飞书授权页。
import { NextRequest, NextResponse } from "next/server";
import crypto from "node:crypto";
import {
  FEISHU_AUTHORIZE_URL,
  STATE_COOKIE,
  getFeishuConfig,
} from "@/lib/server/feishu";

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

  const scopes = [
    "im:message",
    "im:message.send_as_user",
    "im:chat",
    "im:chat.members:read",
    "base:form:update",
    "base:record:read",
    "base:record:retrieve",
    "base:table:read",
    "drive:drive",
    "drive:file:download",
    "drive:file:upload",
    "task:task:read",
    "task:task:write",
    "calendar:calendar:read",
    "calendar:calendar.event:create",
    "wiki:space:read",
    "wiki:node:read",
    "wiki:node:retrieve",
    "docx:document:readonly",
  ];
  authorizeUrl.searchParams.set("scope", scopes.join(" "));

  const res = NextResponse.redirect(authorizeUrl.toString());
  res.cookies.set(STATE_COOKIE, `${state}|${next.startsWith("/") ? next : "/"}`, {
    httpOnly: true,
    sameSite: "lax",
    secure: req.nextUrl.protocol === "https:",
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
