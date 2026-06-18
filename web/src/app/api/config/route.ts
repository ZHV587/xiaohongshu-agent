import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { AUTH_COOKIE, getFeishuConfig } from "@/lib/server/feishu";
import { verifyJwt } from "@/lib/server/jwt";
import { forwardToInternalServer } from "@/lib/server/internal-client";
import fs from "node:fs";
import path from "node:path";

function updateEnvFile(filePath: string, updates: Record<string, string>) {
  if (!fs.existsSync(filePath)) {
    try {
      fs.writeFileSync(filePath, "", "utf-8");
    } catch {
      return;
    }
  }

  try {
    const content = fs.readFileSync(filePath, "utf-8");
    const lines = content.split(/\r?\n/);
    const newLines: string[] = [];
    const applied = new Set<string>();

    for (const line of lines) {
      const stripped = line.trim();
      if (!stripped || stripped.startsWith("#") || !stripped.includes("=")) {
        newLines.push(line);
        continue;
      }
      const parts = stripped.split("=");
      const key = parts[0].trim();
      if (updates[key] !== undefined) {
        newLines.push(`${key}=${updates[key]}`);
        applied.add(key);
      } else {
        newLines.push(line);
      }
    }

    for (const [key, val] of Object.entries(updates)) {
      if (!applied.has(key)) {
        newLines.push(`${key}=${val}`);
      }
    }

    fs.writeFileSync(filePath, newLines.join("\n"), "utf-8");
  } catch (e) {
    console.error(`Failed to update config at ${filePath}:`, e);
  }
}

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const cfg = getFeishuConfig();
  const payload = verifyJwt(token, cfg.jwtSecret);
  if (!payload) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const resp = await forwardToInternalServer("/_internal/config", "GET", payload.sub);
    if (!resp.ok) {
      const errText = await resp.text();
      return NextResponse.json({ error: errText }, { status: resp.status });
    }
    const data = await resp.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get(AUTH_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const cfg = getFeishuConfig();
  const payload = verifyJwt(token, cfg.jwtSecret);
  if (!payload) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const body = await req.json();
    const { configs } = body;
    if (!configs || typeof configs !== "object") {
      return NextResponse.json({ error: "Bad Request: Missing configs object" }, { status: 400 });
    }

    // 1. 同步转发给 Python 内部服务，热更新它的内存和它的 .env
    const resp = await forwardToInternalServer("/_internal/config", "POST", payload.sub, { configs });
    if (!resp.ok) {
      const errText = await resp.text();
      return NextResponse.json({ error: errText }, { status: resp.status });
    }

    // 2. 在 Next.js 进程内存中更新
    for (const [key, val] of Object.entries(configs)) {
      process.env[key] = String(val);
    }

    // 3. 写入 Next.js 服务端本地的 .env
    const webEnvPath = path.join(process.cwd(), ".env");
    updateEnvFile(webEnvPath, configs);

    // 4. 写入根目录的 .env
    const rootEnvPath = path.join(process.cwd(), "../.env");
    updateEnvFile(rootEnvPath, configs);

    const data = await resp.json();
    return NextResponse.json(data);
  } catch (e) {
    return NextResponse.json({ error: (e as Error).message }, { status: 500 });
  }
}
