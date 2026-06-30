import { requireUser } from "@/lib/server/authz";
import { createAccountsGet } from "./handler";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = createAccountsGet({
  requireUser,
  forwardToInternalServer,
});
