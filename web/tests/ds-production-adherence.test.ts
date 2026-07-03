import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";

const webRoot = process.cwd();
const repoRoot = join(webRoot, "..");
const dsRoot = join(repoRoot, "小红书文案助手 Design System");
const srcRoot = join(webRoot, "src");

function read(...parts: string[]): string {
  return readFileSync(join(webRoot, ...parts), "utf8");
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

test("production globals define every design-system token name", () => {
  const globals = read("src", "app", "globals.css");
  const tokenFiles = walk(join(dsRoot, "tokens")).filter((path) => path.endsWith(".css"));
  const tokenNames = new Set<string>();

  for (const file of tokenFiles) {
    const source = readFileSync(file, "utf8");
    for (const match of source.matchAll(/--[a-zA-Z0-9-]+(?=\s*:)/g)) {
      tokenNames.add(match[0]);
    }
  }

  const missing = [...tokenNames].filter((token) => !globals.includes(token)).sort();
  assert.deepEqual(missing, []);
});

test("production-facing React code imports DS primitives instead of legacy ui primitives", () => {
  const productionDirs = [
    join(srcRoot, "components", "studio"),
    join(srcRoot, "components", "thread", "history"),
    join(srcRoot, "providers"),
  ];
  const productionFiles = [
    join(srcRoot, "components", "auth-gate.tsx"),
    ...productionDirs.flatMap((dir) => walk(dir).filter((path) => /\.(ts|tsx)$/.test(path))),
  ];
  const offenders = productionFiles
    .filter((path) => readFileSync(path, "utf8").includes("@/components/ui/"))
    .map((path) => relative(webRoot, path).replaceAll("\\", "/"))
    .sort();

  assert.deepEqual(offenders, []);
});

test("each manifest DS component has a production usage outside the DS library", () => {
  const manifest = JSON.parse(readFileSync(join(dsRoot, "_ds_manifest.json"), "utf8")) as {
    components: Array<{ name: string }>;
  };
  const intentionallyUnused = new Set(["NoteCard", "PhoneFrame"]);
  const productionFiles = walk(srcRoot)
    .filter((path) => /\.(ts|tsx)$/.test(path))
    .filter((path) => !relative(srcRoot, path).replaceAll("\\", "/").startsWith("components/ds/"));
  const productionSource = productionFiles.map((path) => readFileSync(path, "utf8")).join("\n");

  const unused = manifest.components
    .map((component) => component.name)
    .filter((name) => !intentionallyUnused.has(name))
    .filter((name) => !new RegExp(`<${name}\\b`).test(productionSource))
    .sort();

  assert.deepEqual(unused, []);
});

test("design-system desktop starting points have production parity tests", () => {
  const uiTests = read("tests", "ds-ui-kit-alignment.test.ts");
  const requiredTestNames = [
    "studio production shell exposes the DS Tweaks variants",
    "creation screen supports all DS right-panel layouts",
    "deep creation supports all DS forms and supporting panels",
    "operations screen supports all DS hosting variants",
    "workbench starting point has a production entry and DS interaction affordances",
    "workbench right canvas carries the DS bottom copy bar",
    "workbench command palette mirrors the DS searchable palette",
    "workbench feishu sync mirrors the DS sync cards and flip auth",
    "workbench right canvas focuses on Feishu sync without mobile preview tabs",
    "production desktop removes mobile preview surfaces",
    "desktop shells expose accessible landmarks and keyboard focus affordances",
  ];

  const missing = requiredTestNames.filter((name) => !uiTests.includes(`test("${name}"`));
  assert.deepEqual(missing, []);
});

test("DS primitive source parity covers public prop APIs", () => {
  const primitiveContracts: Record<string, { path: string; markers: string[] }> = {
    Button: {
      path: "core/Button.tsx",
      markers: ["export interface ButtonProps", "variant?", '"primary"', '"secondary"', '"soft"', '"ghost"', "size?", '"sm"', '"md"', '"lg"', "block?", "loading?", "disabled?", "leftIcon?", "rightIcon?"],
    },
    IconButton: {
      path: "core/IconButton.tsx",
      markers: ["export interface IconButtonProps", "size?", '"sm"', '"md"', '"lg"', "variant?", '"ghost"', '"soft"', '"solid"', '"surface"', "rounded?", '"full"', "label?"],
    },
    Badge: {
      path: "core/Badge.tsx",
      markers: ["export interface BadgeProps", "tone?", '"neutral"', '"synced"', '"hot"', '"topic"', '"info"', '"coral"', '"draft"', "shape?", '"pill"', '"chip"', "dot?"],
    },
    Avatar: {
      path: "core/Avatar.tsx",
      markers: ["export interface AvatarProps", "name?", "src?", "glyph?", "size?", "variant?", '"coral"', '"solid"', '"neutral"', '"agent"'],
    },
    Card: {
      path: "core/Card.tsx",
      markers: ["export interface CardProps", "interactive?", "tone?", '"default"', '"sunken"', '"coral"', "padding?", '"none"', '"sm"', '"md"', '"lg"'],
    },
    StatCard: {
      path: "data/StatCard.tsx",
      markers: ["export interface StatCardProps", "label:", "value:", "unit?", "delta?", "icon?", "tone?", '"neutral"', '"coral"', '"topic"', '"success"', "editable?", "onValueChange?"],
    },
    NoteCard: {
      path: "device/NoteCard.tsx",
      markers: ["export interface NoteCardProps", "image?", "title?", "author?", "authorInitial?", "likes?", "ratio?", "dim?"],
    },
    PhoneFrame: {
      path: "device/PhoneFrame.tsx",
      markers: ["export interface PhoneFrameProps", "width?", "children"],
    },
    Input: {
      path: "forms/Input.tsx",
      markers: ["export interface InputProps", "leadingIcon?", "trailing?", "invalid?", "containerStyle?"],
    },
    Select: {
      path: "forms/Select.tsx",
      markers: ["export interface SelectOption", "value:", "label:", "export interface SelectProps", "options?", "invalid?", "containerStyle?", "children?"],
    },
    Textarea: {
      path: "forms/Textarea.tsx",
      markers: ["export interface TextareaProps", "footer?", "invalid?", "rows?", "innerRef?", "containerStyle?"],
    },
    TopicCard: {
      path: "content/TopicCard.tsx",
      markers: ["export interface TopicCardProps", "index?", "title:", "rationale?", "hotRate?", "onClick?"],
    },
    ThinkingAura: {
      path: "content/ThinkingAura.tsx",
      markers: ["export interface ThinkingAuraProps", "title?", "steps?", "logs?", "defaultOpen?", "defaultCollapsed?"],
    },
    HashtagTag: {
      path: "content/HashtagTag.tsx",
      markers: ["export interface HashtagTagProps", "tone?", '"topic"', '"coral"', '"plain"', "addable?", "onAdd?"],
    },
  };

  const missing: Record<string, string[]> = {};
  for (const [name, contract] of Object.entries(primitiveContracts)) {
    const source = read("src", "components", "ds", ...contract.path.split("/"));
    const absent = contract.markers.filter((marker) => !source.includes(marker));
    if (absent.length > 0) missing[name] = absent;
  }

  assert.deepEqual(missing, {});
});
