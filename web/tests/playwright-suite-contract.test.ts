import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const webRoot = process.cwd();
const readWeb = (file: string) => readFileSync(join(webRoot, file), "utf8");
const workflow = readFileSync(join(webRoot, "..", ".github", "workflows", "ci.yml"), "utf8");

test("Playwright separates local fixture UI from the real-backend studio baseline", () => {
  const localConfig = readWeb("playwright.config.ts");
  const studioConfig = readWeb("playwright.studio-data.config.ts");

  assert.match(localConfig, /testIgnore:\s*"\*\*\/studio-data\.spec\.ts"/);
  assert.match(localConfig, /webServer:\s*\{/);
  assert.match(localConfig, /node \.next\/standalone\/server\.js/);
  assert.match(studioConfig, /testMatch:\s*"\*\*\/studio-data\.spec\.ts"/);
  assert.doesNotMatch(studioConfig, /webServer:\s*\{/);
  assert.match(studioConfig, /XHS_E2E_BASE_URL\?\.trim\(\)\s*\|\|\s*DEFAULT_BASE_URL/);
});

test("CI wires each E2E suite to its own topology and installed browser", () => {
  const commonConfig = readWeb("playwright.common.ts");

  assert.match(workflow, /web-ui-e2e:/);
  assert.match(workflow, /pnpm run test:e2e:ui/);
  assert.match(workflow, /pnpm run test:e2e:studio/);
  assert.match(
    workflow,
    /- name: Build web application\s+env:\s+(?:#[^\n]*\s+)*NEXT_PUBLIC_API_URL: \/api\s+NEXT_PUBLIC_ASSISTANT_ID: agent\s+run: pnpm build/,
  );
  assert.match(workflow, /cp -R \.next\/static \.next\/standalone\/\.next\/static/);
  assert.doesNotMatch(workflow, /pnpm exec playwright test 2>&1/);
  assert.doesNotMatch(commonConfig, /channel:\s*["']chrome["']/);
});
