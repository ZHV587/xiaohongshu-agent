import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import test from "node:test";

const webRoot = process.cwd();
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

// 设计基准:总设计(bug/设计稿/assets/tokens.css)的入库拷贝。此前测试引用从未入库的
// 「小红书文案助手 Design System/」目录,在服务器/CI 上 ENOENT —— 防回归形同虚设。
// 基准变更时同步更新该 fixture(与总设计保持一字不差)。
const designTokensCss = readFileSync(join(webRoot, "tests", "fixtures", "design-tokens.css"), "utf8");

test("production globals define every design-system token name", () => {
  const globals = read("src", "app", "globals.css");
  const tokenNames = new Set<string>();
  for (const match of designTokensCss.matchAll(/--[a-zA-Z0-9-]+(?=\s*:)/g)) {
    tokenNames.add(match[0]);
  }

  const missing = [...tokenNames].filter((token) => !globals.includes(token)).sort();
  assert.deepEqual(missing, []);
});

test("production globals keep design token values equivalent to the design baseline", () => {
  const globals = read("src", "app", "globals.css");
  // 值级防回归:设计基准 :root 的每个 token,在 globals 中解析 var() 别名链后必须取值等价。
  // (globals 允许 --primary-hover: var(--coral-600) 这类间接引用,只要最终值与基准一致。)
  const declsOf = (css: string): Map<string, string> => {
    const map = new Map<string, string>();
    for (const decl of css.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) {
      if (!map.has(decl[1])) map.set(decl[1], decl[2]);
    }
    return map;
  };
  const resolveVars = (value: string, map: Map<string, string>, depth = 0): string => {
    if (depth > 8) return value;
    return value.replace(/var\((--[a-zA-Z0-9-]+)\)/g, (whole, name: string) => {
      const target = map.get(name);
      return target == null ? whole : resolveVars(target, map, depth + 1);
    });
  };
  const normalize = (value: string): string =>
    value.replace(/\s+/g, "").replace(/(^|[^0-9])0\./g, "$1.").toLowerCase();

  const designMap = declsOf(designTokensCss);
  const globalsMap = declsOf(globals);
  const rootBlock = /:root\s*\{([\s\S]*?)\}/.exec(designTokensCss)?.[1] ?? "";
  const mismatched: string[] = [];
  for (const decl of rootBlock.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g)) {
    const [, name, designValue] = decl;
    const globalsValue = globalsMap.get(name);
    if (globalsValue == null) {
      mismatched.push(`${name} (missing)`);
      continue;
    }
    const designResolved = normalize(resolveVars(designValue, designMap));
    const globalsResolved = normalize(resolveVars(globalsValue, globalsMap));
    if (designResolved !== globalsResolved) {
      mismatched.push(`${name}: 设计=${designResolved} 实现=${globalsResolved}`);
    }
  }
  assert.deepEqual(mismatched, []);
});

test("design utility classes referenced by production components exist in globals", () => {
  const globals = read("src", "app", "globals.css");
  // 组件里引用的设计动效类必须有真实定义,否则动画静默失效(.pane-in/.stagger 曾悬空)。
  const requiredClasses = [".fade-up", ".pane-in", ".stagger > *", ".cs::-webkit-scrollbar"];
  const missing = requiredClasses.filter((cls) => !globals.includes(cls));
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

test("each DS library component has a production usage outside the DS library", () => {
  // 组件清单直接从 DS barrel(src/components/ds/index.ts)派生 —— 库本身就是权威来源,
  // 不再依赖已删除原型目录里的 _ds_manifest.json。
  const barrel = read("src", "components", "ds", "index.ts");
  const componentNames = new Set<string>();
  for (const match of barrel.matchAll(/export\s*\{\s*([A-Za-z0-9_,\s]+?)(?:,\s*type[^}]*)?\}/g)) {
    for (const piece of match[1].split(",")) {
      const name = piece.trim();
      if (/^[A-Z][A-Za-z0-9]*$/.test(name)) componentNames.add(name);
    }
  }
  assert.ok(componentNames.size >= 10, `DS barrel 解析出的组件数异常: ${componentNames.size}`);

  const intentionallyUnused = new Set(["NoteCard", "PhoneFrame"]);
  const productionFiles = walk(srcRoot)
    .filter((path) => /\.(ts|tsx)$/.test(path))
    .filter((path) => !relative(srcRoot, path).replaceAll("\\", "/").startsWith("components/ds/"));
  const productionSource = productionFiles.map((path) => readFileSync(path, "utf8")).join("\n");

  const unused = [...componentNames]
    .filter((name) => !intentionallyUnused.has(name))
    .filter((name) => !new RegExp(`<${name}\\b`).test(productionSource))
    .sort();

  assert.deepEqual(unused, []);
});

test("design-system desktop starting points have production parity tests", () => {
  const uiTests = read("tests", "ds-ui-kit-alignment.test.ts");
  const requiredTestNames = [
    "studio production shell uses the fixed final screen composition",
    "creation screen right panel is the reference-material workbench",
    "v2 in-place editor is single-column with a top toolbar and right drawers",
    "operations screen uses the fixed final page hosting",
    "workbench starting point has a production entry and DS interaction affordances",
    "workbench right canvas carries the DS bottom copy bar",
    "workbench command palette mirrors the DS searchable palette",
    "workbench feishu sync mirrors the DS sync cards and flip auth",
    "workbench right canvas focuses on Feishu sync without mobile preview tabs",
    "production desktop removes mobile preview surfaces",
    "production desktop does not ship prototype exploration controls",
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
