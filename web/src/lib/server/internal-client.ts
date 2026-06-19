import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { configCenterRunnerArgs } from "@/lib/server/config-store";

const execFileAsync = promisify(execFile);

export async function forwardToInternalServer(
  pathName: string,
  method: "GET" | "POST",
  openId: string,
  extraBody?: any,
  extraHeaders?: any
): Promise<Response> {
  const scriptPath = path.resolve(process.cwd(), "../tools/web_bridge_runner.py");
  
  let action = "";
  const runnerArgs: string[] = [scriptPath, "--open-id", openId];
  
  if (pathName === "/_internal/chats") {
    action = "chats";
    runnerArgs.push("--action", "chats");
  } else if (pathName === "/_internal/uat") {
    action = "save-uat";
    const { uat, refresh_token, expires_at, scopes, name } = extraBody || {};
    runnerArgs.push(
      "--action", "save-uat",
      "--uat", String(uat),
      "--refresh-token", String(refresh_token || ""),
      "--expires-at", String(expires_at),
      "--scopes", (scopes || []).join(","),
      "--name", String(name || "")
    );
  } else if (pathName === "/_internal/uat-status") {
    action = "uat-status";
    runnerArgs.push("--action", "uat-status");
  } else if (pathName === "/_internal/wiki-space") {
    action = "wiki-space";
    runnerArgs.push("--action", "wiki-space");
  } else if (pathName === "/_internal/config-status") {
    action = "config-status";
    runnerArgs.push(...configCenterRunnerArgs("config-status"));
  } else if (pathName === "/_internal/config-set") {
    action = "config-set";
    runnerArgs.push(
      ...configCenterRunnerArgs("config-set"),
      "--configs",
      JSON.stringify(extraBody?.configs || {}),
    );
  } else {
    return new Response(JSON.stringify({ error: `Unknown internal path: ${pathName}` }), { status: 404 });
  }

  try {
    let executable = "uv";
    let cmdArgs = ["run", "python", ...runnerArgs];

    if (process.platform !== "win32") {
      // 生产服务器环境 (Linux)
      // 直接用虚拟环境的 python 解释器跑，跳过 uv 包装
      executable = process.env.XHS_PYTHON_BIN || "/home/ubuntu/xiaohongshu-agent/.venv/bin/python3";
      cmdArgs = runnerArgs;
    }

    const { stdout, stderr } = await execFileAsync(executable, cmdArgs, {
      cwd: path.resolve(process.cwd(), ".."),
      env: { ...process.env }
    });
    
    if (stderr && stderr.trim().toLowerCase().includes("error")) {
      console.error(`web_bridge_runner stderr: ${stderr}`);
    }
    
    const result = JSON.parse(stdout.trim());
    if (result.ok === false) {
      return new Response(JSON.stringify({ error: result.error || "Execution failed" }), { status: 500 });
    }
    return new Response(JSON.stringify(result), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });
  } catch (e: any) {
    console.error(`Failed to run web_bridge_runner for action ${action}:`, e);
    let errorMsg = e.message;
    if (e.stdout) {
      try {
        const result = JSON.parse(e.stdout.trim());
        if (result.error) {
          errorMsg = result.error;
        }
      } catch {
        // Ignore JSON parsing errors for stdout
      }
    }
    return new Response(JSON.stringify({ error: errorMsg }), { status: 500 });
  }
}
