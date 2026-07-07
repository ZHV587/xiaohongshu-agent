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
  // v2:深创并入创作屏右栏就地渲染,独立 DeepCreation 整屏已移除,shell 只挂 create/ops 两区。
  assertIncludes(shell, ["StudioTopBar", "<CreationScreen />", "<Operations />", "EvidencePanel"], "StudioShell");
  assert.doesNotMatch(shell, /Tweaks|方案探索|rightLayout|deepForm|opsHosting|useState/);
  assert.doesNotMatch(shell, /DeepCreation|section === "deep"|"deep"/);
});

test("creation screen right panel is the reference-material workbench", () => {
  // 需求 §3:右边栏专职参考素材笔记工作台(线上+本地混排),选题卡移进对话气泡。
  // 撤掉原来的选题卡右栏(TopicRail),改 RefMaterialRail + MaterialCard;
  // 三个平行动作:批量收录(勾选+底部按钮)、单张仿写(卡上按钮);统一详情弹层 DetailModal。
  const creation = read("src", "components", "studio", "CreationScreen.tsx");
  assertIncludes(
    creation,
    [
      "RefMaterialRail",
      "MaterialCard",
      "参考素材笔记",
      "仿写",
      "收录选中",
      "DetailModal",
      "EvidencePanel",
      "TrendingTopics",
      "ThinkingAura",
      "intent-choice",
    ],
    "CreationScreen",
  );
  // 旧的固定右栏组件应已删除(不留旧逻辑)。
  assert.doesNotMatch(creation, /TopicRail|SelectedTopicBar|function DiscoveryNotesCard/);
  assert.doesNotMatch(creation, /RightLayout|rightLayout|orientation="horizontal"|仅创作栏|左右分栏/);
});

test("v2 in-place editor is single-column with a top toolbar and right drawers", () => {
  // v2(DEV-SPEC §4.5):deep 整屏已移除,编辑器在创作屏右栏就地渲染;单列编辑区 + 顶部工具条
  // (版本/大纲/依据/文案体检/风控/标题优化,同时只开一个抽屉,按钮带实时角标)+ 底部 ScheduleBar 常驻。
  const editor = read("src", "components", "studio", "DeepEditor.tsx");
  assertIncludes(
    editor,
    [
      "ToolBtn",       // 顶部工具按钮
      "Drawer",        // 右侧抽屉容器
      "VersionsDrawerBody",
      "OutlineDrawerBody",
      "TitleToolBody", // 标题优化(抽屉,非整屏)
      "ProcessDrawerBody",
      "ScheduleBar",   // 底部定稿常驻
      "话题标签",
      "文案体检",
      "版本",
      'setTool',       // 单值工具态:同时只开一个抽屉
    ],
    "DeepEditor",
  );
  // v1 三栏 aside 与 ABCompare/TitleScreen 整屏均已删除,不留旧结构。
  assert.doesNotMatch(editor, /ABCompare|TitleScreen|DeepTopicBar|DeepStatusChip|DeepMode|质检定稿/);
  // 独立 DeepCreation 整屏文件应已删除。
  assert.ok(!existsSync(join(webRoot, "src", "components", "studio", "DeepCreation.tsx")), "DeepCreation.tsx (v1 独立深创整屏) should be deleted");
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

test("desktop chat composers send on Enter without breaking multiline or IME input", () => {
  const creation = read("src", "components", "studio", "CreationScreen.tsx");
  const workbench = read("src", "components", "workbench", "WorkbenchShell.tsx");
  const source = `${creation}\n${workbench}`;
  assertIncludes(
    source,
    [
      "handleComposerKeyDown",
      "event.key !== \"Enter\"",
      "event.shiftKey",
      "event.nativeEvent.isComposing",
      "event.preventDefault()",
      "sendDraft()",
    ],
    "Desktop chat composer keyboard behavior",
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
    read("src", "components", "studio", "DeepEditor.tsx"),
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
