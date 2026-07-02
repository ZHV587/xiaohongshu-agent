import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import { parseXhsBlocks } from "../src/lib/xhs-blocks";

// Feature: studio-data-integration, Property 4
// Property 4: 缺字段降级不抛错且选题数量守恒
// Validates: Requirements 3.1, 3.7 (studio-data-integration 3.3, 3.4)
//
// tryParse 的 topics.map 分支对每个数组元素恰好产出一个输出：
//   - 字符串 → 原样保留（旧格式）
//   - 对象   → parseRichTopic（缺/错字段降级为省略键，绝不抛错）
//   - 其它   → String(t) 降级
// 因此对任意混入畸形项（缺字段 / 类型错配 / null / 数字 / 布尔）的 topics 数组：
//   (a) 解析永不抛异常；
//   (b) 解析出的选题数恒等于输入 topics 数组长度（逐项 map，绝不丢弃/增补）。

// 所有字符串剥离反引号，避免污染 ```xhs_topics``` 围栏匹配（否则会提前闭合围栏、
// 使 JSON 截断走 pending 降级路径而非 tryParse 正式路径）。
const safeString = fc.string({ maxLength: 30 }).map((s) => s.replace(/`/g, ""));

// 结构良好的富选题：title 必填，其余富字段随机存在。
const wellFormedTopicArb = fc.record(
  {
    title: safeString,
    hotRate: fc.integer({ min: 1, max: 100 }),
    angle: safeString,
    kw: safeString,
    rationale: safeString,
    emotional: safeString,
  },
  { requiredKeys: ["title"] },
);

// 畸形对象：缺 title / title 类型错配 / 富字段类型错配 / 空对象 / 未知字段。
const malformedObjectArb = fc.oneof(
  fc.record({ angle: safeString, kw: safeString }), // 缺 title
  fc.record({ title: fc.integer(), hotRate: safeString }), // title 与 hotRate 类型错配
  fc.record({ title: safeString, evidence: fc.integer() }), // evidence 非数组
  fc.constant<Record<string, unknown>>({}), // 空对象
  fc.record({ foo: safeString, bar: fc.integer(), baz: fc.boolean() }), // 全未知字段
);

// 单个 topics 数组元素：混合字符串 / 富选题 / 畸形对象 / 原始类型 / null。
const topicEntryArb = fc.oneof(
  safeString, // 字符串（旧格式）
  wellFormedTopicArb, // 结构良好富选题
  malformedObjectArb, // 畸形对象
  fc.integer(), // 数字
  fc.double({ noNaN: true, noDefaultInfinity: true }), // 浮点
  fc.boolean(), // 布尔
  fc.constant(null), // null
);

// topics 数组：允许空数组（守恒对 length 0 亦成立）。
const topicsArrayArb = fc.array(topicEntryArb, { maxLength: 12 });

function buildTopicsContent(topics: unknown[]): string {
  const payload = { intro: "候选选题", topics, evidence: [] as unknown[] };
  // 三反引号围栏 + 合法 JSON（JSON.stringify 保证合法），走 tryParse 正式解析路径。
  return "```xhs_topics\n" + JSON.stringify(payload) + "\n```";
}

test("Property 4: 缺字段降级不抛错且选题数量守恒", () => {
  fc.assert(
    fc.property(topicsArrayArb, (topics) => {
      const content = buildTopicsContent(topics);

      // (a) 解析永不抛异常（畸形项降级而非抛错）。
      let segments;
      try {
        segments = parseXhsBlocks(content);
      } catch (err) {
        assert.fail(`parseXhsBlocks 不应抛出异常，却抛出：${String(err)}`);
      }

      const topicsSeg = segments.find((s) => s.kind === "topics");
      assert.ok(topicsSeg && topicsSeg.kind === "topics", "应解析出 topics 片段");
      assert.equal(topicsSeg.isPending, undefined, "合法 JSON 应走正式解析路径而非 pending 降级");

      // (b) 选题数量守恒：输出条目数 == 输入 topics 数组长度。
      assert.equal(
        topicsSeg.data.topics.length,
        topics.length,
        `选题数应守恒：输入 ${topics.length}，输出 ${topicsSeg.data.topics.length}`,
      );
    }),
    { numRuns: 200 },
  );
});
