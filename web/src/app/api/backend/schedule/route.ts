import { requireUser } from "@/lib/server/authz";
import { createSchedulePost } from "./handler";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const POST = createSchedulePost({
  requireUser,
  forwardToInternalServer,
});
