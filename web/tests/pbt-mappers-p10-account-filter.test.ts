import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import {
  filterByAccount,
  filterCalendarByAccount,
} from "../src/components/studio/backend-mappers";
import type { CalendarDay, CalendarItem } from "../src/components/studio/types";

// Feature: studio-data-integration, Property 10
// Property 10: 单账号视图过滤归属
// Validates: Requirements 3.1, 3.7 (studio-data-integration 10.3, 12.3, 13.5)
//
// 对任意混多账号数据集与选定账号：
//  - filterByAccount(items, account) 只返回 acct === account 的条目；
//  - filterCalendarByAccount(calendar, account) 保留每天归属该账号的 items、
//    剔除过滤后为空的日期、且不修改入参。
// 用小账号池（filtering 才非平凡）生成数据集。

// 小账号池：仅 4 个 id，保证多账号混合、过滤命中概率高。
const ACCOUNT_POOL = ["acc_a", "acc_b", "acc_c", "acc_d"] as const;
const accountArb = fc.constantFrom(...ACCOUNT_POOL);
const toneArb = fc.constantFrom<CalendarItem["tone"]>("coral", "topic", "draft");

const calendarItemArb: fc.Arbitrary<CalendarItem> = fc.record({
  t: fc.string({ maxLength: 20 }),
  time: fc.string({ maxLength: 8 }),
  tone: toneArb,
  acct: accountArb,
});

// 混多账号的 items 数组（可能为空，覆盖空态）。
const itemsArb = fc.array(calendarItemArb, { maxLength: 12 });

// 日历：日期 1–28，每天含混多账号的 items。
const calendarDayArb: fc.Arbitrary<CalendarDay> = fc.record({
  date: fc.integer({ min: 1, max: 28 }),
  items: itemsArb,
});
const calendarArb = fc.array(calendarDayArb, { maxLength: 8 });

test("Property 10: filterByAccount 只返回归属选定账号的条目", () => {
  fc.assert(
    fc.property(itemsArb, accountArb, (items, account) => {
      const before = JSON.stringify(items);
      const result = filterByAccount(items, account);

      // 结果内每一项都归属选定账号。
      for (const item of result) {
        assert.equal(item.acct, account, "过滤结果中的条目必须归属选定账号");
      }
      // 无遗漏：原数组中所有归属该账号的条目都被保留（计数一致）。
      const expectedCount = items.filter((i) => i.acct === account).length;
      assert.equal(result.length, expectedCount, "应保留全部归属该账号的条目，不多不少");
      // 保序：结果是原数组按账号过滤后的子序列。
      assert.deepEqual(
        result,
        items.filter((i) => i.acct === account),
        "过滤应保持原有相对顺序",
      );
      // 不修改入参。
      assert.equal(JSON.stringify(items), before, "filterByAccount 不得修改入参");
    }),
    { numRuns: 200 },
  );
});

test("Property 10: filterCalendarByAccount 归属过滤 + 剔除空日期 + 不修改入参", () => {
  fc.assert(
    fc.property(calendarArb, accountArb, (calendar, account) => {
      const before = JSON.stringify(calendar);
      const result = filterCalendarByAccount(calendar, account);

      for (const day of result) {
        // 每天所有 item 均归属选定账号。
        for (const item of day.items) {
          assert.equal(item.acct, account, "过滤后每个日历项都必须归属选定账号");
        }
        // 保留的日期一定非空。
        assert.ok(day.items.length > 0, "过滤后为空的日期必须被剔除");
      }

      // 结构一致：结果等于对原日历逐天按账号过滤、再剔除空日期后的产物。
      // 用索引对齐的方式独立计算期望值（不按 date 查找，容忍重复 date）。
      const expected = calendar
        .map((d) => ({ ...d, items: d.items.filter((i) => i.acct === account) }))
        .filter((d) => d.items.length > 0);
      assert.deepEqual(result, expected, "过滤结果应等于逐天过滤 + 剔除空日期");

      // 剔除性质：所有过滤后仍有归属条目的日期都被保留（计数一致）。
      const expectedDays = calendar.filter(
        (d) => d.items.some((i) => i.acct === account),
      ).length;
      assert.equal(result.length, expectedDays, "应保留且仅保留过滤后非空的日期");

      // 不修改入参（深比较序列化前后一致）。
      assert.equal(JSON.stringify(calendar), before, "filterCalendarByAccount 不得修改入参");
    }),
    { numRuns: 200 },
  );
});
