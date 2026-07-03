import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const webRoot = process.cwd();
const repoRoot = join(webRoot, "..");

function readFromWeb(...parts: string[]): string {
  return readFileSync(join(webRoot, ...parts), "utf8");
}

function readFromRepo(...parts: string[]): string {
  return readFileSync(join(repoRoot, ...parts), "utf8");
}

test("StudioProvider file exports only the component runtime, keeping Fast Refresh quiet", () => {
  const providerSource = readFromWeb("src", "components", "studio", "StudioContext.tsx");
  const hookPath = join(webRoot, "src", "components", "studio", "useStudio.ts");

  assert.equal(providerSource.includes("createContext("), false);
  assert.equal(providerSource.includes("useContext("), false);
  assert.equal(providerSource.includes("export function useStudio"), false);
  assert.equal(existsSync(hookPath), true);

  const hookSource = readFileSync(hookPath, "utf8");
  assert.match(hookSource, /export const StudioContext = createContext<StudioStore \| null>/);
  assert.match(hookSource, /export function useStudio\(\): StudioStore/);
});

test("Next lint/build config uses supported flat-config plumbing without deprecated next lint", () => {
  const eslintConfig = readFromWeb("eslint.config.js");
  const pkg = JSON.parse(readFromWeb("package.json")) as { scripts: Record<string, string> };

  assert.match(eslintConfig, /eslint-config-next\/core-web-vitals/);
  assert.equal(pkg.scripts.lint, "eslint .");
  assert.equal(pkg.scripts["lint:fix"], "eslint . --fix");
});

test("deployment configs keep structural fixes without silencing warnings", () => {
  const route = readFromWeb("src", "app", "api", "[..._path]", "route.ts");
  const dockerfile = readFromWeb("Dockerfile");
  const configStore = readFromWeb("src", "lib", "server", "config-store.ts");
  const langgraph = JSON.parse(readFromRepo("langgraph.json")) as {
    dockerfile_lines?: string[];
    image_distro?: string;
  };

  assert.doesNotMatch(route, /disableWarningLog/);
  assert.doesNotMatch(route, /langgraph-nextjs-api-passthrough|initApiPassthrough/);
  assert.doesNotMatch(dockerfile, /NEXT_TELEMETRY_DISABLED/);
  assert.doesNotMatch(dockerfile, /NPM_CONFIG_(AUDIT|FUND|UPDATE_NOTIFIER)/);
  assert.doesNotMatch(configStore, /rubric\s*:/);
  assert.doesNotMatch(configStore, /rubric .*热切|rubric 评分模型/);
  assert.equal(langgraph.image_distro, "wolfi");
  assert.match(JSON.stringify(langgraph.dockerfile_lines), /mkdir -p \/usr\/local\/bin/);
});
