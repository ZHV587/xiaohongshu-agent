import { apiErrorResponse, jsonNoStore, requireAdmin } from "@/lib/server/authz";
import { isConfigCenterEnabled } from "@/lib/server/config-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await requireAdmin();
    const applyMode = (process.env.XHS_BACKEND_APPLY_MODE || "manual")
      .trim()
      .toLowerCase();

    return jsonNoStore({
      ok: true,
      config_version: process.env.XHS_CONFIG_VERSION || "",
      apply_mode: applyMode,
      config_center_enabled: isConfigCenterEnabled(),
      hot_apply_supported: false,
      hot_reload_supported_paths: {
        main_agent: true,
        server_async: true,
        subagents: true,
        rubric: false,
      },
      hot_reload_message:
        "Only ModelRouterMiddleware paths are hot-reload eligible. Rubric remains restart-required in phase 2.",
      status_message:
        applyMode === "manual"
          ? "配置已保存到环境文件；Python 后端需要手动重启后才会加载新版本。"
          : "配置保存后会通过固定 apply mode 触发后端重启。",
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
