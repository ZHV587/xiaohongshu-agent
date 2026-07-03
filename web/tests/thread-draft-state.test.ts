import assert from "node:assert/strict";
import test from "node:test";

import {
  buildDraftAutosaveKey,
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
