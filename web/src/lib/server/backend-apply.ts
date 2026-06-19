import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export interface ApplyResult {
  mode: "manual" | "pm2" | "systemd";
  applied: boolean;
  message: string;
}

export async function applyBackendConfig(): Promise<ApplyResult> {
  const mode = (process.env.XHS_BACKEND_APPLY_MODE || "manual")
    .trim()
    .toLowerCase();

  if (mode === "manual" || !mode) {
    return {
      mode: "manual",
      applied: false,
      message: "配置已保存。当前为 manual apply 模式，请手动重启 Python 后端。",
    };
  }

  if (mode === "pm2") {
    const name = process.env.XHS_BACKEND_PM2_NAME || "xhs-backend";
    await execFileAsync("pm2", ["restart", name], { windowsHide: true });
    return { mode: "pm2", applied: true, message: `已执行 pm2 restart ${name}` };
  }

  if (mode === "systemd") {
    const service =
      process.env.XHS_BACKEND_SYSTEMD_SERVICE || "xhs-backend.service";
    await execFileAsync("systemctl", ["restart", service], {
      windowsHide: true,
    });
    return {
      mode: "systemd",
      applied: true,
      message: `已执行 systemctl restart ${service}`,
    };
  }

  throw new Error(`Unsupported XHS_BACKEND_APPLY_MODE: ${mode}`);
}
