import { NextRequest, NextResponse } from "next/server";
import { apiErrorResponse, requireAdmin } from "@/lib/server/authz";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    await requireAdmin();
  } catch (error) {
    return apiErrorResponse(error);
  }

  try {
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
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            model: targetModel,
            messages: [{ role: "user", content: "ping" }],
            max_tokens: 3,
          }),
          signal: controller.signal,
        });
        clearTimeout(timeoutId);
        return resp;
      } catch (err) {
        clearTimeout(timeoutId);
        throw err;
      }
    };

    // 拉取 /models 列表。返回 {models, error}:models 为空时用 error 说明原因(HTTP 码/超时/
    // 格式异常),供前端在「连通成功但拉不到模型」时给出可诊断的提示,而非静默空下拉。
    const fetchModelsList = async (): Promise<{ models: string[]; error?: string }> => {
      const modelsUrl = `${baseUrl.replace(/\/$/, "")}/models`;
      const modelsController = new AbortController();
      const modelsTimeoutId = setTimeout(() => modelsController.abort(), 5000); // 5s timeout
      try {
        const modelsResp = await fetch(modelsUrl, {
          method: "GET",
          headers: {
            Authorization: `Bearer ${apiKey}`,
          },
          signal: modelsController.signal,
        });
        clearTimeout(modelsTimeoutId);

        if (modelsResp.status !== 200) {
          return { models: [], error: `拉取模型列表失败：HTTP ${modelsResp.status}` };
        }
        const modelsData = await modelsResp.json();
        if (!modelsData || !Array.isArray(modelsData.data)) {
          return { models: [], error: "拉取模型列表失败：响应缺少 data 数组" };
        }
        const models = modelsData.data
          .map((item: any) => item?.id)
          .filter(
            (id: any): id is string => typeof id === "string" && id.trim() !== "",
          );
        return { models };
      } catch (err: any) {
        clearTimeout(modelsTimeoutId);
        const reason = err?.name === "AbortError" ? "超时(5s)" : err?.message || String(err);
        console.error("Failed to fetch models list in helper:", err);
        return { models: [], error: `拉取模型列表失败：${reason}` };
      }
    };

    let resp: Response;
    try {
      resp = await performChatTest(testModel);
    } catch (e: any) {
      // If the first request throws network error/timeout, try auto-discovery
      const { models: discovered } = await fetchModelsList();
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
      const { models: discovered } = await fetchModelsList();
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
      // 连通成功后拉模型列表:即便拉取失败(modelsError)也返回 ok:true(连通本身没问题),
      // 但带上 modelsError 让前端明确提示「连通成功、模型列表拉取失败:原因」,不再静默空下拉。
      const { models, error: modelsError } = await fetchModelsList();
      return NextResponse.json({ ok: true, latency, models, modelsError });
    }

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
      error: `HTTP ${resp.status}: ${errorDetail.substring(0, 100)}`,
    });
  } catch (e: any) {
    let errorMsg = e.message || String(e);
    if (e.name === "AbortError") {
      errorMsg = "Request timeout (6s)";
    }
    return NextResponse.json({ ok: false, error: errorMsg });
  }
}
