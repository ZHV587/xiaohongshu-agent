import { requireAdmin } from "@/lib/server/authz";
import { createRuntimeFactsGet } from "./handler";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = createRuntimeFactsGet({
  requireAdmin,
  forwardToInternalServer,
});
