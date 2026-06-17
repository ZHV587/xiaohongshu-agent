import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { AUTH_COOKIE, getFeishuConfig } from "@/lib/server/feishu";
import { verifyJwt } from "@/lib/server/jwt";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }
  
  const cfg = getFeishuConfig();
  const payload = verifyJwt(token, cfg.jwtSecret);
  if (!payload) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await req.json();
    const { chatId, title, content } = body;
    if (!chatId || !title || !content) {
      return NextResponse.json({ error: "Bad Request: Missing parameters" }, { status: 400 });
    }

    const resp = await forwardToInternalServer("/_internal/notify", "POST", payload.sub, {
      chatId,
      title,
      content
    });

    if (!resp.ok) {
      const errText = await resp.text();
      return NextResponse.json({ error: errText }, { status: resp.status });
    }

    const data = await resp.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
