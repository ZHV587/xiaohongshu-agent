import { requireUser } from "@/lib/server/authz";
import { createPipelineGet, createPipelinePost } from "./handler";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = createPipelineGet({
  requireUser,
  forwardToInternalServer,
});

export const POST = createPipelinePost({
  requireUser,
  forwardToInternalServer,
});
