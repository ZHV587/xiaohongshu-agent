import { apiErrorResponse, jsonNoStore, type CurrentServerUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";
import { parseCopyLifecycle } from "@/components/studio/backend-mappers";

type CopyLifecycleRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

export type CopyLifecycleAction = "select" | "revision" | "adopt";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

function invalid(error: string): Response {
  return jsonNoStore({ ok: false, error }, { status: 400 });
}

function lifecycleResponse(payload: unknown, status: number, expectedResourceId: string): Response {
  if (status >= 200 && status < 300) {
    const lifecycle = payload && typeof payload === "object" && !Array.isArray(payload)
      ? parseCopyLifecycle((payload as Record<string, unknown>).lifecycle)
      : null;
    if (!lifecycle || lifecycle.resourceId !== expectedResourceId) {
      return jsonNoStore({ ok: false, error: "internal lifecycle payload is invalid" }, { status: 502 });
    }
  }
  return jsonNoStore(payload, { status });
}

function resourceIdFromLifecycleUrl(request: Request): string | null {
  const match = /\/copies\/([^/]+)\/lifecycle\/?$/.exec(new URL(request.url).pathname);
  if (!match) return null;
  try {
    const resourceId = decodeURIComponent(match[1]).trim();
    return UUID_RE.test(resourceId) ? resourceId : null;
  } catch {
    return null;
  }
}

export function createCopyLifecycleGet(deps: CopyLifecycleRouteDeps) {
  return async function GET(request: Request) {
    try {
      const user = await deps.requireUser();
      const resourceId = resourceIdFromLifecycleUrl(request);
      if (!resourceId) return invalid("'resourceId' must be a valid uuid");
      const response = await deps.forwardToInternalServer(
        `/_internal/studio/copies/${encodeURIComponent(resourceId)}/lifecycle`,
        "GET",
        user.openId,
        undefined,
        { isAdmin: user.isAdmin },
      );
      const payload = await response.json();
      return lifecycleResponse(payload, response.status, resourceId);
    } catch (error) {
      return apiErrorResponse(error);
    }
  };
}

function validateLifecycleWrite(action: CopyLifecycleAction, body: Record<string, unknown>): Response | null {
  if (typeof body.resourceId !== "string" || !UUID_RE.test(body.resourceId.trim())) {
    return invalid("'resourceId' must be a valid uuid");
  }
  if (!isPositiveInteger(body.expectedStateVersion)) {
    return invalid("'expectedStateVersion' must be a positive integer");
  }
  if (action === "select" || action === "adopt") {
    if (!isPositiveInteger(body.resourceVersion)) {
      return invalid("'resourceVersion' must be a positive integer");
    }
  }
  if (action === "revision") {
    if (!isPositiveInteger(body.expectedResourceVersion)) {
      return invalid("'expectedResourceVersion' must be a positive integer");
    }
    if (typeof body.title !== "string" || !body.title.trim()) return invalid("'title' is required");
    if (typeof body.body !== "string" || !body.body.trim()) return invalid("'body' is required");
    if (!Array.isArray(body.tags) || body.tags.some((tag) => typeof tag !== "string")) {
      return invalid("'tags' must be an array of strings");
    }
    if (body.cover != null && typeof body.cover !== "string") return invalid("'cover' must be a string");
    if (body.note != null && typeof body.note !== "string") return invalid("'note' must be a string");
  }
  if (body.label != null && typeof body.label !== "string") return invalid("'label' must be a string");
  return null;
}

export function createCopyLifecyclePost(action: CopyLifecycleAction, deps: CopyLifecycleRouteDeps) {
  return async function POST(request: Request) {
    try {
      const user = await deps.requireUser();
      let body: Record<string, unknown>;
      try {
        body = await request.json();
      } catch {
        return invalid("invalid JSON body");
      }
      if (typeof body !== "object" || body === null || Array.isArray(body)) {
        return invalid("body must be an object");
      }
      const validation = validateLifecycleWrite(action, body);
      if (validation) return validation;
      const response = await deps.forwardToInternalServer(
        `/_internal/studio/copies/${action}`,
        "POST",
        user.openId,
        {
          ...body,
          resourceId: String(body.resourceId).trim(),
        },
        { isAdmin: user.isAdmin },
      );
      const payload = await response.json();
      return lifecycleResponse(payload, response.status, String(body.resourceId).trim());
    } catch (error) {
      return apiErrorResponse(error);
    }
  };
}
