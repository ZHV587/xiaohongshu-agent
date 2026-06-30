import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/recents:登录用户最近创作(按时间倒序)。requireUser(需求 7.1/7.2/7.4/17.1)。
// 后端按登录用户(open_id)归属过滤,照搬 runtime-facts 范式。
type RecentsRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createRecentsGet(deps: RecentsRouteDeps) {
  return async function GET() {
    try {
      const user = await deps.requireUser();
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/recents",
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
