import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import { parseXhsBlocks, type RichTopic } from "../src/lib/xhs-blocks";

// Feature: studio-data-integration, Property 3
// Property 3: hotRate 字段净化
// Validates: Requirements 3.1, 3.7 (studio-data-integration 1.3)
//
// parseRichTopic 仅在 hotRate 为 [1,100] 的整数时保留该键，其余一律省略（绝不渲染 🔥0）。
// 本属性覆盖输入空间：缺失 / 0 / 负 / >100 / 非整浮点 / 合法 1–100 整数。

const MISSING = Symbol("missing-hotRate");

// hotRate 输入生成器：覆盖净化契约的全部分支。
const hotRateArb = fc.oneof(
  fc.constant<typeof MISSING>(MISSING), // 缺失：不写入 hotRate 键
  fc.integer({ min: 1, max: 100 }), // 合法：1–100 整数
  fc.constant(0), // 边界下越界：0
  fc.integer({ min: -1_000_000, max: -1 }), // 负数
  fc.integer({ min: 101, max: 1_000_000 }), // 上界越界：>100
  fc
    .double({ min: -50, max: 200, noNaN: true, noDefaultInfinity: true })
    .filter((x) => !Number.isInteger(x)), // 非整浮点（含区间内的小数，如 50.5）
);

// 标题仅用于构造合法富选题对象；过滤反引号，避免污染 ```xhs_topics``` 围栏匹配。
const titleArb = fc.string({ maxLength: 40 }).filter((t) => !t.includes("`"));

function buildTopicsContent(title: string, hotRate: unknown): string {
  const topicObj: Record<string, unknown> = { title };
  if (hotRate !== MISSING) topicObj.hotRate = hotRate;
  const payload = { intro: "候选选题", topics: [topicObj], evidence: [] };
  // 三反引号围栏 + 合法 JSON，确保走 tryParse 正式解析路径（非 pending 降级）。
  return "```xhs_topics\n" + JSON.stringify(payload) + "\n```";
}

test("Property 3: hotRate 当且仅当为 [1,100] 整数时保留，否则省略", () => {
  fc.assert(
    fc.property(titleArb, hotRateArb, (title, hotRate) => {
      const content = buildTopicsContent(title, hotRate);
      const segments = parseXhsBlocks(content);

      const topicsSeg = segments.find((s) => s.kind === "topics");
      assert.ok(topicsSeg && topicsSeg.kind === "topics", "应解析出 topics 片段");

      const parsedTopic = topicsSeg.data.topics[0];
      assert.equal(typeof parsedTopic, "object", "富选题应解析为对象而非字符串");
      const topic = parsedTopic as RichTopic;

      const value = hotRate === MISSING ? undefined : (hotRate as number);
      const shouldKeep =
        typeof value === "number" &&
        Number.isInteger(value) &&
        value >= 1 &&
        value <= 100;

      if (shouldKeep) {
        assert.ok(
          Object.prototype.hasOwnProperty.call(topic, "hotRate"),
          `合法整数 ${value} 应保留 hotRate 键`,
        );
        assert.equal(topic.hotRate, value, "保留的 hotRate 应与输入一致");
      } else {
        assert.equal(topic.hotRate, undefined, `非法输入 ${String(value)} 的 hotRate 应为 undefined`);
        assert.ok(
          !Object.prototype.hasOwnProperty.call(topic, "hotRate"),
          `非法输入 ${String(value)} 应省略 hotRate 键（而非置 0/保留）`,
        );
      }
    }),
    { numRuns: 200 },
  );
});
