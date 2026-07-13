import { defineConfig } from "@playwright/test";

import { commonPlaywrightConfig } from "./playwright.common";

const LOCAL_BASE_URL = "http://127.0.0.1:3000";

/**
 * 本地 UI E2E：只运行完全自带 fixture 的界面契约，并由 Playwright 管理 Next 服务。
 * 真实后端 studio-data 基线使用 playwright.studio-data.config.ts，不能混入本拓扑。
 */
export default defineConfig({
  ...commonPlaywrightConfig,
  testIgnore: "**/studio-data.spec.ts",
  use: {
    ...(commonPlaywrightConfig.use ?? {}),
    baseURL: LOCAL_BASE_URL,
  },
  webServer: {
    command: process.env.CI ? "node .next/standalone/server.js" : "pnpm dev",
    url: LOCAL_BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
