import { NextRequest, NextResponse } from "next/server";
import { apiErrorResponse, jsonNoStore, requireAdmin } from "@/lib/server/authz";
import { applyBackendConfig } from "@/lib/server/backend-apply";
import {
  assertAllowedConfigKeys,
  envPaths,
  generateConfigVersion,
  isConfigCenterEnabled,
  readConfigResponse,
  updateEnvFile,
} from "@/lib/server/config-store";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await requireAdmin();
    if (isConfigCenterEnabled()) {
      const resp = await forwardToInternalServer("/_internal/config-status", "GET", "system");
      const data = await resp.json();
      if (!resp.ok || data.ok === false) {
        return NextResponse.json(
          { error: data.error || "Failed to read config center" },
          { status: resp.status || 500 },
        );
      }
      return jsonNoStore({ ok: true, configs: data.configs, source: "config-center" });
    }
    return jsonNoStore({ ok: true, configs: readConfigResponse() });
  } catch (error) {
    return apiErrorResponse(error);
  }
}

export async function POST(req: NextRequest) {
  try {
    const user = await requireAdmin();
    const body = await req.json();
    if (!body.configs || typeof body.configs !== "object") {
      return NextResponse.json({ error: "Bad Request: Missing configs object" }, { status: 400 });
    }
    const configs = assertAllowedConfigKeys(body.configs);

    if (isConfigCenterEnabled()) {
      const resp = await forwardToInternalServer("/_internal/config-set", "POST", user.openId, { configs });
      const data = await resp.json();
      if (!resp.ok || data.ok === false) {
        return NextResponse.json(
          { error: data.error || "Failed to save config center" },
          { status: resp.status || 500 },
        );
      }
      return NextResponse.json({
        ok: true,
        version: data.version,
        apply: {
          mode: "config-center",
          applied: false,
          message: "配置已保存到配置中心；registry 覆盖路径将在进程内 reload 通道触发后热切。",
        },
      });
    }

    const version = generateConfigVersion(configs);
    const updates = { ...configs, XHS_CONFIG_VERSION: version };

    for (const [key, value] of Object.entries(updates)) {
      process.env[key] = value;
    }

    const { webEnvPath, rootEnvPath } = envPaths();
    updateEnvFile(webEnvPath, updates);
    updateEnvFile(rootEnvPath, updates);

    let apply;
    try {
      apply = await applyBackendConfig();
    } catch (error) {
      apply = {
        mode: process.env.XHS_BACKEND_APPLY_MODE || "manual",
        applied: false,
        message: (error as Error).message,
      };
    }

    console.info("[config] saved", {
      actor: user.openId,
      version,
      keys: Object.keys(configs),
      apply,
    });

    return NextResponse.json({ ok: true, version, apply });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
