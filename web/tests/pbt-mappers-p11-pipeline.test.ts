import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import {
  PUBLISH_STAGES,
  groupQueueByStage,
  canAdvanceStage,
  publishItemHasRequiredLink,
  queueSatisfiesLinkInvariant,
} from "../src/components/studio/backend-mappers";
import type { PublishItem, PublishStage } from "../src/components/studio/types";

// Feature: studio-data-integration, Property 11
// Property 11: 发布管线 stage 不变量与单向状态机
// Validates: Requirements 3.4, 3.1, 3.7 (studio-data-integration 13.1, 13.2, 13.3, 13.4)
//
// 对任意发布队列与任意 (from, to) stage 对：
//  - 分组：groupQueueByStage 分区后每列内条目 stage 与列标识一致，且已知 stage
//    条目总数守恒（未知 stage 被容错忽略、不计入）；
//  - 状态机：canAdvanceStage(from, to) 当且仅当相邻正向转移
//    (scheduled→published / published→measured) 时为真，逆向/跨级/自环一律为假；
//  - link 不变量：scheduled 条目无论有无 link 均满足；published/measured 条目
//    当且仅当 link 为去空白后非空字符串时满足；队列级 == 逐条 every。

const stageArb = fc.constantFrom<PublishStage>(...PUBLISH_STAGES);

// link 生成器：覆盖 undefined、空串、纯空白、正常 URL、含前后空白的串。
const linkArb = fc.oneof(
  fc.constant(undefined),
  fc.constant(""),
  fc.constantFrom("   ", "\t", "\n  "),
  fc.webUrl(),
  fc.string({ maxLength: 12 }),
  fc.string({ maxLength: 8 }).map((s) => `  ${s}  `),
);

// 合法 stage 的发布队列项。
const publishItemArb: fc.Arbitrary<PublishItem> = fc.record({
  id: fc.integer({ min: 0, max: 10_000 }),
  title: fc.string({ maxLength: 20 }),
  acct: fc.constantFrom("acc_a", "acc_b", "acc_c"),
  stage: stageArb,
  link: linkArb,
  time: fc.string({ maxLength: 8 }),
});

// 已知 + 未知 stage 混合项：把 stage 替换为任意字符串（含合法与非法值），
// 用于验证分组的容错降级（未知 stage 被忽略）。
const tolerantItemArb: fc.Arbitrary<PublishItem> = fc
  .tuple(
    publishItemArb,
    fc.oneof(
      stageArb,
      fc.constantFrom("draft", "archived", "unknown", "", "PUBLISHED", "Scheduled"),
      fc.string({ maxLength: 10 }),
    ),
  )
  // 故意注入可能非法的 stage 字符串，测试运行时容错口径。
  .map(([item, stage]) => ({ ...item, stage: stage as PublishStage }));

const queueArb = fc.array(publishItemArb, { maxLength: 20 });
const tolerantQueueArb = fc.array(tolerantItemArb, { maxLength: 20 });

const KNOWN_STAGES = new Set<string>(PUBLISH_STAGES);

test("Property 11: groupQueueByStage 分组一致 + 已知 stage 条目总数守恒 + 容错忽略未知 stage", () => {
  fc.assert(
    fc.property(tolerantQueueArb, (queue) => {
      const before = JSON.stringify(queue);
      const groups = groupQueueByStage(queue);

      // 返回对象始终含且仅含三个已知 stage 键。
      assert.deepEqual(
        Object.keys(groups).sort(),
        [...PUBLISH_STAGES].sort(),
        "分组结果必须始终含全部三个 stage 键",
      );

      // 每列内所有条目的 stage 与列标识一致。
      let grouped = 0;
      for (const stage of PUBLISH_STAGES) {
        for (const item of groups[stage]) {
          assert.equal(item.stage, stage, `group[${stage}] 中的条目 stage 必须为 ${stage}`);
        }
        grouped += groups[stage].length;
      }

      // 总数守恒：分组条目数 == 队列中 stage 为已知值的条目数（未知 stage 被忽略）。
      const knownCount = queue.filter((i) => KNOWN_STAGES.has(i.stage as string)).length;
      assert.equal(grouped, knownCount, "分组条目总数应等于已知 stage 条目数（守恒）");

      // 分组是对已知 stage 条目的稳定分区：逐列等于原队列按该 stage 过滤后的子序列。
      for (const stage of PUBLISH_STAGES) {
        assert.deepEqual(
          groups[stage],
          queue.filter((i) => i.stage === stage),
          `group[${stage}] 应等于原队列按该 stage 过滤的结果（保序）`,
        );
      }

      // 不修改入参。
      assert.equal(JSON.stringify(queue), before, "groupQueueByStage 不得修改入参");
    }),
    { numRuns: 200 },
  );
});

test("Property 11: canAdvanceStage 当且仅当相邻正向转移（穷举 + 随机）", () => {
  // 穷举全部 3×3 = 9 个 (from, to) 组合，精确断言真值表。
  const ALLOWED = new Set(["scheduled->published", "published->measured"]);
  for (const from of PUBLISH_STAGES) {
    for (const to of PUBLISH_STAGES) {
      const expected = ALLOWED.has(`${from}->${to}`);
      assert.equal(
        canAdvanceStage(from, to),
        expected,
        `canAdvanceStage(${from}, ${to}) 应为 ${expected}`,
      );
      // 自环显式为假。
      if (from === to) {
        assert.equal(canAdvanceStage(from, to), false, "自环转移必须被拒绝");
      }
    }
  }

  // 随机迭代：与真值表定义保持一致，且逆向转移恒为假。
  fc.assert(
    fc.property(stageArb, stageArb, (from, to) => {
      const forward =
        (from === "scheduled" && to === "published") ||
        (from === "published" && to === "measured");
      assert.equal(canAdvanceStage(from, to), forward, "仅相邻正向转移被允许");
      // 若正向被允许，则其逆向必须被拒绝（单向性）。
      if (forward) {
        assert.equal(canAdvanceStage(to, from), false, "逆向转移必须被拒绝（单向状态机）");
      }
    }),
    { numRuns: 200 },
  );
});

test("Property 11: publishItemHasRequiredLink / queueSatisfiesLinkInvariant link 不变量", () => {
  fc.assert(
    fc.property(publishItemArb, (item) => {
      const hasNonEmptyLink =
        typeof item.link === "string" && item.link.trim().length > 0;
      const expected =
        item.stage === "scheduled" ? true : hasNonEmptyLink;
      assert.equal(
        publishItemHasRequiredLink(item),
        expected,
        `stage=${item.stage} link=${JSON.stringify(item.link)} 的 link 不变量判定错误`,
      );
    }),
    { numRuns: 200 },
  );

  // 队列级不变量 == 逐条 every。
  fc.assert(
    fc.property(queueArb, (queue) => {
      assert.equal(
        queueSatisfiesLinkInvariant(queue),
        queue.every(publishItemHasRequiredLink),
        "队列级不变量必须等于逐条 publishItemHasRequiredLink 的合取",
      );
    }),
    { numRuns: 200 },
  );
});
