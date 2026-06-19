import assert from "node:assert/strict";
import test from "node:test";

import { parseXhsBlocks } from "./xhs-blocks";

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
