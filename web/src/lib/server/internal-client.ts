type InternalRoute = {
  path: string;
  method: "GET" | "POST";
};

const internalPathMap: Record<string, InternalRoute> = {
  "/_internal/chats": { path: "/internal/feishu/chats", method: "GET" },
  "/_internal/uat": { path: "/internal/feishu/uat", method: "POST" },
  "/_internal/uat-status": { path: "/internal/feishu/status", method: "GET" },
  "/_internal/wiki-space": { path: "/internal/feishu/wiki-space", method: "GET" },
  "/_internal/config-status": { path: "/internal/config", method: "GET" },
  "/_internal/config-set": { path: "/internal/config", method: "POST" },
};

function jsonResponse(payload: Record<string, unknown>, status: number): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-store",
    },
  });
}

function allowsConfigFallback(pathName: string, extraHeaders?: any): boolean {
  return (
    extraHeaders?.allowConfigFallback === true &&
    (pathName === "/_internal/config-status" || pathName === "/_internal/config-set")
  );
}

function degradedConfigResponse(): Response {
  return jsonResponse(
    {
      ok: false,
      degraded: true,
      error: "Internal HTTP unavailable; config fallback is required",
    },
    503
  );
}

export async function forwardToInternalServer(
  pathName: string,
  method: "GET" | "POST",
  openId: string,
  extraBody?: any,
  extraHeaders?: any
): Promise<Response> {
  const route = internalPathMap[pathName];
  if (!route) {
    return jsonResponse({ error: `Unknown internal path: ${pathName}` }, 404);
  }
  if (method !== route.method) {
    return jsonResponse({ error: `Method not allowed for internal path: ${pathName}` }, 405);
  }

  const baseUrl = process.env.XHS_INTERNAL_BASE_URL;
  const secret = process.env.XHS_INTERNAL_SECRET;
  if (!baseUrl && allowsConfigFallback(pathName, extraHeaders)) {
    return degradedConfigResponse();
  }
  if (!baseUrl || !secret) {
    return jsonResponse({ error: "Internal HTTP is not configured" }, 503);
  }

  const headers: Record<string, string> = {
    "X-XHS-Internal-Key": secret,
    "X-XHS-Open-Id": openId,
    "X-XHS-Is-Admin": String(Boolean(extraHeaders?.isAdmin)),
  };
  if (route.method === "POST") headers["Content-Type"] = "application/json";

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    return await fetch(new URL(route.path, baseUrl).toString(), {
      method: route.method,
      headers,
      body: route.method === "POST" ? JSON.stringify(extraBody || {}) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    if (allowsConfigFallback(pathName, extraHeaders)) {
      return degradedConfigResponse();
    }
    return jsonResponse({ error: (error as Error).message || "Internal HTTP request failed" }, 503);
  } finally {
    clearTimeout(timeout);
  }
}
