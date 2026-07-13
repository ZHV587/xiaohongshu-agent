import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

// /api/backend/pipeline GET:发布管线队列(scheduled/published/measured)。requireUser
// (需求 13.1/13.2/13.5/17.1);单账号视图按 account 过滤(forward account 查询串)。
// POST 推进 stage(scheduled→published[link] / published→measured):前端层校验
// resourceId/toStage(published 需 link)缺失即 400;逆向/跨级由后端返回 409。
type PipelineRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export function createPipelineGet(deps: PipelineRouteDeps) {
  return async function GET(request: Request) {
    try {
      const account = new URL(request.url).searchParams.get("account")?.trim() || "";
      const user = await deps.requireUser();
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/pipeline",
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

export function createPipelinePost(deps: PipelineRouteDeps) {
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
      const toStage = body.toStage;
      if (typeof toStage !== "string" || !toStage.trim()) {
        return jsonNoStore({ ok: false, error: "missing field 'toStage'" }, { status: 400 });
      }
      const link = body.link;
      if (toStage === "published" && (typeof link !== "string" || !link.trim())) {
        return jsonNoStore({ ok: false, error: "missing field 'link'" }, { status: 400 });
      }
      const response = await deps.forwardToInternalServer(
        "/_internal/studio/pipeline-advance",
        "POST",
        user.openId,
        { resourceId, resourceVersion: body.resourceVersion, toStage, link },
        { isAdmin: user.isAdmin },
      );
      const payload = await response.json();
      return jsonNoStore(payload, { status: response.status });
    } catch (error) {
      return apiErrorResponse(error);
    }
  };
}
