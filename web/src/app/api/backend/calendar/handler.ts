import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/calendar:月份信息 + 按日期组织的排期项。requireUser(需求 12.1/17.1);
// 单账号视图按 account 过滤(forward account 查询串)。照搬 runtime-facts 范式。
type CalendarRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createCalendarGet(deps: CalendarRouteDeps) {
  return async function GET(request: Request) {
    try {
      const account = new URL(request.url).searchParams.get("account")?.trim() || "";
      const user = await deps.requireUser();
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/calendar",
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
