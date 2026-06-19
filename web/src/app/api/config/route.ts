import { NextRequest, NextResponse } from "next/server";
import { apiErrorResponse, jsonNoStore, requireAdmin } from "@/lib/server/authz";
import { applyBackendConfig } from "@/lib/server/backend-apply";
import {
  assertAllowedConfigKeys,
  envPaths,
  generateConfigVersion,
  readConfigResponse,
  updateEnvFile,
} from "@/lib/server/config-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await requireAdmin();
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
