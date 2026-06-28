// 退出登录:清除身份 cookie 并回首页。
import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE, getActualOrigin, isSecureRequest } from "@/lib/server/feishu";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const res = NextResponse.redirect(new URL("/", getActualOrigin(req)));
  // 属性需与签发时一致(httpOnly + sameSite + path + Secure 判定),确保浏览器正确覆盖删除。
  // Secure 用 isSecureRequest(x-forwarded-proto)而非 req.nextUrl.protocol,与 login/callback 一致。
  res.cookies.set(AUTH_COOKIE, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: isSecureRequest(req),
    maxAge: 0,
    path: "/",
  });
  return res;
}
