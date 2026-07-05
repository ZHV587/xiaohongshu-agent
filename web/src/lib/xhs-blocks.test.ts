import assert from "node:assert/strict";
import test from "node:test";

import { parseXhsBlocks, stripThinkingTags } from "./xhs-blocks";

test("stripThinkingTags removes paired <thinking> and <think> blocks", () => {
  assert.equal(stripThinkingTags("<thinking>reason</thinking>正文"), "正文");
  assert.equal(stripThinkingTags("<think>abc</think>hi"), "hi");
  // 大小写不敏感 + 跨行
  assert.equal(stripThinkingTags("<Thinking>\nmulti\nline\n</Thinking>结果"), "结果");
});

test("stripThinkingTags truncates an unclosed opening tag (streaming mid-flush)", () => {
  assert.equal(stripThinkingTags("正文<thinking>还没写完的思考"), "正文");
});

test("stripThinkingTags leaves normal text untouched", () => {
  assert.equal(stripThinkingTags("这是普通正文,没有标签"), "这是普通正文,没有标签");
  assert.equal(stripThinkingTags(""), "");
});

test("parseXhsBlocks strips leaked <thinking> from text segments", () => {
  const segs = parseXhsBlocks("<thinking>internal</thinking>给你的文案在下面");
  const text = segs.filter((s) => s.kind === "text").map((s) => (s as { text: string }).text).join("");
  assert.ok(!text.includes("<thinking>"));
  assert.ok(!text.includes("internal"));
  assert.ok(text.includes("给你的文案在下面"));
});

test("preserves valid topic evidence", () => {
  const [segment] = parseXhsBlocks(`\`\`\`xhs_topics
{"intro":"方向建议","topics":["轻量露营"],"evidence":[{"resource_id":"note-1","title":"高互动露营笔记","summary":"轻量装备清单更易收藏","source_updated_at":"2026-05-01T08:00:00Z","indexed_at":"2026-06-18T08:00:00Z"}]}
\`\`\``);

  assert.equal(segment.kind, "topics");
  if (segment.kind !== "topics") return;
  assert.deepEqual(segment.data.evidence, [
    {
      resource_id: "note-1",
      title: "高互动露营笔记",
      summary: "轻量装备清单更易收藏",
      source_updated_at: "2026-05-01T08:00:00Z",
      indexed_at: "2026-06-18T08:00:00Z",
    },
  ]);
});

test("preserves valid copy evidence and filters malformed entries", () => {
  const [segment] = parseXhsBlocks(`\`\`\`xhs_copy
{"title":"周末轻装出发","body":"正文","tags":["#露营"],"evidence":[{"resource_id":"note-2","title":"露营标题样本","summary":"数字和场景组合表现突出"},{"resource_id":"","title":"无效来源","summary":"缺少资源标识"},{"resource_id":"note-3","title":"无效来源","summary":42}]}
\`\`\``);

  assert.equal(segment.kind, "copy");
  if (segment.kind !== "copy") return;
  assert.deepEqual(segment.data.evidence, [
    {
      resource_id: "note-2",
      title: "露营标题样本",
      summary: "数字和场景组合表现突出",
    },
  ]);
});

test("keeps payloads without evidence backward compatible", () => {
  const [topics, copy] = parseXhsBlocks(`\`\`\`xhs_topics
{"topics":["旧选题"]}
\`\`\`
\`\`\`xhs_copy
{"title":"旧标题","body":"旧正文","tags":[]}
\`\`\``).filter((segment) => segment.kind !== "text");

  assert.equal(topics.kind, "topics");
  assert.equal(copy.kind, "copy");
  if (topics.kind !== "topics" || copy.kind !== "copy") return;
  assert.deepEqual(topics.data.evidence, []);
  assert.deepEqual(copy.data.evidence, []);
});

test("discards malformed evidence timestamps without dropping the source", () => {
  const [segment] = parseXhsBlocks(`\`\`\`xhs_copy
{"title":"标题","body":"正文","tags":[],"evidence":[{"resource_id":"note-4","title":"来源","summary":"摘要","source_updated_at":"not-a-date","indexed_at":""}]}
\`\`\``);

  assert.equal(segment.kind, "copy");
  if (segment.kind !== "copy") return;
  assert.deepEqual(segment.data.evidence, [
    {resource_id: "note-4", title: "来源", summary: "摘要"},
  ]);
});

