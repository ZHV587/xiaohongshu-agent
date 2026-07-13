import { defineConfig } from "@playwright/test";

import { commonPlaywrightConfig } from "./playwright.common";

const DEFAULT_BASE_URL = "http://127.0.0.1:3000";

function studioBaseURL(): string {
  const candidate = process.env.XHS_E2E_BASE_URL?.trim() || DEFAULT_BASE_URL;
  let parsed: URL;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error("XHS_E2E_BASE_URL 必须是 http(s) 绝对地址");
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("XHS_E2E_BASE_URL 必须是 http(s) 绝对地址");
  }
  return parsed.toString();
}

/**
 * 真实后端 E2E：只运行 studio-data 基线，不启动或依赖本地 Next 服务。
 * 凭据/真实数据缺失由用例前置探测明确标记 skipped；非空的错误 URL 则直接失败。
 */
export default defineConfig({
  ...commonPlaywrightConfig,
  testMatch: "**/studio-data.spec.ts",
  use: {
    ...(commonPlaywrightConfig.use ?? {}),
    baseURL: studioBaseURL(),
  },
});
