import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

import {
  appendUserSkillVersion,
  createUserSkill,
  friendlySkillError,
  getUserSkill,
  listSkillRegistry,
  listUserSkills,
  runUserSkillAction,
  validateUserSkill,
} from "../src/components/skills/api";
import { EMPTY_SKILL_DEFINITION } from "../src/components/skills/types";

const root = process.cwd();
const read = (...parts: string[]) => readFileSync(join(root, ...parts), "utf8");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const target = join(dir, name);
    return statSync(target).isDirectory() ? walk(target) : [target];
  });
}

test("AppShell mounts one shared capability provider inside ThreadStateProvider", () => {
  const appShell = read("src", "components", "AppShell.tsx");
  assert.equal(appShell.match(/<CapabilityRegistryProvider>/g)?.length, 1);
  assert.equal(appShell.match(/<CapabilityToolbox\s*\/>/g)?.length, 1);
  assert.ok(appShell.indexOf("<ThreadStateProvider>") < appShell.indexOf("<CapabilityRegistryProvider>"));
  assert.ok(appShell.indexOf("</CapabilityRegistryProvider>") < appShell.indexOf("</ThreadStateProvider>"));
});

test("Studio and Workbench open the same toolbox and Ctrl+P has one owner", () => {
  const creation = read("src", "components", "studio", "CreationScreen.tsx");
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assert.match(creation, /useCapabilityRegistry\(\)/);
  assert.match(creation, /onClick=\{openToolbox\}/);
  assert.match(workbench, /useCapabilityRegistry\(\)/);
  assert.match(workbench, /onClick=\{openToolbox\}/);
  assert.doesNotMatch(workbench, /CommandPalette|paletteOpen|setPaletteOpen/);

  const componentSource = walk(join(root, "src", "components"))
    .filter((file) => /\.tsx?$/.test(file))
    .map((file) => readFileSync(file, "utf8"))
    .join("\n");
  assert.equal(componentSource.match(/event\.key\.toLowerCase\(\) === "p"/g)?.length, 1);
});

test("toolbox groups built-ins and user Skills with published execute and draft test states", () => {
  const toolbox = read("src", "components", "skills", "CapabilityToolbox.tsx");
  assert.match(toolbox, /系统内置能力/);
  assert.match(toolbox, /我的 Skill/);
  assert.match(toolbox, /skill\.status === "published" && published/);
  assert.match(toolbox, /skill\.status === "draft"/);
  assert.match(toolbox, /executeUser\(published, "execute"/);
  assert.match(toolbox, /executeUser\(skill, "test"/);
  assert.match(toolbox, /<Badge tone="synced" shape="chip">内置<\/Badge>/);

  const registry = read("src", "components", "skills", "CapabilityRegistry.tsx");
  const builtin = registry.slice(registry.indexOf("const executeBuiltin"), registry.indexOf("const executeUser"));
  assert.match(builtin, /thread\.submitText/);
  assert.doesNotMatch(builtin, /executeUserSkill|selected_user_skill/);
});

test("explicit user Skill execution always supplies an exact versionId", () => {
  const registry = read("src", "components", "skills", "CapabilityRegistry.tsx");
  assert.match(registry, /const targetVersionId/);
  assert.match(registry, /versionId: targetVersionId/);
  assert.match(registry, /thread\.executeUserSkill/);

  const provider = read("src", "components", "thread", "ThreadStateProvider.tsx");
  assert.match(provider, /version_id: invocation\.versionId/);
});

test("Skill client covers list, registry, detail, create, validate, immutable edit and lifecycle actions", async () => {
  const calls: Array<{ url: string; method: string; body?: string }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({
      url: typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
      method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? init.body : undefined,
    });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    await listUserSkills(true);
    await listSkillRegistry();
    await getUserSkill("skill / one");
    await validateUserSkill(EMPTY_SKILL_DEFINITION);
    await createUserSkill(EMPTY_SKILL_DEFINITION);
    await appendUserSkillVersion("skill-1", 7, EMPTY_SKILL_DEFINITION);
    for (const action of ["publish", "rollback", "enable", "disable", "archive"] as const) {
      await runUserSkillAction("skill-1", action, action === "publish" || action === "rollback" ? 5 : undefined);
    }
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.deepEqual(calls.map(({ url, method }) => [url, method]), [
    ["/api/skills?includeArchived=true", "GET"],
    ["/api/skills/registry", "GET"],
    ["/api/skills/skill%20%2F%20one", "GET"],
    ["/api/skills/validate", "POST"],
    ["/api/skills", "POST"],
    ["/api/skills/skill-1", "PATCH"],
    ["/api/skills/skill-1/publish", "POST"],
    ["/api/skills/skill-1/rollback", "POST"],
    ["/api/skills/skill-1/enable", "POST"],
    ["/api/skills/skill-1/disable", "POST"],
    ["/api/skills/skill-1/archive", "POST"],
  ]);
  assert.deepEqual(JSON.parse(calls[5].body ?? "{}"), { ...EMPTY_SKILL_DEFINITION, expectedLatestVersion: 7 });
  assert.deepEqual(JSON.parse(calls[6].body ?? "{}"), { version: 5 });
  assert.deepEqual(JSON.parse(calls[7].body ?? "{}"), { version: 5 });
  assert.deepEqual(JSON.parse(calls[8].body ?? "{}"), {});
});

test("Skill API errors stay user-facing even when an upstream message is English", () => {
  assert.equal(friendlySkillError("SKILL_NAME_CONFLICT", "duplicate", 409), "已有同名能力，请换一个名称。");
  assert.equal(friendlySkillError(undefined, "Internal Server Error", 500), "能力服务暂时不可用，请稍后重试。");
  assert.equal(friendlySkillError(undefined, "Forbidden", 403), "你没有权限执行这项操作。");
});