test("parses valid xhs_panel segments", () => {
  const [segment] = parseXhsBlocks(`\`\`\`xhs_panel
{
  "actions": [
    { "label": "✍️ 确认为该标题写开头", "text": "我选这个标题，请帮我写开头设计。" },
    { "label": "🔄 换一批标题", "text": "这几个不够亮眼，换一批新的标题。" }
  ]
}
\`\`\``);

  assert.equal(segment.kind, "panel");
  if (segment.kind !== "panel") return;
  assert.deepEqual(segment.data, {
    actions: [
      { label: "✍️ 确认为该标题写开头", text: "我选这个标题，请帮我写开头设计。" },
      { label: "🔄 换一批标题", text: "这几个不够亮眼，换一批新的标题。" },
    ],
  });
});

test("parses partial xhs_panel segments gracefully", () => {
  const [segment] = parseXhsBlocks(`\`\`\`xhs_panel
{
  "actions": [
    { "label": "✍️ 确认为该标题写开头", "text": "我选这个标题，请帮我写开头设计。" },
    { "label": "🔄 换一批标题", "text": "这几个不够
\`\``); // note the unclosed JSON and incomplete actions array

  assert.equal(segment.kind, "panel");
  if (segment.kind !== "panel") return;
  assert.deepEqual(segment.data, {
    actions: [
      { label: "✍️ 确认为该标题写开头", text: "我选这个标题，请帮我写开头设计。" },
    ],
  });
});

test("parses xhs_topics when JSON is on the same line as the fence tag (Claude /v1/messages 习惯)", () => {
  // 回归:Anthropic 原生 /v1/messages 常把 JSON 紧跟在 ```xhs_topics 标签同一行(无换行)。
  // FENCE_RE 若强制标签后换行,会整块漏解析 → 选题卡不渲染。此用例锁住同行写法可解析。
  const segments = parseXhsBlocks(
    '前言文字 ```xhs_topics {"intro":"久坐健康","topics":[{"title":"工位5分钟代谢重启","hotRate":88,"angle":"碎片化"}]} ``` 收尾文字',
  );
  const topics = segments.find((s) => s.kind === "topics");
  assert.ok(topics, "同行 fence 应被解析为 topics 段");
  if (!topics || topics.kind !== "topics") return;
  assert.equal(topics.data.topics.length, 1);
  const first = topics.data.topics[0];
  assert.equal(typeof first === "string" ? first : first.title, "工位5分钟代谢重启");
});

test("parses xhs_topics when JSON string values contain triple backticks", () => {
  const [segment] = parseXhsBlocks(`\`\`\`xhs_topics
{"topics":["围栏字符"],"evidence":[{"resource_id":"note-5","title":"标题含 \`\`\` 字符","summary":"摘要也保留","source_updated_at":"2026-05-01T08:00:00Z","indexed_at":"2026-06-18T08:00:00Z"}]}
\`\`\``);

  assert.equal(segment.kind, "topics");
  if (segment.kind !== "topics") return;
  assert.deepEqual(segment.data.evidence, [
    {
      resource_id: "note-5",
      title: "标题含 ``` 字符",
      summary: "摘要也保留",
      source_updated_at: "2026-05-01T08:00:00Z",
      indexed_at: "2026-06-18T08:00:00Z",
    },
  ]);
});

test("xhs_imitation block is stripped from prose (no JSON leak)", () => {
  const content = [
    "两版仿写好了,选一版定稿。",
    "```xhs_imitation",
    '{ "reference_resource_id": "res-1", "reference_title": "范本", "teardown": { "angle": "避坑", "painpoint": "踩雷", "hook_mechanism": "数字", "structure": "清单" }, "title": "我的标题", "body": "我的正文", "tags": ["#a"], "versions": [{ "label": "A", "title": "我的标题", "body": "我的正文", "tags": ["#a"], "cover": "", "note": "" }] }',
    "```",
  ].join("\n");
  const segs = parseXhsBlocks(content);
  const text = segs.filter((s) => s.kind === "text").map((s) => (s as { text: string }).text).join("");
  assert.ok(text.includes("两版仿写好了"));
  assert.ok(!text.includes("reference_resource_id"));
  assert.ok(!text.includes("teardown"));
  assert.ok(segs.some((s) => s.kind === "copy"));
});

test("parses xhs_titles candidates and strips from prose", () => {
  const content = [
    "按「数字清单」出的候选:",
    "```xhs_titles",
    '{ "formula": "数字清单", "candidates": ["露营必买 6 件", "5 个露营坑"] }',
    "```",
  ].join("\n");
  const segs = parseXhsBlocks(content);
  const titles = segs.find((s) => s.kind === "titles");
  assert.ok(titles && titles.kind === "titles");
  assert.equal(titles.data.formula, "数字清单");
  assert.deepEqual(titles.data.candidates, ["露营必买 6 件", "5 个露营坑"]);
  const text = segs.filter((s) => s.kind === "text").map((s) => (s as { text: string }).text).join("");
  assert.ok(!text.includes("candidates"));
});
