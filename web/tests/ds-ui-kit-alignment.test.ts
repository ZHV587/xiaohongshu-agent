import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const webRoot = process.cwd();

function read(...parts: string[]): string {
  return readFileSync(join(webRoot, ...parts), "utf8");
}

function assertIncludes(source: string, needles: string[], label: string) {
  const missing = needles.filter((needle) => !source.includes(needle));
  assert.deepEqual(missing, [], `${label} is missing expected DS UI-kit markers`);
}

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

test("studio production shell uses the fixed final screen composition", () => {
  const shell = read("src", "components", "studio", "StudioShell.tsx");
  assertIncludes(shell, ["StudioTopBar", "<CreationScreen />", "<DeepCreation />", "<Operations />", "EvidencePanel"], "StudioShell");
  assert.doesNotMatch(shell, /Tweaks|方案探索|rightLayout|deepForm|opsHosting|useState/);
});

test("creation screen uses the fixed final right panel", () => {
  const creation = read("src", "components", "studio", "CreationScreen.tsx");
  assertIncludes(
    creation,
    [
      "SelectedTopicBar",
      "DraftSnapshot",
      "TopicRail",
      "EvidencePanel",
      "TrendingTopics",
      "ThinkingAura",
    ],
    "CreationScreen",
  );
  assert.doesNotMatch(creation, /RightLayout|rightLayout|orientation="horizontal"|仅创作栏|左右分栏/);
});

test("deep creation uses the fixed final immersive editor", () => {
  const deep = read("src", "components", "studio", "DeepCreation.tsx");
  const deepEditor = read("src", "components", "studio", "DeepEditor.tsx");
  const source = `${deep}\n${deepEditor}`;
  assertIncludes(
    source,
    [
      "Version",
      "话题标签",
      "文案体检",
      "DeepEditor",
    ],
    "DeepCreation",
  );
  assert.doesNotMatch(deep, /DeepForm|form =|DeepFlow|DeepWorkspace|StepCards|分步流程|多栏工作台/);
});

test("operations screen uses the fixed final page hosting", () => {
  const operations = read("src", "components", "studio", "Operations.tsx");
  assertIncludes(
    operations,
    [
      "OpsPage",
      "AccountRail",
      "DashboardBody",
      "CalendarSection",
      "LibrarySection",
      "BackfillSection",
      "PipelineSection",
      "StateNote",
    ],
    "Operations",
  );
  assert.doesNotMatch(operations, /OpsHosting|hosting|OpsInline|OpsHybrid|会话内|同屏融合|发起运营动作/);
});

test("workbench starting point has a production entry and DS interaction affordances", () => {
  const appShell = read("src", "components", "AppShell.tsx");
  assertIncludes(appShell, ["WorkbenchShell", "mode"], "AppShell");

  const workbenchPath = join(webRoot, "src", "components", "workbench", "WorkbenchShell.tsx");
  assert.ok(existsSync(workbenchPath), "WorkbenchShell.tsx must exist");
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "CommandPalette",
      "RightCanvas",
      "FeishuSync",
      "Ctrl+P",
      "rotateY(180deg)",
      "transformStyle",
      "var(--dur-slow)",
      "var(--dur-fly)",
      "xhs-fly-to-sync",
      "setPaletteOpen",
    ],
    "WorkbenchShell",
  );
});

test("workbench right canvas carries the DS bottom copy bar", () => {
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "RightCanvasBottomBar",
      "CopyButton",
      "文案长度",
      "1000 字",
      "一键复制纯文案",
      "已复制",
      "navigator.clipboard.writeText",
    ],
    "WorkbenchShell right canvas bottom bar",
  );
});

test("workbench top bar mirrors DS brand and reauth prompt", () => {
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "小红书文案助手",
      "v1.2 工作台",
      "飞书 CLI 状态：Ready (bot)",
      "User 身份已过期，点此扫码重连",
      "setScanned(false)",
    ],
    "Workbench TopBar",
  );
});

test("workbench right canvas focuses on Feishu sync without mobile preview tabs", () => {
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "🔗 飞书同步协作",
      "RightCanvasBottomBar",
      "文案长度",
      "一键复制纯文案",
      "navigator.clipboard.writeText",
    ],
    "Workbench RightCanvas header",
  );
  assert.ok(!workbench.includes("📱 小红书手机预览"), "Workbench must not expose the mobile preview tab");
  assert.ok(!workbench.includes("详情视窗"), "Workbench must not expose the detail preview toggle");
  assert.ok(!workbench.includes("瀑布流卡片"), "Workbench must not expose the feed preview toggle");
});

test("workbench feishu sync mirrors the DS sync cards and flip auth", () => {
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "同步到飞书多维表格",
      "APP Token: bascnu",
      "绑定选题记录",
      "飞书文档列映射",
      "字数检测",
      "立即同步至飞书多维表格",
      "群发通知与协同审核",
      "选择接收通知的飞书群聊",
      "一键发送通知至飞书群聊",
      "飞书个人身份已过期",
      "飞书个人身份重连成功",
      "gridTemplateColumns: \"repeat(3,1fr)\"",
      "setSyncing",
    ],
    "Workbench FeishuSync",
  );
});

test("workbench command palette mirrors the DS searchable palette", () => {
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "Input",
      "输入命令或搜索动作",
      "ESC",
      "无匹配命令",
      "setQuery",
      "commands.filter",
    ],
    "Workbench CommandPalette",
  );
});

