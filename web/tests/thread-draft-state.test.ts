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

test("parseAiDraft extracts short first line as title and keeps full content", () => {
  const draft = parseAiDraft("# ✨ 周末轻露营清单\n正文第一段\n正文第二段");

  assert.deepEqual(draft, {
    title: "周末轻露营清单",
    content: "# ✨ 周末轻露营清单\n正文第一段\n正文第二段",
  });
});

test("parseAiDraft falls back when first line is too long", () => {
  const draft = parseAiDraft(
    "这是一行超过四十个字符的标题候选它不应该被塞进手机卡片标题字段里还要继续加长避免误判\n正文",
  );

  assert.deepEqual(draft, {
    title: "小红书爆款文案",
    content:
      "这是一行超过四十个字符的标题候选它不应该被塞进手机卡片标题字段里还要继续加长避免误判\n正文",
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
