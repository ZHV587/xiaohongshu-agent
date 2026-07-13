import { requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";
import { createUserSkillActionPost } from "../../handler";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const POST = createUserSkillActionPost({ requireUser, forwardToInternalServer }, "archive");
