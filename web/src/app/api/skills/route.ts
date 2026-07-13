import { requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";
import { createUserSkillsGet, createUserSkillsPost } from "./handler";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const deps = { requireUser, forwardToInternalServer };
export const GET = createUserSkillsGet(deps);
export const POST = createUserSkillsPost(deps);
