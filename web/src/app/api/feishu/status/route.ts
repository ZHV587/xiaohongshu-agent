import { NextResponse } from "next/server";

export async function GET() {
  const appId = process.env.FEISHU_APP_ID;
  const appSecret = process.env.FEISHU_APP_SECRET;
  return NextResponse.json({
    ok: true,
    bot_configured: !!(appId && appSecret),
    internal_port: 0
  });
}
