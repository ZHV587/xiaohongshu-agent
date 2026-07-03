import { expect, test } from "@playwright/test";
import { captureDiagnostics, expectDesktopHealthy, expectNoPrototypeExploration, installDsMocks } from "./ds-desktop-helpers";

test.describe("design-system desktop parity UAT", () => {
  test("studio route exercises final response UI, thinking logs, and desktop health", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    const diagnostics = captureDiagnostics(page);
    await installDsMocks(page, "dense");

    await page.goto("/?threadId=fixture-thread");
    await expect(page.locator("header").getByText("小红书创作运营工作室")).toBeVisible();
    await expect(page.getByText("查完 1 步").first()).toBeVisible();
    await expect(page.getByText("已基于数据底座生成选题与草稿", { exact: false })).toBeVisible();

    await page.getByText("查完 1 步").first().click();
    await expect(page.getByText("按语义找相关素材", { exact: false }).first()).toBeVisible();
    const collapse = page.getByRole("button", { name: /收起记录/ });
    if (await collapse.count()) await collapse.first().click();

    await expectNoPrototypeExploration(page);
    await expect(page.getByText("选题卡", { exact: true })).toBeVisible();
    await page.locator('[data-testid="topic-card"]').first().click();
    const deepButton = page.getByRole("button", { name: "进入深度创作" });
    await expect(deepButton).toBeVisible();
    await deepButton.click();
    await expect(page.getByText("文案体检 · 定稿")).toBeVisible();
    await page.getByRole("button", { name: "返回" }).click();
    await page.getByRole("button", { name: "账号运营" }).click();
    await expect(page.getByText("账号矩阵总览")).toBeVisible();

    await expectDesktopHealthy(page, diagnostics);
  });

  test("workbench route exercises command palette, right canvas, Feishu sync, copy, and desktop health", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    const diagnostics = captureDiagnostics(page);
    await installDsMocks(page, "dense");

    await page.goto("/?mode=workbench&threadId=fixture-thread");
    await expect(page.getByText("v1.2 工作台")).toBeVisible();
    await expect(page.getByText("查完 1 步").first()).toBeVisible();
    await page.getByText("查完 1 步").first().click();
    await expect(page.getByText("按语义找相关素材", { exact: false }).first()).toBeVisible();

    await page.keyboard.press("Control+P");
    await expect(page.getByPlaceholder("输入命令或搜索动作...")).toBeVisible();
    await page.getByPlaceholder("输入命令或搜索动作...").fill("标签");
    await expect(page.getByText("补充话题标签")).toBeVisible();
    await expect(page.getByText("无匹配命令")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(page.getByPlaceholder("输入命令或搜索动作...")).toHaveCount(0);

    await expect(page.getByText("飞书同步协作")).toBeVisible();
    await expect(page.getByText("小红书手机预览")).toHaveCount(0);
    await expect(page.getByText("瀑布流卡片")).toHaveCount(0);
    await page.getByRole("button", { name: "立即同步至飞书多维表格" }).click();
    await expect(page.getByText(/正在验证飞书 CLI 环境配置|正在解析多维表格行结构|正在写入文案至多维表格/).first()).toBeVisible();
    await page.getByTitle("点此模拟扫码成功").click();
    await expect(page.getByText("飞书个人身份重连成功")).toBeVisible();

    await page.getByRole("button", { name: /一键复制纯文案/ }).click();
    await expect(page.getByRole("button", { name: "已复制" })).toBeVisible();

    await expectDesktopHealthy(page, diagnostics);
  });

  test("empty collections render honest StateNote content without desktop overflow", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    const diagnostics = captureDiagnostics(page);
    await installDsMocks(page, "empty");

    await page.goto("/");
    await expect(page.getByText("先说一个方向")).toBeVisible();
    await expectNoPrototypeExploration(page);
    await page.getByRole("button", { name: "账号运营" }).click();
    await expect(page.getByText("暂无账号", { exact: false }).first()).toBeVisible();

    const unsafeText = await page.locator("body").innerText();
    expect(unsafeText).not.toMatch(/undefined|null|NaN|\[object Object\]/);
    await expectDesktopHealthy(page, diagnostics);
  });

  test("composer keyboard sends with Enter and preserves Shift+Enter newlines", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    const diagnostics = captureDiagnostics(page);
    await installDsMocks(page, "empty");

    await page.goto("/?threadId=fixture-thread");
    const composer = page.getByPlaceholder(/按职场穿搭出 3 个选题/);
    await expect(composer).toBeVisible();

    await composer.fill("按咖啡店探店出 3 个选题");
    await Promise.all([
      page.waitForRequest((request) => request.url().includes("/runs/stream"), { timeout: 5000 }),
      composer.press("Enter"),
    ]);
    await expect(composer).toHaveValue("");

    await page.waitForTimeout(100);
    await composer.fill("第一行");
    const noSend = page.waitForRequest((request) => request.url().includes("/runs/stream"), { timeout: 500 }).catch(() => null);
    await composer.press("Shift+Enter");
    await expect(composer).toHaveValue("第一行\n");
    expect(await noSend).toBeNull();

    await expectDesktopHealthy(page, diagnostics);
  });
});
