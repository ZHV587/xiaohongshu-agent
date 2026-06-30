import { requireAdmin, requireUser } from "@/lib/server/authz";
import { createAnalyticsGet } from "./handler";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = createAnalyticsGet({
  requireUser,
  requireAdmin,
  forwardToInternalServer,
});
