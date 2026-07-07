import { test } from "@playwright/test";
import { captureDiagnostics, expectDesktopHealthy, expectNoPrototypeExploration, installDsMocks, screenshotNonBlank } from "./ds-desktop-helpers";

test.describe("design-system desktop visual spot checks", () => {
  test("captures Studio and Workbench desktop states", async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    const diagnostics = captureDiagnostics(page);
    await installDsMocks(page, "dense");

    await page.goto("/?threadId=fixture-thread");
    await expectNoPrototypeExploration(page);
    await screenshotNonBlank(page, testInfo, "studio-create-final");

    // v2:dense fixture 含 xhs_copy → 创作屏右栏就地进编辑器,直接截就地编辑态(不再跳独立深创屏)。
    await page.locator('[data-testid="draft-body"]').first().waitFor({ state: "visible", timeout: 15_000 });
    await screenshotNonBlank(page, testInfo, "studio-editor-inplace");

    await page.getByRole("button", { name: "账号运营" }).click();
    await screenshotNonBlank(page, testInfo, "studio-ops-final");

    await page.goto("/?mode=workbench&threadId=fixture-thread");
    await screenshotNonBlank(page, testInfo, "workbench-feishu-sync");

    await page.keyboard.press("Control+P");
    await screenshotNonBlank(page, testInfo, "workbench-command-palette");

    await expectDesktopHealthy(page, diagnostics);
  });
});
