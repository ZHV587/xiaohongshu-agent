import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/accounts:账号矩阵档案 + 聚合总览(overview 由后端基于真实账号计算)。
// requireUser(需求 9.1/9.3/9.5/17.1)。照搬 runtime-facts 范式。
type AccountsRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createAccountsGet(deps: AccountsRouteDeps) {
  return async function GET() {
    try {
      const user = await deps.requireUser();
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/accounts",
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
