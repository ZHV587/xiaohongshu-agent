import { devices, type PlaywrightTestConfig } from "@playwright/test";

/** 两套 E2E 共用的执行约束；测试选择与服务拓扑由各自 config 明确声明。 */
export const commonPlaywrightConfig: PlaywrightTestConfig = {
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  timeout: 900_000,
  expect: { timeout: 15_000 },
  use: {
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
};
