import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import { parseXhsBlocks, type RichTopic } from "../src/lib/xhs-blocks";

// Feature: studio-data-integration, Property 5
// Property 5: 数据不足明示
// Validates: Requirements 3.1, 3.7 (studio-data-integration 16.2)
//
// 对任意 evidence_mode = "insufficient_relevance"、evidence 为空数组 []、gaps 非空的
// 富选题载荷，解析后应满足：
//   - topic.evidence_mode === "insufficient_relevance"（检索模式如实保留）；
//   - topic.evidence 为空数组（不产出任何弱相关/虚构证据条目）；
//   - topic.gaps 保留为可渲染的非空字符串。
//
// 关键对齐 parseRichTopic：当 source.evidence 为「数组」（含空数组）时，
// topic.evidence = parseRichEvidence(source.evidence)；仅当该键缺失/非数组时才回退顶层证据。
// 因此本测试在顶层放入「非空」共享证据 —— 若解析器错误地对空 evidence 走了回退，
// topic.evidence 将变为非空，从而被断言捕获。这保证「数据不足时不掺入证据」为真属性而非巧合。

// 所有字符串剥离反引号，避免污染 ```xhs_topics``` 围栏匹配（否则会提前闭合围栏、
// 使 JSON 截断走 pending 降级路径而非 tryParse 正式路径）。
const stripBackticks = (s: string): string => s.replace(/`/g, "");

const safeString = fc.string({ maxLength: 30 }).map(stripBackticks);

// 非空且可渲染的字符串：剥离反引号后若为空白，回退为确定的非空默认值。
const nonEmptyRenderable = (fallback: string) =>
  fc
    .string({ minLength: 1, maxLength: 60 })
    .map(stripBackticks)
    .map((s) => (s.trim().length > 0 ? s : fallback));

// gaps：非空可渲染字符串（数据不足时向用户明示的缺口说明）。
const gapsArb = nonEmptyRenderable("相关语料不足，暂无法给出高置信证据");

// 数据不足的富选题：evidence_mode 固定 insufficient_relevance、evidence 为空数组、gaps 非空。
const insufficientTopicArb = fc.record({
  title: safeString,
  angle: safeString,
  kw: safeString,
  gaps: gapsArb,
});

const topicsArrayArb = fc.array(insufficientTopicArb, { minLength: 1, maxLength: 4 });

// 顶层「非空」共享证据：用于探测解析器是否对空 evidence 误走回退（若误回退则 topic.evidence 非空）。
const topLevelEvidenceArb = fc.array(
  fc.record({
    resource_id: nonEmptyRenderable("res-x"),
    title: nonEmptyRenderable("共享证据标题"),
    summary: nonEmptyRenderable("共享证据摘要"),
  }),
  { minLength: 1, maxLength: 3 },
);

function buildTopicsContent(
  topics: Array<{ title: string; angle: string; kw: string; gaps: string }>,
  topLevelEvidence: unknown[],
): string {
  const payload = {
    intro: "候选选题（数据不足）",
    topics: topics.map((t) => ({
      title: t.title,
      angle: t.angle,
      kw: t.kw,
      evidence_mode: "insufficient_relevance",
      evidence: [] as unknown[], // 空证据数组
      gaps: t.gaps,
    })),
    evidence: topLevelEvidence, // 顶层非空共享证据
  };
  // 三反引号围栏 + 合法 JSON（JSON.stringify 保证合法），走 tryParse 正式解析路径。
  return "```xhs_topics\n" + JSON.stringify(payload) + "\n```";
}

test("Property 5: 数据不足明示（证据为空、gaps 保留、检索模式如实）", () => {
  fc.assert(
    fc.property(topicsArrayArb, topLevelEvidenceArb, (topics, topLevelEvidence) => {
      const content = buildTopicsContent(topics, topLevelEvidence);
      const segments = parseXhsBlocks(content);

      const topicsSeg = segments.find((s) => s.kind === "topics");
      assert.ok(topicsSeg && topicsSeg.kind === "topics", "应解析出 topics 片段");
      assert.equal(topicsSeg.isPending, undefined, "合法 JSON 应走正式解析路径而非 pending 降级");

      // 选题数守恒，且每个选题均为富选题对象。
      assert.equal(topicsSeg.data.topics.length, topics.length, "选题数量应守恒");

      for (let i = 0; i < topicsSeg.data.topics.length; i += 1) {
        const parsed: string | RichTopic = topicsSeg.data.topics[i];
        assert.equal(typeof parsed, "object", "数据不足选题应解析为富选题对象");
        const topic = parsed as RichTopic;

        // (1) 检索模式如实保留为 insufficient_relevance。
        assert.equal(
          topic.evidence_mode,
          "insufficient_relevance",
          "evidence_mode 应保留为 insufficient_relevance",
        );

        // (2) 证据为空数组：不产出任何弱相关/虚构证据，且不回退顶层非空共享证据。
        assert.ok(Array.isArray(topic.evidence), "evidence 应为数组");
        assert.equal(
          topic.evidence?.length,
          0,
          "数据不足时证据应为空，绝不掺入弱相关或回退顶层证据",
        );

        // (3) gaps 保留为可渲染的非空字符串。
        assert.equal(typeof topic.gaps, "string", "gaps 应保留为字符串");
        assert.ok((topic.gaps ?? "").trim().length > 0, "gaps 应为可渲染的非空文本");
        assert.equal(topic.gaps, topics[i].gaps, "gaps 内容应与输入一致，无损保留");
      }
    }),
    { numRuns: 200 },
  );
});
