// 飞书授权回调:校验 state → 用 code 换 user_access_token → 取用户信息 →
// 签发 JWT 写入可读 cookie → 回跳前端页面。client_secret 只在此服务端使用。
import { NextRequest, NextResponse } from "next/server";
import {
  AUTH_COOKIE,
  FEISHU_TOKEN_URL,
  FEISHU_USER_INFO_URL,
  STATE_COOKIE,
  getFeishuConfig,
} from "@/lib/server/feishu";
import { signJwt } from "@/lib/server/jwt";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function getActualOrigin(req: NextRequest): string {
  if (process.env.XHS_PUBLIC_ORIGIN) return process.env.XHS_PUBLIC_ORIGIN.replace(/\/$/, "");
  const host = req.headers.get("x-forwarded-host") || req.headers.get("host") || "localhost:3000";
  const protocol = req.headers.get("x-forwarded-proto") || "http";
  const actualHost = host.split(",")[0].trim();
  return `${protocol}://${actualHost}`;
}

function fail(req: NextRequest, msg: string) {
  // 失败时回首页并带上错误,前端可 toast 提示。
  const origin = getActualOrigin(req);
  const url = new URL("/", origin);
  url.searchParams.set("auth_error", msg);
  return NextResponse.redirect(url);
}

export async function GET(req: NextRequest) {
  let cfg;
  try {
    cfg = getFeishuConfig();
  } catch (e) {
    return fail(req, (e as Error).message);
  }

  const code = req.nextUrl.searchParams.get("code");
  const state = req.nextUrl.searchParams.get("state");
  const stateCookie = req.cookies.get(STATE_COOKIE)?.value;

  if (!code) return fail(req, "缺少授权码");
  if (!state || !stateCookie) return fail(req, "登录状态失效，请重试");

  const [savedState, savedNext] = stateCookie.split("|");
  if (state !== savedState) return fail(req, "state 校验失败，请重试");
  const next = savedNext && savedNext.startsWith("/") ? savedNext : "/";

  // 1) 授权码换 user_access_token(v2 接口,JSON 体)
  let userToken: string;
  let refreshToken: string | undefined;
  let expiresIn: number;
  let tokenData: any;
  try {
    const tokenResp = await fetch(FEISHU_TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({
        grant_type: "authorization_code",
        client_id: cfg.appId,
        client_secret: cfg.appSecret,
        code,
        redirect_uri: `${getActualOrigin(req)}/api/auth/feishu/callback`,
      }),
    });
    tokenData = await tokenResp.json();
    // v2 返回 access_token;部分老接口包在 data 下,做个兼容。
    userToken = tokenData.access_token ?? tokenData?.data?.access_token;
    refreshToken = tokenData.refresh_token ?? tokenData?.data?.refresh_token; // v2 可能不返回
    expiresIn = tokenData.expires_in ?? tokenData?.data?.expires_in ?? 7200;
    if (!userToken) {
      console.error("[Feishu Callback] token exchange failed:", JSON.stringify(tokenData));
      return fail(
        req,
        `换取 token 失败：${tokenData.error_description ?? tokenData.msg ?? tokenData.message ?? JSON.stringify(tokenData)}`,
      );
    }
  } catch {
    return fail(req, "换取 token 请求异常");
  }

  // 2) 用 user_access_token 取用户信息(open_id 作稳定身份)
  let openId: string;
  let name: string | undefined;
  try {
    const infoResp = await fetch(FEISHU_USER_INFO_URL, {
      headers: { Authorization: `Bearer ${userToken}` },
    });
    const infoData = await infoResp.json();
    const data = infoData.data ?? infoData;
    openId = data.open_id ?? data.union_id;
    name = data.name;
    if (!openId) {
      return fail(
        req,
        `获取用户信息失败：${infoData.msg ?? "无 open_id"}`,
      );
    }
  } catch {
    return fail(req, "获取用户信息请求异常");
  }

  // ── Sync to Python UAT storage using HMAC signature ──────────
  try {
    const expiresAt = Math.floor(Date.now() / 1000 + expiresIn);
    const rtStr = refreshToken || "";
    const bodyObj = {
      uat: userToken,
      refresh_token: rtStr,
      expires_at: expiresAt,
      scopes: tokenData.scope ? tokenData.scope.split(" ") : [],
      name: name || openId
    };
    
    const syncResp = await forwardToInternalServer("/_internal/uat", "POST", openId, bodyObj, {
      isAdmin: false,
    });
    
    if (!syncResp.ok) {
      const errMsg = await syncResp.text();
      console.error(`UAT sync to python internal server failed: ${errMsg}`);
    }
  } catch (e) {
    console.error("Exception during UAT sync post to Python:", e);
  }

  // 3) 签发本系统 JWT(后端 auth.py 用同一密钥验签,取 sub 作身份)
  const jwt = signJwt({ sub: openId, name }, cfg.jwtSecret);

  const res = NextResponse.redirect(new URL(next, getActualOrigin(req)));
  // 可读 cookie(非 httpOnly):前端 JS 要读出来塞进 Authorization 头发给后端。
  res.cookies.set(AUTH_COOKIE, jwt, {
    httpOnly: false,
    sameSite: "lax",
    secure: req.nextUrl.protocol === "https:",
    maxAge: 7 * 24 * 3600,
    path: "/",
  });
  // 清掉一次性 state cookie
  res.cookies.set(STATE_COOKIE, "", { maxAge: 0, path: "/" });
  return res;
}
