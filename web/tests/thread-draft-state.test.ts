import assert from "node:assert/strict";
import test from "node:test";

import type { Message } from "@langchain/langgraph-sdk";
import {
  buildDraftAutosaveKey,
  latestDraftFromMessages,
  parseAiDraft,
  readDraftSnapshot,
  shouldDirtyDraft,
} from "../src/components/thread/useThreadDraftState";

test("buildDraftAutosaveKey scopes drafts by thread and new conversation", () => {
  assert.equal(buildDraftAutosaveKey(null), "xhs_autosave_draft_new");
  assert.equal(
    buildDraftAutosaveKey("thread-1"),
    "xhs_autosave_draft_thread-1",
  );
});

test("parseAiDraft returns null for plain prose without a structured copy block", () => {
  // 纯大白话(非结构化成品块)不是草稿源。此前的"纯文本兜底"会把它当草稿 → 采纳确认语/
  // 意图问句/选题引导语被写进编辑器正文,并让 status 停在 draft(不显示生成中)、chooseTopic
  // 误判已有 copy 而早返回不再生成(点选题卡"没反应")。现在一律返回 null,不覆盖既有草稿。
  assert.equal(parseAiDraft("# ✨ 周末轻露营清单\n正文第一段\n正文第二段"), null);
});

test("parseAiDraft returns null for the adopt acknowledgment prose (the real bug)", () => {
  // 用户实测触发的确切文案:采纳后 agent 的确认语,不含 xhs_copy → 绝不能当草稿。
  assert.equal(parseAiDraft("已收录 4 条入库。现在基于这批 + 本地相关内容检索取证出选题。"), null);
});

test("parseAiDraft parses an xhs_imitation block as a draft (仿写成品也是草稿源)", () => {
  const draft = parseAiDraft(
    [
      "两版仿写好了,选一版定稿。",
      "```xhs_imitation",
      JSON.stringify({
        reference_resource_id: "res-1",
        teardown: { angle: "避坑", painpoint: "踩雷", hook_mechanism: "数字", structure: "清单" },
        versions: [{ label: "A", title: "我的仿写标题", body: "我的仿写正文第一段。\n\n第二段。" }],
      }),
      "```",
    ].join("\n"),
  );
  assert.deepEqual(draft, {
    title: "我的仿写标题",
    content: "我的仿写正文第一段。\n\n第二段。",
  });
});

test("parseAiDraft prefers xhs_copy body over machine-readable planning blocks", () => {
  const draft = parseAiDraft(
    [
      "```xhs_topics",
      JSON.stringify({ topics: [{ title: "机器选题块" }] }),
      "```",
      "```xhs_copy",
      JSON.stringify({
        versions: [
          {
            title: "第一次露营别乱买",
            body: "第一次露营真的别一上来就买一堆。\n\n先把睡眠、照明、收纳、防潮这几件事解决。",
          },
        ],
      }),
      "```",
      "已基于数据底座生成选题与草稿。",
    ].join("\n"),
  );

  assert.deepEqual(draft, {
    title: "第一次露营别乱买",
    content:
      "第一次露营真的别一上来就买一堆。\n\n先把睡眠、照明、收纳、防潮这几件事解决。",
  });
});

test("parseAiDraft returns null for topics-only messages (not a draft source)", () => {
  const topicsOnly = [
    "我按相关素材整理了几个方向，点卡片进入创作。",
    "```xhs_topics",
    JSON.stringify({ topics: [{ title: "选题一" }, { title: "选题二" }] }),
    "```",
  ].join("\n");
  assert.equal(parseAiDraft(topicsOnly), null);
  assert.equal(parseAiDraft(""), null);
});

const aiMsg = (content: unknown): Message =>
  ({ id: Math.random().toString(), type: "ai", content } as unknown as Message);
const toolMsg = (): Message =>
  ({ id: "t", type: "tool", tool_call_id: "c1", content: "ok" } as unknown as Message);
const humanMsg = (text: string): Message =>
  ({ id: "h", type: "human", content: text } as unknown as Message);

test("latestDraftFromMessages scans backwards past trailing tool/human messages", () => {
  // 草稿那条 AI 消息后面跟着 tool 消息和 human 消息——旧实现只看末尾会解析不到草稿。
  const copy = [
    "```xhs_copy",
    JSON.stringify({ versions: [{ title: "露营别乱买", body: "正文：先解决睡眠照明收纳。" }] }),
    "```",
  ].join("\n");
  const messages = [
    humanMsg("写第 1 个选题"),
    aiMsg(copy),
    toolMsg(),
    humanMsg("配个标签"),
  ];
  assert.deepEqual(latestDraftFromMessages(messages), {
    title: "露营别乱买",
    content: "正文：先解决睡眠照明收纳。",
  });
});

test("latestDraftFromMessages handles Anthropic content-block array form", () => {
  const copy = [
    "```xhs_copy",
    JSON.stringify({ title: "标题X", body: "正文X" }),
    "```",
  ].join("\n");
  const messages = [aiMsg([{ type: "text", text: copy }])];
  assert.deepEqual(latestDraftFromMessages(messages), { title: "标题X", content: "正文X" });
});

test("latestDraftFromMessages returns null when no message carries a draft", () => {
  const messages = [humanMsg("你好"), aiMsg("```xhs_topics\n{\"topics\":[]}\n```"), toolMsg()];
  assert.equal(latestDraftFromMessages(messages), null);
});

test("readDraftSnapshot tolerates missing and malformed autosave payloads", () => {
  assert.deepEqual(readDraftSnapshot(null), { title: "", content: "" });
  assert.deepEqual(readDraftSnapshot("{bad json"), { title: "", content: "" });
  assert.deepEqual(
    readDraftSnapshot(JSON.stringify({ title: "标题", content: "正文" })),
    { title: "标题", content: "正文" },
  );
});

test("shouldDirtyDraft only marks dirty after a saved baseline exists", () => {
  assert.equal(
    shouldDirtyDraft({ title: "A", content: "B" }, { title: "", content: "" }),
    false,
  );
  assert.equal(
    shouldDirtyDraft(
      { title: "A", content: "B" },
      { title: "A", content: "B" },
    ),
    false,
  );
  assert.equal(
    shouldDirtyDraft(
      { title: "A2", content: "B" },
      { title: "A", content: "B" },
    ),
    true,
  );
});
