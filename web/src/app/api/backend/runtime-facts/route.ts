import { apiErrorResponse, jsonNoStore, requireAdmin, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RuntimeFactsRouteDeps = {
  requireAdmin: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createRuntimeFactsGet(deps: RuntimeFactsRouteDeps) {
  return async function GET() {
    try {
      const user = await deps.requireAdmin();
      const response = await deps.forwardToInternalServer(
        "/_internal/runtime-facts",
        "GET",
        user.openId,
        undefined,
        { isAdmin: true },
      );
      const payload = await response.json();
      return jsonNoStore(payload, { status: response.status });
    } catch (error) {
      return apiErrorResponse(error);
    }
  };
}

export const GET = createRuntimeFactsGet({
  requireAdmin,
  forwardToInternalServer,
});
