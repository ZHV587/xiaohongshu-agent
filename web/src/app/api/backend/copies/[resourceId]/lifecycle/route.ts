import { requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";
import { createCopyLifecycleGet } from "../../handler";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = createCopyLifecycleGet({ requireUser, forwardToInternalServer });
