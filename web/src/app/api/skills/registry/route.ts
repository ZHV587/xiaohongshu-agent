import { createSkillRegistryGet } from "../handler";
import { requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const GET = createSkillRegistryGet({ requireUser, forwardToInternalServer });
