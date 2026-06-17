// 退出登录:清除身份 cookie 并回首页。
import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/lib/server/feishu";

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const res = NextResponse.redirect(new URL("/", req.nextUrl.origin));
  res.cookies.set(AUTH_COOKIE, "", { maxAge: 0, path: "/" });
  return res;
}
