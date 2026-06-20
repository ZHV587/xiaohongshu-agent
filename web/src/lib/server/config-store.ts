import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const llmConfigKeys = new Set([
  "LLM_PROVIDER",
  "LLM_BASE_URL",
  "LLM_API_KEY",
  "LLM_QUALITY_MODELS",
  "LLM_GATEWAY_2_BASE_URL",
  "LLM_GATEWAY_2_API_KEY",
  "LLM_GATEWAY_3_BASE_URL",
  "LLM_GATEWAY_3_API_KEY",
]);

export const feishuConfigKeys = new Set([
  "FEISHU_APP_ID",
  "FEISHU_APP_SECRET",
  "FEISHU_BITABLE_APP_TOKEN",
  "FEISHU_BITABLE_TABLE_ID",
  "FEISHU_WIKI_SPACE_ID",
  "XHS_BITABLE_FIELD_TITLE",
  "XHS_BITABLE_FIELD_BODY",
  "XHS_BITABLE_FIELD_TAGS",
  "XHS_BITABLE_FIELD_AUTHOR",
  "XHS_BITABLE_FIELD_STATUS",
]);

export const embeddingConfigKeys = new Set([
  "XHS_EMBEDDING_BASE_URL",
  "XHS_EMBEDDING_API_KEY",
  "XHS_EMBEDDING_MODEL",
  "XHS_EMBEDDING_DIMENSIONS",
  "XHS_EMBEDDING_BATCH_SIZE",
  "XHS_EMBEDDING_TIMEOUT_SECONDS",
]);

export const runtimeApplyKeys = new Set([
  "XHS_BACKEND_APPLY_MODE",
  "XHS_BACKEND_PM2_NAME",
  "XHS_BACKEND_SYSTEMD_SERVICE",
  "XHS_PUBLIC_ORIGIN",
  "XHS_PYTHON_BIN",
]);

export const deployOnlyKeys = new Set([
  "XHS_ADMIN_OPEN_IDS",
  "XHS_JWT_SECRET",
  "XHS_INTERNAL_SECRET",
  "XHS_CONFIG_ENCRYPTION_KEY",
  "XHS_CONFIG_CENTER_PATH",
  "PATH",
  "NODE_OPTIONS",
]);

export const secretConfigKeys = new Set([
  "LLM_API_KEY",
  "LLM_GATEWAY_2_API_KEY",
  "LLM_GATEWAY_3_API_KEY",
  "FEISHU_APP_SECRET",
  "XHS_EMBEDDING_API_KEY",
]);

export function assertAllowedConfigKeys(
  configs: Record<string, unknown>,
): Record<string, string> {
  const allowed = new Set([
    ...llmConfigKeys,
    ...feishuConfigKeys,
    ...embeddingConfigKeys,
    ...runtimeApplyKeys,
  ]);
  const sanitized: Record<string, string> = {};

  for (const [key, value] of Object.entries(configs)) {
    if (deployOnlyKeys.has(key) || !allowed.has(key)) {
      throw new Error(`Config key is not editable: ${key}`);
    }
    sanitized[key] = String(value ?? "");
  }

  return sanitized;
}

export function generateConfigVersion(updates: Record<string, string>): string {
  const hash = crypto
    .createHash("sha256")
    .update(
      JSON.stringify(
        Object.keys(updates)
          .sort()
          .map((key) => [key, updates[key]]),
      ),
    )
    .digest("hex")
    .slice(0, 12);
  return `${new Date().toISOString().replace(/[-:.TZ]/g, "")}-${hash}`;
}

function serializeEnvValue(value: string): string {
  if (!/[#\s"'\\]/.test(value)) return value;
  return JSON.stringify(value);
}

export function updateEnvFile(
  filePath: string,
  updates: Record<string, string>,
): void {
  if (!fs.existsSync(filePath)) fs.writeFileSync(filePath, "", "utf-8");

  const content = fs.readFileSync(filePath, "utf-8");
  const lines = content.split(/\r?\n/);
  const nextLines: string[] = [];
  const applied = new Set<string>();

  for (const line of lines) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("#") || !stripped.includes("=")) {
      nextLines.push(line);
      continue;
    }

    const key = stripped.split("=")[0].trim();
    if (Object.prototype.hasOwnProperty.call(updates, key)) {
      nextLines.push(`${key}=${serializeEnvValue(updates[key])}`);
      applied.add(key);
    } else {
      nextLines.push(line);
    }
  }

  for (const [key, value] of Object.entries(updates)) {
    if (!applied.has(key)) nextLines.push(`${key}=${serializeEnvValue(value)}`);
  }

  fs.writeFileSync(filePath, nextLines.join("\n"), "utf-8");
}

export function envPaths() {
  return {
    webEnvPath: path.join(process.cwd(), ".env"),
    rootEnvPath: path.join(process.cwd(), "../.env"),
  };
}

export function readConfigResponse(): Record<string, string> {
  const keys = [
    ...llmConfigKeys,
    ...feishuConfigKeys,
    ...embeddingConfigKeys,
    ...runtimeApplyKeys,
    "XHS_CONFIG_VERSION",
  ];
  return Object.fromEntries(
    keys.map((key) => {
      const value = process.env[key] || "";
      return [key, secretConfigKeys.has(key) && value ? "********" : value];
    }),
  );
}

export function isConfigCenterEnabled(): boolean {
  return Boolean(process.env.XHS_CONFIG_ENCRYPTION_KEY && process.env.XHS_CONFIG_CENTER_PATH);
}

export function configCenterRunnerArgs(action: "config-status" | "config-set"): string[] {
  if (!process.env.XHS_CONFIG_ENCRYPTION_KEY || !process.env.XHS_CONFIG_CENTER_PATH) {
    throw new Error("Config center is not enabled");
  }
  return [
    "--action",
    action,
    "--config-path",
    process.env.XHS_CONFIG_CENTER_PATH,
    "--encryption-key",
    process.env.XHS_CONFIG_ENCRYPTION_KEY,
  ];
}