test("workbench conversation response mirrors DS ChatPane states", () => {
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "ChatPane",
      "ThinkingAura",
      "item.kind === \"thinking\"",
      "item.kind === \"error\"",
      "正在针对",
      "飞书同步协作",
      "✅ 已完成",
      "润色工具箱",
      "图片或 PDF",
      "Ctrl+P",
      "生成",
      "TopicCard",
    ],
    "Workbench ChatPane response states",
  );
});

test("workbench sidebar mirrors DS Sidebar with real recents wiring", () => {
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  assertIncludes(
    workbench,
    [
      "WorkbenchSidebar",
      "开启全新灵感对话",
      "最近创作",
      "按 Ctrl+J 隐藏",
      "useThreadsOptional",
      "useThreadOptional",
      "setThreadId",
      "threadTitle",
      "borderLeft",
      "退出登录",
      "log-out",
      "logout",
      "管理员配置",
      "AdminConfigPanel",
    ],
    "Workbench Sidebar",
  );
  assert.ok(!workbench.includes("<Recents"), "Workbench must not use the Studio Recents sidebar directly");
});

test("production desktop removes mobile preview surfaces", () => {
  const productionFiles = [
    read("src", "components", "workbench", "WorkbenchShell.tsx"),
    read("src", "components", "studio", "CreationScreen.tsx"),
    read("src", "components", "studio", "Composer.tsx"),
    read("src", "components", "studio", "DeepCreation.tsx"),
  ].join("\n");

  for (const marker of [
    "手机预览",
    "PhonePreview",
    "PhoneFrame",
    "NoteCard",
    "详情视窗",
    "瀑布流卡片",
    "笔记详情",
  ]) {
    assert.ok(!productionFiles.includes(marker), `production desktop must not include mobile preview marker: ${marker}`);
  }
});

test("studio shell and recents mirror DS shell and recents", () => {
  const shell = read("src", "components", "studio", "Shell.tsx");
  assertIncludes(
    shell,
    [
      "StudioTopBar",
      "工作区切换",
      "开启全新灵感对话",
      "历史会话",
      "管理员配置",
      "panel-left-close",
      "panel-left-open",
      "borderLeft",
    ],
    "Studio Shell and Recents",
  );
});

test("studio composer mirrors DS composer panels and actions", () => {
  const composer = read("src", "components", "studio", "Composer.tsx");
  const deepEditor = read("src", "components", "studio", "DeepEditor.tsx");
  const source = `${composer}\n${deepEditor}`;
  assertIncludes(
    source,
    [
      "CopyDoctor",
      "ScheduleBar",
      "VisualStudio",
      "RiskPanel",
      "EmptyComposer",
      "quickEmoji",
      "润色",
      "瘦身",
      "配标签",
      "同步飞书",
      "定稿并排期",
      "文案体检",
    ],
    "Studio Composer",
  );
  assert.ok(!composer.includes("已随未挂载路径删除"), "Composer must not document DS composer panels as removed");
});

test("desktop shells expose accessible landmarks and keyboard focus affordances", () => {
  const globals = read("src", "app", "globals.css");
  const studioShell = read("src", "components", "studio", "StudioShell.tsx");
  const shell = read("src", "components", "studio", "Shell.tsx");
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");

  assert.ok(studioShell.includes("<h1"), "StudioShell must expose a real h1 for the desktop app landmark");
  assert.ok(workbench.includes("<h1"), "WorkbenchShell must expose a real h1 for the desktop app landmark");
  assert.match(shell, /<nav\s+aria-label="工作区切换"/, "Studio top nav must have an accessible label");
  assert.ok(globals.includes(".sr-only"), "globals.css must provide a hidden-but-readable text utility");
  assert.ok(globals.includes(":focus-visible"), "globals.css must keep keyboard focus visible on raw controls");
  assert.doesNotMatch(studioShell, /Tweaks|方案探索/, "StudioShell must not expose prototype exploration controls");
});

test("production desktop does not ship prototype exploration controls", () => {
  const srcFiles = walk(join(webRoot, "src"))
    .filter((path) => /\.(ts|tsx)$/.test(path))
    .map((path) => readFileSync(path, "utf8"))
    .join("\n");

  for (const marker of [
    "TweaksPanel",
    "TweakRadio",
    "TweakSection",
    "TweakSelect",
    "TweakToggle",
    "TweakNumber",
    "TweakColor",
    "Tweaks · 方案探索",
    "方案探索",
    "探索性选题",
    "__activate_edit_mode",
    "__edit_mode_available",
    "rightLayout",
    "deepForm",
    "opsHosting",
    "OpsInline",
    "OpsHybrid",
    "DeepFlow",
    "DeepWorkspace",
  ]) {
    assert.ok(!srcFiles.includes(marker), `production desktop must not include prototype exploration marker: ${marker}`);
  }
});

test("brand guidelines and motion are represented in production globals", () => {
  const globals = read("src", "app", "globals.css");
  assertIncludes(
    globals,
    [
      "--coral-brand",
      "--shadow-coral",
      "--radius-phone",
      "--rail-sidebar",
      "--rail-canvas",
      "--topbar-height",
      ".dark",
      "secIn",
      "toastIn",
      "slide-in-right",
      "pop-in",
      "lift",
      "custom-scrollbar",
    ],
    "Brand guidelines and motion",
  );
});
