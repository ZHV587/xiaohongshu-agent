import { requireUser } from "@/lib/server/authz";
import { createRecentsGet } from "./handler";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = createRecentsGet({
  requireUser,
  forwardToInternalServer,
});
