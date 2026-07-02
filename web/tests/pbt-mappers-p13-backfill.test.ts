import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import {
  ALLOWED_BACKFILL_METRICS,
  validateBackfillMetrics,
} from "../src/components/studio/backend-mappers";

// Feature: studio-data-integration, Property 13
// Property 13: 回填指标校验（前后端同口径）
// Validates: Requirements 3.1, 3.7 (studio-data-integration 15.3)
//
// 口径对齐后端 data_foundation/performance_feedback.py 的 _clean_metrics：
//  - 入参非「纯对象」（null / 数组 / 原始值）→ 拒绝（"metrics must be a mapping"）
//  - 仅受支持指标（ALLOWED_BACKFILL_METRICS）参与校验，其它键被忽略
//  - 受支持指标值无法转为数值 / 非有限 → 拒绝（"metrics must be finite non-negative numbers"）
//  - 受支持指标值为负 → 拒绝（"metrics must be non-negative"）
//  - 不含任何受支持指标 → 拒绝（"metrics must contain at least one supported metric"）
// 当且仅当「入参为纯对象」且「至少含一个受支持指标」且「全部受支持指标均强制为有限非负数值」时通过。

// --- 值强制 oracle：复刻 impl 的 coerceMetricNumber，作为独立真值来源 ----------
function coerce(value: unknown): number | null {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const s = value.trim();
    if (s === "") return null;
    const lower = s.toLowerCase();
    if (["inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"].includes(lower)) {
      return lower.startsWith("-") ? -Infinity : Infinity;
    }
    if (["nan", "+nan", "-nan"].includes(lower)) return NaN;
    const n = Number(s);
    return Number.isNaN(n) ? null : n;
  }
  return null;
}

const SUPPORTED = new Set<string>(ALLOWED_BACKFILL_METRICS);

// 期望判定与期望错误文案（严格复刻 impl：按 Object.entries 插入顺序遍历，
// 首个命中的错误分支决定文案，故遍历顺序必须与 impl 一致）。
function expected(metrics: Record<string, unknown>): { ok: boolean; error?: string } {
  let supportedCount = 0;
  for (const [key, value] of Object.entries(metrics)) {
    if (!SUPPORTED.has(key)) continue;
    supportedCount += 1;
    const n = coerce(value);
    if (n === null || !Number.isFinite(n)) return { ok: false, error: "metrics must be finite non-negative numbers" };
    if (n < 0) return { ok: false, error: "metrics must be non-negative" };
  }
  if (supportedCount === 0) return { ok: false, error: "metrics must contain at least one supported metric" };
  return { ok: true };
}

// --- 生成器：值横跨 负数 / 非数值字符串 / NaN·Infinity / 布尔 / 有限非负数 ------
const valueArb: fc.Arbitrary<unknown> = fc.oneof(
  // 有限非负数（合法）
  fc.nat({ max: 10_000_000 }),
  fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
  // 负数（拒绝：non-negative）
  fc.integer({ min: -10_000_000, max: -1 }),
  fc.double({ min: -1e9, max: -0.001, noNaN: true, noDefaultInfinity: true }),
  // 非有限
  fc.constantFrom(Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY),
  // 非数值字符串 + 可解析字符串 + inf/nan 字面量
  fc.constantFrom("abc", "1万", "", "  ", "1.2.3", "12", "3.5", "-4", "inf", "-infinity", "NaN"),
  // 布尔（float(True/False) → 1/0，合法）
  fc.boolean(),
  // 其它不可强制类型（→ null → 拒绝）
  fc.constantFrom(null, undefined),
);

// 键：受支持键 + 不受支持键混合；允许空对象与「仅不受支持键」边界。
const keyArb = fc.oneof(
  fc.constantFrom(...ALLOWED_BACKFILL_METRICS),
  fc.constantFrom("unknown", "title", "noise", "点赞", "score"),
);

const metricsObjectArb: fc.Arbitrary<Record<string, unknown>> = fc.dictionary(keyArb, valueArb, {
  maxKeys: 8,
});

test("Property 13: validateBackfillMetrics 当且仅当受支持指标全为有限非负数值时通过（口径一致）", () => {
  fc.assert(
    fc.property(metricsObjectArb, (metrics) => {
      const exp = expected(metrics);
      const got = validateBackfillMetrics(metrics);

      assert.equal(got.ok, exp.ok, `ok 判定应与 oracle 一致：${JSON.stringify(metrics)}`);
      if (!exp.ok) {
        // 拒绝原因文案必须与后端 _clean_metrics 抛出的 ValueError 文案对齐。
        assert.equal(got.error, exp.error, `拒绝原因应对齐：${JSON.stringify(metrics)}`);
        assert.equal(got.cleaned, undefined, "拒绝时不得返回 cleaned");
      } else {
        // 通过时 cleaned 仅含受支持键、均为有限非负数值。
        assert.ok(got.cleaned, "通过时应返回 cleaned");
        const cleaned = got.cleaned as Record<string, number>;
        const supportedKeys = ALLOWED_BACKFILL_METRICS.filter((k) =>
          Object.prototype.hasOwnProperty.call(metrics, k),
        );
        assert.deepEqual(Object.keys(cleaned).sort(), [...supportedKeys].sort());
        for (const v of Object.values(cleaned)) {
          assert.ok(Number.isFinite(v) && v >= 0, "cleaned 值须为有限非负数");
        }
      }
    }),
    { numRuns: 300 },
  );
});

test("Property 13: 非映射入参（null / 数组 / 原始值）一律拒绝为 mapping 错误", () => {
  const nonMappingArb = fc.oneof(
    fc.constant(null),
    fc.constant(undefined),
    fc.array(fc.anything(), { maxLength: 4 }),
    fc.integer(),
    fc.double(),
    fc.string(),
    fc.boolean(),
  );
  fc.assert(
    fc.property(nonMappingArb, (input) => {
      const got = validateBackfillMetrics(input);
      assert.equal(got.ok, false);
      assert.equal(got.error, "metrics must be a mapping");
    }),
    { numRuns: 200 },
  );
});

test("Property 13: 注入任一非法受支持指标必然拒绝（→ 方向）", () => {
  const validValueArb = fc.oneof(
    fc.nat({ max: 10_000_000 }),
    fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
  );
  const badValueArb = fc.oneof(
    fc.integer({ min: -10_000_000, max: -1 }),
    fc.constantFrom(Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY),
    fc.constantFrom("abc", "1万", "", "  ", "1.2.3", null, undefined),
  );
  fc.assert(
    fc.property(
      fc.dictionary(fc.constantFrom(...ALLOWED_BACKFILL_METRICS), validValueArb, {
        minKeys: 1,
        maxKeys: 6,
      }),
      fc.constantFrom(...ALLOWED_BACKFILL_METRICS),
      badValueArb,
      (valid, badKey, badValue) => {
        const metrics: Record<string, unknown> = { ...valid, [badKey]: badValue };
        const got = validateBackfillMetrics(metrics);
        assert.equal(got.ok, false, `注入非法值后必拒绝：${JSON.stringify(metrics)}`);
      },
    ),
    { numRuns: 300 },
  );
});
