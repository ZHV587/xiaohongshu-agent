import { test } from "@playwright/test";
import { captureDiagnostics, expectDesktopHealthy, installDsMocks, openTweaks, screenshotNonBlank } from "./ds-desktop-helpers";

test.describe("design-system desktop visual spot checks", () => {
  test("captures Studio and Workbench desktop states", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    const diagnostics = captureDiagnostics(page);
    await installDsMocks(page, "dense");

    await page.goto("/?threadId=fixture-thread");
    await openTweaks(page);
    await screenshotNonBlank(page, testInfo, "studio-create-stack");

    await page.getByText("左右分栏").click();
    await screenshotNonBlank(page, testInfo, "studio-create-split");

    await page.getByText("多栏工作台").click();
    await screenshotNonBlank(page, testInfo, "studio-deep-workspace");

    await page.getByText("同屏融合").click();
    await screenshotNonBlank(page, testInfo, "studio-ops-hybrid");

    await page.goto("/?mode=workbench&threadId=fixture-thread");
    await screenshotNonBlank(page, testInfo, "workbench-feishu-sync");

    await page.keyboard.press("Control+P");
    await screenshotNonBlank(page, testInfo, "workbench-command-palette");

    await expectDesktopHealthy(page, diagnostics);
  });
});
