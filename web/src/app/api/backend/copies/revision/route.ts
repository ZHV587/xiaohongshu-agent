import { requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";
import { createCopyLifecyclePost } from "../handler";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = createCopyLifecyclePost("revision", { requireUser, forwardToInternalServer });
