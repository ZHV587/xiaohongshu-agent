import { defineConfig, devices } from "@playwright/test";

// E2E 基线配置(studio-data-integration task 11)。
// 针对真实后端运行,不 mock 业务数据;baseURL / 鉴权密钥经环境变量注入,
// 默认指向本地 dev server,可经 XHS_E2E_BASE_URL 指向任意部署(含生产)。
//
//   XHS_E2E_BASE_URL   被测站点(默认 http://127.0.0.1:3000)
//   XHS_JWT_SECRET     与后端共享的 JWT 密钥(签发 xhs_auth 登录 cookie 必需)
//   XHS_E2E_OPEN_ID    登录身份 open_id(必需;须是后端 XHS_ADMIN_OPEN_IDS 之一以覆盖矩阵总览)
//   XHS_E2E_USER_NAME  登录显示名(可选;断言顶栏用户名一致)
const baseURL = process.env.XHS_E2E_BASE_URL ?? "http://127.0.0.1:3000";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  // 真实数据基线驱动多轮真实 LLM 对话(选题产出 + 多版本文案 + 排期),每轮 LLM 往返
  // 可达 ~90-120s,偶发长尾更久;单测试放宽到 15 分钟以容纳整条链路 + LLM 长尾。
  timeout: 900_000,
  expect: { timeout: 15_000 },
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      // 用系统安装的 Chrome(channel),避免在受限网络下载 Playwright 自带 chromium。
      use: { ...devices["Desktop Chrome"], channel: "chrome", viewport: { width: 1440, height: 900 } },
    },
  ],
});
