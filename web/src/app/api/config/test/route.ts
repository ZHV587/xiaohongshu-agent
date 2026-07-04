import { NextRequest, NextResponse } from "next/server";
import { apiErrorResponse, requireAdmin } from "@/lib/server/authz";
import { lookup } from "node:dns/promises";
import { isIP } from "node:net";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// SSRF 防护:管理员可填任意 baseUrl 测网关连通性,但绝不能让 web 服务器据此对内网/环回/
// 链路本地(如 169.254.169.254 元数据、127.0.0.1、10/172.16-31/192.168、fc00::/7)发认证请求
// 并回显响应。先校验协议,再按字面量 IP 或 DNS 解析结果判定是否落在禁止段。
function isPrivateIp(ip: string): boolean {
  const v4 = ip.match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
  if (v4) {
    const a = Number(v4[1]);
    const b = Number(v4[2]);
    if (a === 0 || a === 10 || a === 127) return true;            // 0.0.0.0 / 内网 / 环回
    if (a === 169 && b === 254) return true;                       // 链路本地(含云元数据)
    if (a === 172 && b >= 16 && b <= 31) return true;             // 内网
    if (a === 192 && b === 168) return true;                       // 内网
    if (a >= 224) return true;                                     // 多播/保留
  }
  const low = ip.toLowerCase();
  if (low === "::1" || low === "::") return true;                  // 环回 / 未指定
  if (low.startsWith("fc") || low.startsWith("fd")) return true;   // IPv6 唯一本地
  if (low.startsWith("fe80")) return true;                         // IPv6 链路本地
  return false;
}

async function safeOrigin(raw: string): Promise<string> {
  let u: URL;
  try {
    u = new URL(raw);
  } catch {
    throw new Error("baseUrl 不是合法 URL");
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") {
    throw new Error("仅支持 http/https");
  }
  const host = u.hostname;
  const direct = isIP(host);
  if (direct !== 0) {
    if (isPrivateIp(host)) throw new Error("目标地址位于内网/环回/保留段,禁止探测");
  } else {
    let address: string;
    try {
      ({ address } = await lookup(host));
    } catch {
      throw new Error("目标域名无法解析");
    }
    if (isPrivateIp(address)) throw new Error("目标域名解析到内网/环回/保留段,禁止探测");
  }
  return u.origin.replace(/\/$/, "");
}

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

    let origin: string;
    try {
      origin = await safeOrigin(baseUrl);
    } catch (e: any) {
      return NextResponse.json({ ok: false, error: e?.message || "baseUrl 不安全" }, { status: 400 });
    }

    let testModel = model?.trim() || "gpt-4o";
    const testUrl = `${origin}/chat/completions`;
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
      const modelsUrl = `${origin}/models`;
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
