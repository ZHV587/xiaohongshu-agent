import { NextResponse, type NextRequest } from "next/server";
import { refererFor, resolveImageTarget } from "./resolve";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// 图片代理:小红书 CDN 默认下发 image/heif(浏览器 <img> 无法渲染,显示灰白破图),部分域还以 http 下发
// (https 页面被混合内容拦截)。由服务端拉取、按需把 heif 改写为 jpg、注入 Referer,再把字节流回前端。
// 仅此一个用途,不做通用转发。安全:严格 host 白名单(见 resolve.ts)杜绝 SSRF;响应仅回图片 content-type。

export async function GET(request: NextRequest) {
  const resolved = resolveImageTarget(request.nextUrl.searchParams.get("u"));
  if (!resolved.ok) {
    return NextResponse.json({ error: resolved.error }, { status: resolved.status });
  }
  const { target } = resolved;

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), {
      headers: {
        Referer: refererFor(target),
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        Accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
      },
      // 上游偶发慢,给一个上限,避免挂死连接。
      signal: AbortSignal.timeout(10_000),
    });
  } catch {
    return NextResponse.json({ error: "图片拉取失败" }, { status: 502 });
  }

  if (!upstream.ok) {
    return NextResponse.json({ error: "图片源返回错误" }, { status: upstream.status });
  }

  const contentType = upstream.headers.get("content-type") ?? "";
  if (!contentType.startsWith("image/")) {
    // 只回图片,防止把代理当作任意内容转发通道。
    return NextResponse.json({ error: "目标不是图片" }, { status: 415 });
  }

  const body = await upstream.arrayBuffer();
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      // 图片内容稳定,可较长缓存;private 避免共享缓存混入用户上下文。
      "Cache-Control": "private, max-age=86400",
    },
  });
}
