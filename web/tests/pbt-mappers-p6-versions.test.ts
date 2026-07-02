import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import {
  mapVersions,
  selectVersionDraft,
  VERSION_IDS,
  type DraftVersionInput,
} from "../src/components/studio/backend-mappers";
import type { VersionId } from "../src/components/studio/types";

// Feature: studio-data-integration, Property 6
// Property 6: 多版本映射与选择应用
// Validates: Requirements 3.1, 3.7 (studio-data-integration 4.2, 4.3)
//
// mapVersions 把 1–3 项的原始版本数组按固定顺序 A/B/C 一一落位，得到 Partial<Versions>；
// 空数组返回 null；>3 项截断为 A/B/C 三档；缺失/类型错配字段规整为安全默认值（不编造内容）。
// selectVersionDraft(mapped, id) 回写 canonical 草稿的 { title, body }，等于所选版本对应值；
// 选中不存在的版本返回 null（调用方保持当前草稿不变）。

const MISSING = Symbol("missing-field");

/** 单个字段生成器：覆盖 缺失 / 合法 string / 类型错配（number/null/boolean/object）。 */
const stringFieldArb = fc.oneof(
  fc.constant<typeof MISSING>(MISSING),
  fc.string({ maxLength: 30 }),
  fc.constant(""),
  fc.integer(),
  fc.constant(null),
  fc.boolean(),
  fc.constant({ nested: true }),
);

/** tags 字段生成器：覆盖 缺失 / 纯字符串数组 / 含非字符串杂质数组 / 非数组类型错配。 */
const tagsFieldArb = fc.oneof(
  fc.constant<typeof MISSING>(MISSING),
  fc.array(fc.string({ maxLength: 12 }), { maxLength: 5 }),
  fc.array(fc.oneof(fc.string({ maxLength: 12 }), fc.integer(), fc.constant(null)), { maxLength: 5 }),
  fc.constant("not-an-array"),
  fc.integer(),
);

/** 生成一个可能字段缺失/类型错配的原始版本对象（模拟后端 xhs_copy 多版本项)。 */
const draftVersionInputArb: fc.Arbitrary<Record<string, unknown>> = fc
  .record({
    label: stringFieldArb,
    note: stringFieldArb,
    title: stringFieldArb,
    cover: stringFieldArb,
    body: stringFieldArb,
    tags: tagsFieldArb,
  })
  .map((raw) => {
    const obj: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(raw)) {
      if (value !== MISSING) obj[key] = value;
    }
    return obj;
  });

/** 在测试侧独立复算规整后的期望值，镜像 normalizeDraftVersion 的口径（安全默认、不编造）。 */
function expectedNormalized(input: Record<string, unknown>, id: VersionId) {
  const label =
    typeof input.label === "string" && (input.label as string).length > 0 ? (input.label as string) : id;
  return {
    label,
    note: typeof input.note === "string" ? (input.note as string) : "",
    title: typeof input.title === "string" ? (input.title as string) : "",
    cover: typeof input.cover === "string" ? (input.cover as string) : "",
    body: typeof input.body === "string" ? (input.body as string) : "",
    tags: Array.isArray(input.tags)
      ? (input.tags as unknown[]).filter((t): t is string => typeof t === "string")
      : [],
  };
}

test("Property 6: 空数组 → mapVersions 返回 null（保持单版本编辑态，不编造版本）", () => {
  const mapped = mapVersions([]);
  assert.equal(mapped, null);
});

test("Property 6: 1–3 项版本按 A/B/C 顺序一一映射且字段规整为安全默认值", () => {
  fc.assert(
    fc.property(fc.array(draftVersionInputArb, { minLength: 1, maxLength: 3 }), (versions) => {
      const mapped = mapVersions(versions as DraftVersionInput[]);
      assert.ok(mapped, "非空数组应返回映射对象而非 null");

      // 键与输入条目一一对应、顺序为 A/B/C 前 N 个。
      const expectedKeys = VERSION_IDS.slice(0, versions.length);
      assert.deepEqual(Object.keys(mapped!), [...expectedKeys], "键集应等于 A/B/C 的前 N 个且有序");

      // 每个版本的内容与「测试侧独立复算的规整期望」逐字段相等（含缺失字段的安全默认）。
      expectedKeys.forEach((id, i) => {
        const actual = mapped![id];
        assert.ok(actual, `键 ${id} 应存在`);
        assert.deepEqual(actual, expectedNormalized(versions[i], id), `版本 ${id} 内容应与规整期望一致`);
      });
    }),
    { numRuns: 200 },
  );
});

test("Property 6: >3 项被截断为 A/B/C 三档（多余版本丢弃，不越界编造键）", () => {
  fc.assert(
    fc.property(fc.array(draftVersionInputArb, { minLength: 4, maxLength: 8 }), (versions) => {
      const mapped = mapVersions(versions as DraftVersionInput[]);
      assert.ok(mapped, "超长数组仍返回映射对象");
      assert.deepEqual(Object.keys(mapped!), ["A", "B", "C"], "键应恰为 A/B/C 三档");

      // 前三项分别落位 A/B/C，其内容与对应输入项规整期望一致。
      (["A", "B", "C"] as const).forEach((id, i) => {
        assert.deepEqual(mapped![id], expectedNormalized(versions[i], id), `截断后版本 ${id} 应取第 ${i} 项`);
      });
    }),
    { numRuns: 200 },
  );
});

test("Property 6: selectVersionDraft 对存在版本返回其 title/body，对缺失版本返回 null", () => {
  fc.assert(
    fc.property(
      fc.array(draftVersionInputArb, { minLength: 1, maxLength: 3 }),
      fc.constantFrom<VersionId>("A", "B", "C"),
      (versions, id) => {
        const mapped = mapVersions(versions as DraftVersionInput[]);
        assert.ok(mapped, "非空数组应返回映射对象");

        const selected = selectVersionDraft(mapped, id);
        const present = mapped![id];

        if (present) {
          assert.ok(selected, `存在的版本 ${id} 应可选中`);
          // 选中后回写 canonical 草稿的 title/body 恰等于该版本对应值。
          assert.equal(selected!.title, present.title, "回写的 title 应等于所选版本 title");
          assert.equal(selected!.body, present.body, "回写的 body 应等于所选版本 body");
          assert.deepEqual(Object.keys(selected!).sort(), ["body", "title"], "仅回写 title/body 两字段");
        } else {
          assert.equal(selected, null, `不存在的版本 ${id} 应返回 null（保持当前草稿不变）`);
        }
      },
    ),
    { numRuns: 200 },
  );
});

test("Property 6: null/undefined 映射对象上的 selectVersionDraft 返回 null", () => {
  fc.assert(
    fc.property(fc.constantFrom<VersionId>("A", "B", "C"), (id) => {
      assert.equal(selectVersionDraft(null, id), null);
      assert.equal(selectVersionDraft(undefined, id), null);
    }),
    { numRuns: 100 },
  );
});
