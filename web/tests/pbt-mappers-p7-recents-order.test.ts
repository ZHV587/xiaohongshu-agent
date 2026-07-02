// Feature: studio-data-integration, Property 7: 最近创作按时间倒序
// 对任意带随机时间戳的条目数组，sortByTimeDesc 产出相邻项时间戳单调非递增（ts[i] >= ts[i+1]），
// 且不修改入参、稳定（相等时间戳保持原相对顺序）。
// Validates: Requirements 3.1, 3.7 （对应 studio-data-integration: 7.2）
import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";
import { sortByTimeDesc } from "../src/components/studio/backend-mappers";

const NUM_RUNS = 200;

// 单个「最近创作」条目：id 用于唯一定位、追踪稳定性；ts 为 epoch 毫秒时间戳。
interface Item {
  id: number;
  ts: number;
}

const getTime = (item: Item): number => item.ts;

// 生成带唯一 id 的条目数组：id 严格递增以保证可区分（追踪稳定性），
// ts 有意约束到较小范围以制造大量重复时间戳，压测稳定排序分支。
const itemsArb: fc.Arbitrary<Item[]> = fc
  .array(fc.integer({ min: 0, max: 5 }), { minLength: 0, maxLength: 30 })
  .map((tsList) => tsList.map((ts, id) => ({ id, ts })));

test("Property 7: sortByTimeDesc 相邻条目时间戳单调非递增（最新在前）", () => {
  fc.assert(
    fc.property(itemsArb, (items) => {
      const sorted = sortByTimeDesc(items, getTime);
      for (let i = 0; i + 1 < sorted.length; i++) {
        assert.ok(
          sorted[i].ts >= sorted[i + 1].ts,
          `相邻项应非递增：位置 ${i} 的 ts=${sorted[i].ts} 应 >= 位置 ${i + 1} 的 ts=${sorted[i + 1].ts}`,
        );
      }
    }),
    { numRuns: NUM_RUNS },
  );
});

test("Property 7: sortByTimeDesc 不修改入参（纯函数）", () => {
  fc.assert(
    fc.property(itemsArb, (items) => {
      const snapshot = items.map((it) => ({ ...it }));
      sortByTimeDesc(items, getTime);
      // 入参数组的长度、顺序与每项内容均保持不变。
      assert.equal(items.length, snapshot.length, "入参长度不得变化");
      items.forEach((it, i) => {
        assert.equal(it.id, snapshot[i].id, "入参各项 id 不得变化");
        assert.equal(it.ts, snapshot[i].ts, "入参各项 ts 不得变化");
      });
    }),
    { numRuns: NUM_RUNS },
  );
});

test("Property 7: sortByTimeDesc 稳定排序（相等时间戳保持原相对顺序）", () => {
  fc.assert(
    fc.property(itemsArb, (items) => {
      const sorted = sortByTimeDesc(items, getTime);

      // 长度守恒 + 元素为原对象的置换（同一引用集合）。
      assert.equal(sorted.length, items.length, "排序前后元素数量应守恒");
      const inputIds = items.map((it) => it.id).sort((a, b) => a - b);
      const outputIds = sorted.map((it) => it.id).sort((a, b) => a - b);
      assert.deepEqual(outputIds, inputIds, "排序后应为原元素的置换，不增删");

      // 稳定性：同一 ts 分组内，输出中的 id 顺序应等于输入中的原始 id 顺序。
      // 由于 id 严格按输入位置递增，输入中每组内 id 天然升序；
      // 稳定排序应保持该组内相对顺序不变。
      const byTs = new Map<number, number[]>();
      for (const it of sorted) {
        const arr = byTs.get(it.ts) ?? [];
        arr.push(it.id);
        byTs.set(it.ts, arr);
      }
      for (const [ts, ids] of byTs) {
        const expected = [...ids].sort((a, b) => a - b);
        assert.deepEqual(ids, expected, `ts=${ts} 分组内应保持原相对顺序（稳定）`);
      }
    }),
    { numRuns: NUM_RUNS },
  );
});
