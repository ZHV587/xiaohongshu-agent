import { apiErrorResponse, jsonNoStore, requireAdmin } from "@/lib/server/authz";
import { buildBackendStatusPayload, isConfigCenterEnabled } from "@/lib/server/config-store";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const user = await requireAdmin();
    const applyMode = (process.env.XHS_BACKEND_APPLY_MODE || "manual")
      .trim()
      .toLowerCase();

    // 本地基线:apply_mode / config_version / status_message 等 web-apply 侧事实在前端权威。
    const base = buildBackendStatusPayload({
      applyMode,
      configCenterEnabled: isConfigCenterEnabled(),
      configVersion: process.env.XHS_CONFIG_VERSION || "",
    });

    // 热切事实的单一权威源在后端(部署感知)。透传后端 /internal/model/status;
    // 后端可达则用其 hot_reload 覆盖本地推导(前端值派生自后端,杜绝两套布尔漂移),
    // 不可达(未配 internal HTTP / env 模式)再回退本地公式——两者公式一致,降级安全。
    try {
      const resp = await forwardToInternalServer(
        "/_internal/model-status",
        "GET",
        user.openId,
        undefined,
        { isAdmin: true },
      );
      const data = await resp.json().catch(() => null);
      if (resp.ok && data?.ok && data.hot_reload) {
        return jsonNoStore({
          ...base,
          hot_reload_supported_paths: data.hot_reload,
          hot_reload_source: "backend",
          model_registry: data.registry ?? null,
        });
      }
    } catch {
      // 后端不可达:落到本地基线(hot_reload_source=local-fallback)。
    }

    return jsonNoStore({ ...base, hot_reload_source: "local-fallback" });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
