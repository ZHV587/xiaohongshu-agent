import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import { computeAccountsOverview } from "../src/components/studio/backend-mappers";
import type { Account } from "../src/components/studio/types";

// Feature: studio-data-integration, Property 9
// Property 9: 账号矩阵计数与聚合一致
// Validates: Requirements 3.1, 3.7 (studio-data-integration 9.2, 9.3)
//
// computeAccountsOverview(accounts) 满足：
//   totalFans   === Σ fansNum
//   weekNewFans === Σ dFans
//   weekPosts   === Σ posts
//   avgHotRate  === (Σ hot) / count
// 空列表 → 全部为 0（不产生 NaN）。
// 实现对每个数值字段用 Number.isFinite 守卫：非有限值按 0 计入。

// 数值字段生成器：以整数为主，保证求和/求平均可做精确浮点比较；
// 另混入非有限值（NaN / ±Infinity）以验证 isFinite 守卫按 0 处理。
const numericFieldArb = fc.oneof(
  { weight: 8, arbitrary: fc.integer({ min: -1_000_000, max: 1_000_000 }) },
  { weight: 1, arbitrary: fc.constantFrom(NaN, Infinity, -Infinity) },
);

const accountArb: fc.Arbitrary<Account> = fc.record({
  id: fc.string({ maxLength: 8 }),
  handle: fc.string({ maxLength: 8 }),
  niche: fc.string({ maxLength: 8 }),
  initial: fc.string({ maxLength: 2 }),
  fans: fc.string({ maxLength: 8 }),
  fansNum: numericFieldArb,
  dFans: numericFieldArb,
  posts: numericFieldArb,
  hot: numericFieldArb,
  status: fc.string({ maxLength: 8 }),
  tone: fc.constantFrom("coral", "topic", "draft"),
});

// 复刻实现的守卫口径：非有限值按 0 计入。
const finiteOrZero = (n: number): number => (Number.isFinite(n) ? n : 0);

test("Property 9: 账号 overview 聚合与逐项求和/求平均一致", () => {
  fc.assert(
    fc.property(fc.array(accountArb, { maxLength: 50 }), (accounts) => {
      const overview = computeAccountsOverview(accounts);

      const expectedTotalFans = accounts.reduce((s, a) => s + finiteOrZero(a.fansNum), 0);
      const expectedWeekNewFans = accounts.reduce((s, a) => s + finiteOrZero(a.dFans), 0);
      const expectedWeekPosts = accounts.reduce((s, a) => s + finiteOrZero(a.posts), 0);
      const hotSum = accounts.reduce((s, a) => s + finiteOrZero(a.hot), 0);
      const expectedAvgHotRate = accounts.length > 0 ? hotSum / accounts.length : 0;

      // 整数生成器 + 复刻同一归约公式 → 精确浮点相等。
      assert.equal(overview.totalFans, expectedTotalFans, "totalFans 应等于 Σ fansNum");
      assert.equal(overview.weekNewFans, expectedWeekNewFans, "weekNewFans 应等于 Σ dFans");
      assert.equal(overview.weekPosts, expectedWeekPosts, "weekPosts 应等于 Σ posts");
      assert.equal(overview.avgHotRate, expectedAvgHotRate, "avgHotRate 应等于 (Σ hot)/count");

      // 无 NaN 逃逸。
      assert.ok(!Number.isNaN(overview.totalFans), "totalFans 不应为 NaN");
      assert.ok(!Number.isNaN(overview.weekNewFans), "weekNewFans 不应为 NaN");
      assert.ok(!Number.isNaN(overview.weekPosts), "weekPosts 不应为 NaN");
      assert.ok(!Number.isNaN(overview.avgHotRate), "avgHotRate 不应为 NaN");
    }),
    { numRuns: 200 },
  );
});

test("Property 9: 空列表各项聚合为 0（不产生 NaN）", () => {
  const overview = computeAccountsOverview([]);
  assert.equal(overview.totalFans, 0);
  assert.equal(overview.weekNewFans, 0);
  assert.equal(overview.weekPosts, 0);
  assert.equal(overview.avgHotRate, 0);
  assert.ok(!Number.isNaN(overview.avgHotRate), "空列表 avgHotRate 应为 0 而非 NaN");
});
