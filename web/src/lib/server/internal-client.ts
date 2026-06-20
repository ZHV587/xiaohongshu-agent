import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

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
  "/_internal/data-foundation-status": { path: "/internal/data-foundation/status", method: "GET" },
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
    extraHeaders?.isAdmin === true &&
    extraHeaders?.allowConfigFallback === true &&
    (pathName === "/_internal/config-status" || pathName === "/_internal/config-set")
  );
}

function degradedConfigResponse(error = "Internal HTTP unavailable; local config recovery is unavailable"): Response {
  return jsonResponse(
    {
      ok: false,
      degraded: true,
      error,
    },
    503
  );
}

function projectRoot(): string {
  const cwd = process.cwd();
  return existsSync(path.join(cwd, "tools", "web_bridge_runner.py")) ? cwd : path.resolve(cwd, "..");
}

function pythonExecutable(root: string): string {
  if (process.env.XHS_PYTHON_EXECUTABLE) return process.env.XHS_PYTHON_EXECUTABLE;
  const candidates = [
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, ".venv", "bin", "python"),
  ];
  return candidates.find(existsSync) || "python";
}

async function recoverConfigLocally(
  pathName: string,
  openId: string,
  extraBody?: any,
): Promise<Response> {
  const configPath = process.env.XHS_CONFIG_CENTER_PATH;
  const encryptionKey = process.env.XHS_CONFIG_ENCRYPTION_KEY;
  if (!configPath || !encryptionKey) return degradedConfigResponse();

  const root = projectRoot();
  const action = pathName === "/_internal/config-set" ? "config-set" : "config-status";
  try {
    const { stdout } = await execFileAsync(
      pythonExecutable(root),
      [path.join(root, "tools", "web_bridge_runner.py"), "--action", action, "--open-id", openId],
      {
        cwd: root,
        windowsHide: true,
        timeout: 10_000,
        maxBuffer: 1024 * 1024,
        env: {
          ...process.env,
          XHS_RECOVERY_CONFIGS_JSON: action === "config-set" ? JSON.stringify(extraBody?.configs || {}) : "",
        },
      },
    );
    const payload = JSON.parse(stdout.trim());
    if (payload.ok === false) return degradedConfigResponse(payload.error || "Local config recovery failed");
    return jsonResponse(
      {
        ...payload,
        degraded: true,
        degraded_reason: "Internal HTTP unavailable",
        recovery: "local-config-center",
      },
      200,
    );
  } catch (error) {
    return degradedConfigResponse((error as Error).message || "Local config recovery failed");
  }
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
    return recoverConfigLocally(pathName, openId, extraBody);
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
    const upstream = await fetch(new URL(route.path, baseUrl).toString(), {
      method: route.method,
      headers,
      body: route.method === "POST" ? JSON.stringify(extraBody || {}) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
    const raw = await upstream.text();
    try {
      const payload = JSON.parse(raw);
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return jsonResponse({ error: "Internal HTTP returned an invalid JSON payload" }, 502);
      }
      return jsonResponse(payload, upstream.status);
    } catch {
      if (allowsConfigFallback(pathName, extraHeaders)) {
        return recoverConfigLocally(pathName, openId, extraBody);
      }
      return jsonResponse({ error: "Internal HTTP returned a non-JSON response" }, 502);
    }
  } catch (error) {
    if (allowsConfigFallback(pathName, extraHeaders)) {
      return recoverConfigLocally(pathName, openId, extraBody);
    }
    return jsonResponse({ error: (error as Error).message || "Internal HTTP request failed" }, 503);
  } finally {
    clearTimeout(timeout);
  }
}
