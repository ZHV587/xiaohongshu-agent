import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { AUTH_COOKIE, getFeishuConfig } from "@/lib/server/feishu";
import { verifyJwt, type XhsJwtPayload } from "@/lib/server/jwt";

export interface CurrentServerUser {
  openId: string;
  name?: string;
  isAdmin: boolean;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

export function parseAdminOpenIds(
  raw = process.env.XHS_ADMIN_OPEN_IDS ?? "",
): Set<string> {
  return new Set(
    raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

export function isAdminOpenId(openId: string): boolean {
  return parseAdminOpenIds().has(openId);
}

export async function requireUser(): Promise<CurrentServerUser> {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_COOKIE)?.value;
  if (!token) throw new ApiError(401, "Unauthorized");

  const cfg = getFeishuConfig();
  const payload: XhsJwtPayload | null = verifyJwt(token, cfg.jwtSecret);
  if (!payload?.sub) throw new ApiError(401, "Unauthorized");

  return {
    openId: payload.sub,
    name: payload.name,
    isAdmin: isAdminOpenId(payload.sub),
  };
}

export async function requireAdmin(): Promise<CurrentServerUser> {
  const user = await requireUser();
  if (!user.isAdmin) throw new ApiError(403, "Forbidden");
  return user;
}

export function jsonNoStore(body: unknown, init?: ResponseInit): NextResponse {
  const res = NextResponse.json(body, init);
  res.headers.set("Cache-Control", "no-store");
  return res;
}

export function apiErrorResponse(error: unknown): NextResponse {
  if (error instanceof ApiError) {
    return NextResponse.json({ error: error.message }, { status: error.status });
  }
  return NextResponse.json(
    { error: (error as Error).message || "Internal Server Error" },
    { status: 500 },
  );
}
