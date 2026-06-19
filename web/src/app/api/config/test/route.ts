import { NextRequest, NextResponse } from "next/server";
import { apiErrorResponse, requireAdmin } from "@/lib/server/authz";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    await requireAdmin();
    const body = await req.json();
    const { apiKey, baseUrl, model } = body;
    
    if (!apiKey || !baseUrl) {
      return NextResponse.json({ error: "Missing parameters" }, { status: 400 });
    }

    let testModel = model?.trim() || "gpt-4o";
    const testUrl = `${baseUrl.replace(/\/$/, "")}/chat/completions`;
    const startTime = Date.now();

    // Helper function to test chat connectivity for a specific model
    const performChatTest = async (targetModel: string) => {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 6000); // 6s timeout
      try {
        const resp = await fetch(testUrl, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${apiKey}`
          },
          body: JSON.stringify({
            model: targetModel,
            messages: [{ role: "user", content: "ping" }],
            max_tokens: 3
          }),
          signal: controller.signal
        });
        clearTimeout(timeoutId);
        return resp;
      } catch (err) {
        clearTimeout(timeoutId);
        throw err;
      }
    };

    // Helper function to fetch models list from /models
    const fetchModelsList = async (): Promise<string[]> => {
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
            return modelsData.data
              .map((item: any) => item?.id)
              .filter((id: any): id is string => typeof id === "string" && id.trim() !== "");
          }
        }
      } catch (err) {
        console.error("Failed to fetch models list in helper:", err);
      }
      return [];
    };

    let resp: Response;
    try {
      resp = await performChatTest(testModel);
    } catch (e: any) {
      // If the first request throws network error/timeout, try auto-discovery
      const discovered = await fetchModelsList();
      if (discovered.length > 0) {
        try {
          resp = await performChatTest(discovered[0]);
          testModel = discovered[0];
        } catch {
          throw e; // Throw original error if retry also fails
        }
      } else {
        throw e;
      }
    }

    let latency = Date.now() - startTime;

    // If initial chat completions returns non-200 (e.g. 503 model not available), auto-discover and retry
    if (resp.status !== 200) {
      const discovered = await fetchModelsList();
      if (discovered.length > 0) {
        try {
          const retryResp = await performChatTest(discovered[0]);
          if (retryResp.status === 200) {
            resp = retryResp;
            testModel = discovered[0];
            latency = Date.now() - startTime;
          }
        } catch (err) {
          console.error("Auto discovery retry failed:", err);
        }
      }
    }

    if (resp.status === 200) {
      const models = await fetchModelsList();
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
    if (e.status) return apiErrorResponse(e);
    return NextResponse.json({ ok: false, error: errorMsg });
  }
}
