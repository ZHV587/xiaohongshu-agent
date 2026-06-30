import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/trends:热点趋势(真实信号源;无真实外部趋势源时后端返回真实空集合)。
// requireUser(需求 5.1/5.3/17.1)。照搬 runtime-facts 范式。
type TrendsRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createTrendsGet(deps: TrendsRouteDeps) {
  return async function GET() {
    try {
      const user = await deps.requireUser();
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/trends",
        "GET",
        user.openId,
        undefined,
        { isAdmin: user.isAdmin },
      );
      const payload = await response.json();
      return jsonNoStore(payload, { status: response.status });
    } catch (error) {
      return apiErrorResponse(error);
    }
  };
}
