import { requireUser } from "@/lib/server/authz";
import { createTrendsGet } from "./handler";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = createTrendsGet({
  requireUser,
  forwardToInternalServer,
});
