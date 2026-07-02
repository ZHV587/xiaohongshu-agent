import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import {
  applyOptimisticSchedule,
  rollbackSchedule,
} from "../src/components/studio/backend-mappers";
import type { CalendarDay, CalendarItem } from "../src/components/studio/types";

// Feature: studio-data-integration, Property 12
// Property 12: 排期失败回滚（round-trip 恒等）
// Validates: Requirements 3.1, 3.7 (studio-data-integration 14.3)
//
// 对任意日历初态与一次排期写动作（date + CalendarItem）：
//  - 先对初态做深快照 snapshotBefore；
//  - applyOptimisticSchedule(initial, date, item) 做乐观新增；
//  - 排期持久化失败后 rollbackSchedule(snapshotBefore) 必须与「操作前」状态深相等
//    （round-trip 恒等：失败完全撤销乐观更新）；
//  - applyOptimisticSchedule 不修改入参（调用方持有的快照保持完好）；
//  - rollbackSchedule 返回深拷贝，不与快照别名（改动返回值不影响快照）。

const toneArb = fc.constantFrom<CalendarItem["tone"]>("coral", "topic", "draft");

const calendarItemArb: fc.Arbitrary<CalendarItem> = fc.record({
  t: fc.string({ maxLength: 20 }),
  time: fc.string({ maxLength: 8 }),
  tone: toneArb,
  acct: fc.constantFrom("acc_a", "acc_b", "acc_c", "acc_d"),
});

// 日历：日期 1–28（覆盖「date 已存在则追加 / 不存在则新建」两条分支）。
// 日期唯一 —— 契约上 CalendarDay 以 date 为键，每个日期至多一条日历记录。
const calendarDayArb: fc.Arbitrary<CalendarDay> = fc.record({
  date: fc.integer({ min: 1, max: 28 }),
  items: fc.array(calendarItemArb, { maxLength: 6 }),
});
const calendarArb = fc.uniqueArray(calendarDayArb, {
  maxLength: 8,
  selector: (day) => day.date,
});

// 排期写动作的目标日期：与初态日期区间重叠，使 exists / not-exists 两分支都被覆盖。
const scheduleDateArb = fc.integer({ min: 1, max: 28 });

test("Property 12: 排期失败回滚后与操作前状态深相等（round-trip 恒等）", () => {
  fc.assert(
    fc.property(
      calendarArb,
      scheduleDateArb,
      calendarItemArb,
      (initial, date, item) => {
        // 操作前的独立深快照（脱离 initial 引用，作为回滚的真值来源）。
        const snapshotBefore: CalendarDay[] = JSON.parse(JSON.stringify(initial));

        // 乐观更新（模拟排期写动作乐观新增）。
        applyOptimisticSchedule(initial, date, item);

        // 排期持久化失败 → 回滚。
        const rolledBack = rollbackSchedule(snapshotBefore);

        // round-trip 恒等：回滚后状态与操作前深相等。
        assert.deepEqual(rolledBack, snapshotBefore, "回滚必须完全撤销乐观更新，恢复操作前状态");
      },
    ),
    { numRuns: 200 },
  );
});

test("Property 12: applyOptimisticSchedule 不修改入参（快照完好）", () => {
  fc.assert(
    fc.property(
      calendarArb,
      scheduleDateArb,
      calendarItemArb,
      (initial, date, item) => {
        const before = JSON.stringify(initial);
        const result = applyOptimisticSchedule(initial, date, item);

        // 入参未被修改：序列化前后一致。
        assert.equal(JSON.stringify(initial), before, "applyOptimisticSchedule 不得修改入参");
        // 乐观新增确实生效：结果比入参多一个归属该 date 的 item。
        const countIn = (cal: readonly CalendarDay[]) =>
          cal
            .filter((d) => d.date === date)
            .reduce((n, d) => n + d.items.length, 0);
        assert.equal(
          countIn(result),
          countIn(initial) + 1,
          "乐观更新应向目标日期新增恰好一条排期项",
        );
      },
    ),
    { numRuns: 200 },
  );
});

test("Property 12: rollbackSchedule 返回深拷贝，不与快照别名", () => {
  fc.assert(
    fc.property(calendarArb, (initial) => {
      const snapshotBefore: CalendarDay[] = JSON.parse(JSON.stringify(initial));
      const snapshotSerialized = JSON.stringify(snapshotBefore);
      const result = rollbackSchedule(snapshotBefore);

      // 初始为深相等但非同一引用。
      assert.deepEqual(result, snapshotBefore, "回滚结果初始应与快照深相等");
      assert.notEqual(result, snapshotBefore, "回滚结果不得与快照为同一数组引用");

      // 变异返回值不得回写到快照（验证深拷贝、无别名）。
      if (result.length > 0) {
        result[0].date = -999;
        result[0].items.push({ t: "mut---", time: "00:00", tone: "coral", acct: "acc_a" });
      }
      result.push({ date: -1, items: [] });

      assert.equal(
        JSON.stringify(snapshotBefore),
        snapshotSerialized,
        "变异回滚结果不得影响原快照（返回值须为深拷贝）",
      );
    }),
    { numRuns: 200 },
  );
});
