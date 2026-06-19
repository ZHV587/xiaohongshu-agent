import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { AUTH_COOKIE, getFeishuConfig } from "@/lib/server/feishu";
import { verifyJwt } from "@/lib/server/jwt";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

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
    const { apiKey, baseUrl, model } = body;
    
    if (!apiKey || !baseUrl || !model) {
      return NextResponse.json({ error: "Missing parameters" }, { status: 400 });
    }

    const testUrl = `${baseUrl.replace(/\/$/, "")}/chat/completions`;
    const startTime = Date.now();

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 6000); // 6s timeout

    const resp = await fetch(testUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${apiKey}`
      },
      body: JSON.stringify({
        model: model,
        messages: [{ role: "user", content: "ping" }],
        max_tokens: 3
      }),
      signal: controller.signal
    });

    clearTimeout(timeoutId);
    const latency = Date.now() - startTime;

    if (resp.status === 200) {
      let models: string[] = [];
      try {
        const modelsUrl = `${baseUrl.replace(/\/$/, "")}/models`;
        const modelsController = new AbortController();
        const modelsTimeoutId = setTimeout(() => modelsController.abort(), 5000); // 5s timeout

        const modelsResp = await fetch(modelsUrl, {
          method: "GET",
          headers: {
            "Authorization": `Bearer ${apiKey}`
          },
          signal: modelsController.signal
        });
        clearTimeout(modelsTimeoutId);

        if (modelsResp.status === 200) {
          const modelsData = await modelsResp.json();
          if (modelsData && Array.isArray(modelsData.data)) {
            models = modelsData.data
              .map((item: any) => item?.id)
              .filter((id: any): id is string => typeof id === "string" && id.trim() !== "");
          }
        }
      } catch (e) {
        console.error("Failed to fetch models list:", e);
      }
      return NextResponse.json({ ok: true, latency, models });
    } else {
      const errText = await resp.text();
      let errorDetail = "";
      try {
        const parsed = JSON.parse(errText);
        errorDetail = parsed.error?.message || parsed.msg || errText;
      } catch {
        errorDetail = errText;
      }
      return NextResponse.json({
        ok: false,
        status: resp.status,
        error: `HTTP ${resp.status}: ${errorDetail.substring(0, 100)}`
      });
    }
  } catch (e: any) {
    let errorMsg = e.message || String(e);
    if (e.name === "AbortError") {
      errorMsg = "Request timeout (6s)";
    }
    return NextResponse.json({ ok: false, error: errorMsg });
  }
}
