import { NextResponse } from "next/server";
import { apiErrorResponse, requireUser } from "@/lib/server/authz";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const user = await requireUser();
    return NextResponse.json({
      ok: true,
      user: {
        openId: user.openId,
        name: user.name,
        isAdmin: user.isAdmin,
      },
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
