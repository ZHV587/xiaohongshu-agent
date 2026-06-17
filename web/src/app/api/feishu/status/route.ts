import { NextResponse } from "next/server";

export async function GET() {
  const internalPort = process.env.XHS_INTERNAL_PORT || "8081";
  try {
    const resp = await fetch(`http://127.0.0.1:${internalPort}/_internal/status`, {
      method: "GET"
    });
    if (!resp.ok) {
      return NextResponse.json({ ok: false, error: "Internal server error" }, { status: resp.status });
    }
    const data = await resp.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ ok: false, error: (e as Error).message }, { status: 500 });
  }
}
