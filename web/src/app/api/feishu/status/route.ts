import { NextResponse } from "next/server";
import { apiErrorResponse, requireUser } from "@/lib/server/authz";
import { forwardToInternalServer } from "@/lib/server/internal-client";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const user = await requireUser();
    const appConfigured = Boolean(process.env.FEISHU_APP_ID && process.env.FEISHU_APP_SECRET);
    const bitableConfigured = Boolean(
      process.env.FEISHU_BITABLE_APP_TOKEN && process.env.FEISHU_BITABLE_TABLE_ID,
    );

    let uat: { ok?: boolean; authorized?: boolean; error?: string } = {};
    try {
      const resp = await forwardToInternalServer("/_internal/uat-status", "GET", user.openId, undefined, {
        isAdmin: user.isAdmin,
      });
      uat = await resp.json();
    } catch (error) {
      uat = { ok: false, authorized: false, error: (error as Error).message };
    }

    return NextResponse.json({
      ok: true,
      user: { openId: user.openId, name: user.name },
      app_configured: appConfigured,
      bitable_configured: bitableConfigured,
      uat,
    });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
