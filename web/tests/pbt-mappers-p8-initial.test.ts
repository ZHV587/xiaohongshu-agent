// Feature: studio-data-integration, Property 8: 用户首字母派生
// 对任意非空 name 字符串，deriveInitial(name) 恒等于其首个「码点」（Array.from(name)[0]），
// 正确处理 CJK / emoji / 代理对；空字符串返回空字符串（空态，不编造占位字母）。
// Validates: Requirements 3.1, 3.7 （对应 studio-data-integration: 8.2）
import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import { deriveInitial } from "../src/components/studio/backend-mappers";

const NUM_RUNS = 200;

// 参考实现：以码点切分取首元素。deriveInitial 必须与之等价。
function firstCodePoint(name: string): string {
  return Array.from(name)[0] ?? "";
}

// fast-check v4：以 "binary" 为切分单元的字符串，天然覆盖 BMP + 补充平面（代理对）。
// 单元长度按「码点」计，minLength:1 保证至少一个完整码点。
const nonEmptyUnicode = fc.string({ unit: "binary", minLength: 1 });

// 单个完整 unicode 码点（长度 = 1 个 binary 单元）。
const fullUnicodeChar = fc.string({ unit: "binary", minLength: 1, maxLength: 1 });

// 代表性 emoji（含 BMP 外码点，序列化为代理对）与 CJK 首字符样本。
const EMOJIS = ["😀", "🐉", "🎉", "🚀", "🔥", "👩", "🧑", "🌟", "🍜", "🐼"];
const CJK = ["红", "书", "小", "创", "作", "运", "营", "笔", "记", "阿"];

test("Property 8: 非空 name 的 initial 恒等于首个码点（full unicode / 代理对）", () => {
  fc.assert(
    fc.property(nonEmptyUnicode, (name) => {
      const initial = deriveInitial(name);
      assert.equal(initial, firstCodePoint(name));
      // initial 必须是完整码点：绝不切出半个代理对（1 或 2 个 UTF-16 code unit）。
      assert.ok(initial.length === 1 || initial.length === 2, "initial 应为单个完整码点");
      assert.equal(Array.from(initial).length, 1, "initial 恰含一个码点");
    }),
    { numRuns: NUM_RUNS },
  );
});

test("Property 8: emoji 前缀（代理对）不被截半，initial 取完整 emoji", () => {
  fc.assert(
    fc.property(
      fc.constantFrom(...EMOJIS),
      fc.string({ unit: "binary" }),
      (emoji, rest) => {
        const name = emoji + rest;
        assert.equal(deriveInitial(name), emoji);
      },
    ),
    { numRuns: NUM_RUNS },
  );
});

test("Property 8: CJK 前缀，initial 取首个汉字", () => {
  fc.assert(
    fc.property(
      fc.constantFrom(...CJK),
      fc.string({ unit: "binary" }),
      (cjk, rest) => {
        const name = cjk + rest;
        assert.equal(deriveInitial(name), cjk);
      },
    ),
    { numRuns: NUM_RUNS },
  );
});

test("Property 8: 空字符串返回空字符串（空态，不编造占位）", () => {
  assert.equal(deriveInitial(""), "");
});

test("Property 8: 单码点字符串的 initial 等于其自身", () => {
  fc.assert(
    fc.property(fullUnicodeChar, (cp) => {
      assert.equal(deriveInitial(cp), cp);
    }),
    { numRuns: NUM_RUNS },
  );
});
