// 飞书登录入口:生成带 CSRF state 的授权 URL 并 302 跳转到飞书授权页。
import { NextRequest, NextResponse } from "next/server";
import crypto from "node:crypto";
import {
  FEISHU_AUTHORIZE_URL,
  STATE_COOKIE,
  getActualOrigin,
  getFeishuConfig,
  getFeishuOAuthCredentials,
  isSecureRequest,
  safeNextPath,
} from "@/lib/server/feishu";
import { FEISHU_OAUTH_SCOPES } from "@/lib/feishu-scopes";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  try {
    getFeishuConfig(); // 预校验 XHS_JWT_SECRET(回调签 JWT 依赖),缺失则不进入 OAuth
  } catch (e) {
    return NextResponse.json(
      { error: (e as Error).message },
      { status: 500 },
    );
  }

  // app_id 取权威值(config-center 经内部接口;回退 env),与后端强一致。
  const { appId } = await getFeishuOAuthCredentials();
  if (!appId) {
    return NextResponse.json({ error: "飞书 OAuth 配置缺失:FEISHU_APP_ID" }, { status: 500 });
  }

  // CSRF 防护:随机 state 写入 httpOnly cookie,回调时比对。
  const state = crypto.randomBytes(16).toString("hex");
  // 登录成功后回跳的前端页面(默认根路径),从 ?next= 取并做同源约束。
  const next = req.nextUrl.searchParams.get("next") || "/";

  const origin = getActualOrigin(req);

  const authorizeUrl = new URL(FEISHU_AUTHORIZE_URL);
  authorizeUrl.searchParams.set("client_id", appId);
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

