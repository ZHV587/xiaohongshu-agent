// 退出登录:清除身份 cookie 并回首页。
import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/lib/server/feishu";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const res = NextResponse.redirect(new URL("/", req.nextUrl.origin));
  // 属性需与签发时一致(httpOnly + path),确保浏览器正确覆盖删除。
  res.cookies.set(AUTH_COOKIE, "", {
    httpOnly: true,
    sameSite: "strict",
    secure: req.nextUrl.protocol === "https:",
    maxAge: 0,
    path: "/",
  });
  return res;
}
