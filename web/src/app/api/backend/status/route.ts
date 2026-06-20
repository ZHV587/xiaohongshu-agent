import { apiErrorResponse, jsonNoStore, requireAdmin } from "@/lib/server/authz";
import { buildBackendStatusPayload, isConfigCenterEnabled } from "@/lib/server/config-store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    await requireAdmin();
    const applyMode = (process.env.XHS_BACKEND_APPLY_MODE || "manual")
      .trim()
      .toLowerCase();

    return jsonNoStore(
      buildBackendStatusPayload({
        applyMode,
        configCenterEnabled: isConfigCenterEnabled(),
        configVersion: process.env.XHS_CONFIG_VERSION || "",
      }),
    );
  } catch (error) {
    return apiErrorResponse(error);
  }
}
