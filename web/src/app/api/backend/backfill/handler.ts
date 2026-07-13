import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/backfill POST:回填落库为 performance_metric + 飞书同步。requireUser
// (需求 15.1/15.3/17.1)。前端层校验 resourceId/metrics 缺失即 400;非数值/负值由后端
// _clean_metrics 校验返回 400(前端据此提示该字段需非负数值)。照搬 runtime-facts 范式。
type BackfillRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createBackfillPost(deps: BackfillRouteDeps) {
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
      const resourceId = body.resourceId;
      if (typeof resourceId !== "string" || !resourceId.trim()) {
        return jsonNoStore({ ok: false, error: "missing field 'resourceId'" }, { status: 400 });
      }
      const metrics = body.metrics;
      if (typeof metrics !== "object" || metrics === null || Array.isArray(metrics)) {
        return jsonNoStore({ ok: false, error: "missing field 'metrics'" }, { status: 400 });
      }
      const resourceVersion = body.resourceVersion;
      if (resourceVersion != null && (!Number.isInteger(resourceVersion) || Number(resourceVersion) <= 0)) {
        return jsonNoStore({ ok: false, error: "'resourceVersion' must be a positive integer" }, { status: 400 });
      }
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/backfill",
        "POST",
        user.openId,
        {
          resourceId,
          resourceVersion,
          metrics,
          publishedAt: body.publishedAt,
          link: body.link ?? body.noteUrl,
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
