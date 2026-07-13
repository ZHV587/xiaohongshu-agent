import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/schedule POST:排期落库 + 飞书同步。requireUser(需求 14.1/17.1);照搬
// runtime-facts 范式:鉴权 → 请求体校验 → forwardToInternalServer POST → jsonNoStore。
// 前端层先校验 resourceId/date/time/account 缺失即 400(供前端回滚乐观更新),完整请求转后端
// 真实落库;后端落库失败回非 2xx,前端据此回滚。
type ScheduleRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

const REQUIRED_FIELDS = [
  "resourceId",
  "targetResourceVersion",
  "expectedLatestResourceVersion",
  "expectedStateVersion",
  "date",
  "time",
  "account",
] as const;

function missingField(body: Record<string, unknown>): string | null {
  for (const field of REQUIRED_FIELDS) {
    const value = body[field];
    if (value === undefined || value === null || (typeof value === "string" && !value.trim())) {
      return field;
    }
  }
  return null;
}

export function createSchedulePost(deps: ScheduleRouteDeps) {
  return async function POST(request: Request) {
    try {
      const user = await deps.requireUser();
      let body: Record<string, unknown>;
      try {
        body = await request.json();
      } catch {
        return jsonNoStore({ ok: false, error: "invalid JSON body" }, { status: 400 });
      }
      if (typeof body !== "object" || body === null || Array.isArray(body)) {
        return jsonNoStore({ ok: false, error: "body must be an object" }, { status: 400 });
      }
      const missing = missingField(body);
      if (missing) {
        return jsonNoStore({ ok: false, error: `missing field '${missing}'` }, { status: 400 });
      }
      if (!Number.isInteger(body.targetResourceVersion) || Number(body.targetResourceVersion) <= 0) {
        return jsonNoStore({ ok: false, error: "'targetResourceVersion' must be a positive integer" }, { status: 400 });
      }
      if (!Number.isInteger(body.expectedLatestResourceVersion) || Number(body.expectedLatestResourceVersion) <= 0) {
        return jsonNoStore({ ok: false, error: "'expectedLatestResourceVersion' must be a positive integer" }, { status: 400 });
      }
      if (!Number.isInteger(body.expectedStateVersion) || Number(body.expectedStateVersion) <= 0) {
        return jsonNoStore({ ok: false, error: "'expectedStateVersion' must be a positive integer" }, { status: 400 });
      }
      const finalDraft = body.finalDraft;
      if (
        finalDraft != null && (
          typeof finalDraft !== "object" || Array.isArray(finalDraft) ||
          typeof (finalDraft as Record<string, unknown>).title !== "string" ||
          typeof (finalDraft as Record<string, unknown>).body !== "string" ||
          !Array.isArray((finalDraft as Record<string, unknown>).tags) ||
          ((finalDraft as Record<string, unknown>).tags as unknown[]).some((tag) => typeof tag !== "string") ||
          ((finalDraft as Record<string, unknown>).cover != null && typeof (finalDraft as Record<string, unknown>).cover !== "string") ||
          ((finalDraft as Record<string, unknown>).note != null && typeof (finalDraft as Record<string, unknown>).note !== "string")
        )
      ) {
        return jsonNoStore({ ok: false, error: "'finalDraft' must contain title, body and tags" }, { status: 400 });
      }
      const requestId = body.requestId;
      if (requestId != null && (typeof requestId !== "string" || !requestId.trim())) {
        return jsonNoStore({ ok: false, error: "'requestId' must be a non-empty string" }, { status: 400 });
      }
      if (finalDraft != null && requestId == null) {
        return jsonNoStore({ ok: false, error: "missing field 'requestId'" }, { status: 400 });
      }
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/schedule",
        "POST",
        user.openId,
        {
          resourceId: body.resourceId,
          targetResourceVersion: body.targetResourceVersion,
          expectedLatestResourceVersion: body.expectedLatestResourceVersion,
          expectedStateVersion: body.expectedStateVersion,
          date: body.date,
          time: body.time,
          account: body.account,
          ...(finalDraft == null ? {} : { finalDraft }),
          ...(requestId == null ? {} : { requestId }),
        },
        { isAdmin: user.isAdmin },
      );
      const payload = await response.json();
      return jsonNoStore(payload, { status: response.status });
    } catch (error) {
      return apiErrorResponse(error);
    }
  };
}
