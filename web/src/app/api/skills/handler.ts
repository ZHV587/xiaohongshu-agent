import {
  ApiError,
  apiErrorResponse,
  jsonNoStore,
  type CurrentServerUser,
} from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

type SkillRouteDeps = {
  requireUser: () => Promise<CurrentServerUser>;
  forwardToInternalServer: typeof forwardToInternalServer;
};

type SkillContext = { params: Promise<{ skillId: string }> | { skillId: string } };

class SkillRequestError extends ApiError {
  constructor(
    status: number,
    message: string,
    public readonly code: string,
  ) {
    super(status, message);
  }
}

async function bodyObject(request: Request, allowEmpty = false): Promise<Record<string, unknown>> {
  const raw = await request.text();
  if (!raw.trim() && allowEmpty) return {};
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new SkillRequestError(400, "Request body must be valid JSON", "SKILL_INVALID_JSON");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new SkillRequestError(400, "Request body must be an object", "SKILL_INVALID_BODY");
  }
  return value as Record<string, unknown>;
}

async function skillIdFrom(context: SkillContext): Promise<string> {
  const params = await context.params;
  return params.skillId;
}

async function relay(response: Response) {
  return jsonNoStore(await response.json(), { status: response.status });
}

function routeError(error: unknown) {
  if (error instanceof SkillRequestError) {
    return jsonNoStore(
      { ok: false, error: error.message, code: error.code },
      { status: error.status },
    );
  }
  const response = apiErrorResponse(error);
  response.headers.set("Cache-Control", "no-store");
  return response;
}

export function createUserSkillsGet(deps: SkillRouteDeps) {
  return async function GET(request: Request) {
    try {
      const user = await deps.requireUser();
      const includeArchived = new URL(request.url).searchParams.get("includeArchived") ?? undefined;
      return relay(
        await deps.forwardToInternalServer(
          "/_internal/user-skills/list",
          "GET",
          user.openId,
          undefined,
          { isAdmin: user.isAdmin },
          { includeArchived },
        ),
      );
    } catch (error) {
      return routeError(error);
    }
  };
}

export function createSkillRegistryGet(deps: SkillRouteDeps) {
  return async function GET() {
    try {
      const user = await deps.requireUser();
      return relay(
        await deps.forwardToInternalServer(
          "/_internal/user-skills/registry",
          "GET",
          user.openId,
          undefined,
          { isAdmin: user.isAdmin },
        ),
      );
    } catch (error) {
      return routeError(error);
    }
  };
}

function createDefinitionPost(deps: SkillRouteDeps, internalPath: string) {
  return async function POST(request: Request) {
    try {
      const user = await deps.requireUser();
      const body = await bodyObject(request);
      return relay(
        await deps.forwardToInternalServer(
          internalPath,
          "POST",
          user.openId,
          body,
          { isAdmin: user.isAdmin },
        ),
      );
    } catch (error) {
      return routeError(error);
    }
  };
}

export const createUserSkillsPost = (deps: SkillRouteDeps) =>
  createDefinitionPost(deps, "/_internal/user-skills/create");

export const createUserSkillsValidatePost = (deps: SkillRouteDeps) =>
  createDefinitionPost(deps, "/_internal/user-skills/validate");

export function createUserSkillDetailGet(deps: SkillRouteDeps) {
  return async function GET(_request: Request, context: SkillContext) {
    try {
      const user = await deps.requireUser();
      const skillId = await skillIdFrom(context);
      return relay(
        await deps.forwardToInternalServer(
          "/_internal/user-skills/detail",
          "GET",
          user.openId,
          undefined,
          { isAdmin: user.isAdmin },
          { skillId },
        ),
      );
    } catch (error) {
      return routeError(error);
    }
  };
}

export function createUserSkillVersionPatch(deps: SkillRouteDeps) {
  return async function PATCH(request: Request, context: SkillContext) {
    try {
      const user = await deps.requireUser();
      const skillId = await skillIdFrom(context);
      const body = await bodyObject(request);
      return relay(
        await deps.forwardToInternalServer(
          "/_internal/user-skills/version",
          "POST",
          user.openId,
          { ...body, skillId },
          { isAdmin: user.isAdmin },
        ),
      );
    } catch (error) {
      return routeError(error);
    }
  };
}

export function createUserSkillActionPost(deps: SkillRouteDeps, action: string) {
  const allowed = new Set(["publish", "rollback", "enable", "disable", "archive"]);
  if (!allowed.has(action)) throw new Error(`Unknown Skill action: ${action}`);
  return async function POST(request: Request, context: SkillContext) {
    try {
      const user = await deps.requireUser();
      const skillId = await skillIdFrom(context);
      const body = await bodyObject(request, true);
      return relay(
        await deps.forwardToInternalServer(
          `/_internal/user-skills/${action}`,
          "POST",
          user.openId,
          { ...body, skillId },
          { isAdmin: user.isAdmin },
        ),
      );
    } catch (error) {
      return routeError(error);
    }
  };
}
