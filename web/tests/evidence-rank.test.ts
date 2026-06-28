import { test } from "node:test";
import assert from "node:assert/strict";

import { lookupRankSignals } from "../src/lib/evidence-rank";

const rankItem = (id: string, score: number, rel: number) => ({
  resource_id: id,
  title: id,
  summary: "s",
  score,
  why_selected: `因为 ${id}`,
  rank_signals: { relevance: rel, freshness: 0.7, performance: 0.1 },
});

test("从检索工具结果(JSON 字符串 content)按 resource_id 取 rank 信号", () => {
  const messages = [
    { type: "human", content: "找护肤" },
    {
      type: "tool",
      name: "semantic_search_resources",
      content: JSON.stringify({ ok: true, mode: "semantic", results: [rankItem("r1", 0.88, 0.9), rankItem("r2", 0.5, 0.4)] }),
    },
  ];
  const got = lookupRankSignals(messages, "r1");
  assert.equal(got.score, 0.88);
  assert.equal(got.why_selected, "因为 r1");
  assert.deepEqual(got.rank_signals, { relevance: 0.9, freshness: 0.7, performance: 0.1 });
});

test("content 为已解析对象(非字符串)也能取", () => {
  const messages = [
    { type: "tool", name: "search_resources", content: { ok: true, results: [rankItem("r9", 0.42, 0.3)] } },
  ];
  assert.equal(lookupRankSignals(messages, "r9").score, 0.42);
});

test("多轮命中同一 resource 取最近一次", () => {
  const messages = [
    { type: "tool", name: "semantic_search_resources", content: JSON.stringify({ results: [rankItem("r1", 0.6, 0.6)] }) },
    { type: "tool", name: "semantic_search_resources", content: JSON.stringify({ results: [rankItem("r1", 0.95, 0.97)] }) },
  ];
  assert.equal(lookupRankSignals(messages, "r1").score, 0.95);
});

test("非检索工具 / 无命中 / 坏 JSON 一律返回空(看板优雅 N/A)", () => {
  const messages = [
    { type: "tool", name: "graph_expand", content: JSON.stringify({ nodes: [{ resource_id: "r1" }] }) },
    { type: "tool", name: "save_generated_topic", content: JSON.stringify({ ok: true }) },
    { type: "tool", name: "semantic_search_resources", content: "{坏 json" },
    { type: "ai", content: "正文" },
  ];
  assert.deepEqual(lookupRankSignals(messages, "r1"), {});
  assert.deepEqual(lookupRankSignals(messages, undefined), {});
  assert.deepEqual(lookupRankSignals(undefined, "r1"), {});
});
