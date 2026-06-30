import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/analytics:看板 + 选题库 + 爆款拆解(按账号聚合 performance_metric)。
// 鉴权:指定 account(单账号视图) → requireUser;未指定 account(矩阵总览,跨账号聚合)
// → requireAdmin(需求 17.1)。照搬 runtime-facts 范式:鉴权 → forwardToInternalServer →
// jsonNoStore;鉴权失败在转发前拦截,不触达后端。
type AnalyticsRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  requireAdmin: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createAnalyticsGet(deps: AnalyticsRouteDeps) {
  return async function GET(request: Request) {
    try {
      const account = new URL(request.url).searchParams.get("account")?.trim() || "";
      const user = account ? await deps.requireUser() : await deps.requireAdmin();
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/analytics",
        "GET",
        user.openId,
        undefined,
        { isAdmin: user.isAdmin },
        account ? { account } : undefined,
      );
      const payload = await response.json();
      return jsonNoStore(payload, { status: response.status });
    } catch (error) {
      return apiErrorResponse(error);
    }
  };
}
