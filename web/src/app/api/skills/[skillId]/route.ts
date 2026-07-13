import { requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";
import { createUserSkillDetailGet, createUserSkillVersionPatch } from "../handler";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
const deps = { requireUser, forwardToInternalServer };
export const GET = createUserSkillDetailGet(deps);
export const PATCH = createUserSkillVersionPatch(deps);
