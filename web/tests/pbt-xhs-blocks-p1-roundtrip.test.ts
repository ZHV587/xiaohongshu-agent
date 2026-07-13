// Feature: studio-data-integration, Property 1: 选题/证据 JSON 解析往返一致
//
// Validates: design-system-hardening Requirements 3.3, 3.1, 3.7
//
// 对任意随机生成的富选题载荷（intro? + topics: (string|RichTopic)[]，每选题携带
// RichEvidence + evidence_mode，以及顶层共享 SourceEvidence），执行:
//   parse(content) -> segment1
//   parse(serialize(segment1.data)) -> segment2
// 断言 segment1.data 与 segment2.data 为等价对象（字段值逐一相等、忽略键顺序）。
//
// 由于 parseXhsBlocks 是一个「归一化/净化」解析器（hotRate 仅保留 1–100 整数、
// 证据要求 resource_id/title/summary 非空、无效检索模式被丢弃、缺字段回退顶层证据），
// 正确且良定义的往返是「解析结果为再序列化→再解析的不动点」：segment1 == segment2。
import assert from "node:assert/strict";
import test from "node:test";

import fc from "fast-check";

import { parseXhsBlocks, type TopicsSegment } from "../src/lib/xhs-blocks";

const RETRIEVAL_MODES = ["semantic", "keyword_fallback", "insufficient_relevance"] as const;

// 生成的字符串剔除反引号,避免污染 ```xhs_topics ... ``` 围栏定界符
// （本属性验证的是 JSON 契约的往返,而非围栏转义）。
const textArb = fc
  .oneof(
    fc.string({ maxLength: 24 }),
    fc.constantFrom("轻量露营", "通勤穿搭", "职场沟通", "露营装备清单", "周末去哪玩", "高互动笔记"),
  )
  .map((s) => s.replace(/`/g, ""));

// 时间串:一半为合法 ISO（会被 parseIsoTimestamp 保留）,一半为任意串（会被丢弃）。
// 两种情形往返均应为不动点。
const timestampArb = fc.oneof(
  fc
    .date({
      min: new Date("2001-01-01T00:00:00Z"),
      max: new Date("2099-01-01T00:00:00Z"),
      // 禁止在边界处生成 Invalid Date（否则 .toISOString() 会抛 RangeError: Invalid time value）。
      noInvalidDate: true,
    })
    // 双保险：即便任何边界仍漏出非法日期，也在 .toISOString() 之前过滤掉。
    .filter((d) => !Number.isNaN(d.getTime()))
    .map((d) => d.toISOString()),
  textArb,
);

// 数值信号:含合法有限值,以及 NaN/Infinity（经 JSON 序列化会变为 null 而被解析器丢弃）。
const numberArb = fc.oneof(
  fc.double(),
  fc.integer({ min: -1000, max: 1000 }),
  fc.constant(Number.NaN),
  fc.constant(Number.POSITIVE_INFINITY),
);

// 每选题富证据（RichEvidence 原始形态,含缺字段/类型错配的随机性）。
const richEvidenceArb = fc.record(
  {
    resource_id: textArb,
    resource_version: fc.integer({ min: 1, max: 10_000 }),
    type: textArb,
    title: textArb,
    summary: textArb,
    score: numberArb,
    relevance: numberArb,
    freshness: numberArb,
    performance: numberArb,
    why_selected: textArb,
    source_updated_at: timestampArb,
    indexed_at: timestampArb,
  },
  { requiredKeys: ["resource_id", "resource_version", "title", "summary"] },
);

// 顶层共享证据（SourceEvidence 原始形态）。
const sourceEvidenceArb = fc.record(
  {
    resource_id: textArb,
    resource_version: fc.integer({ min: 1, max: 10_000 }),
    title: textArb,
    summary: textArb,
    source_updated_at: timestampArb,
    indexed_at: timestampArb,
  },
  { requiredKeys: ["resource_id", "resource_version", "title", "summary"] },
);

// 富选题原始形态:所有键可选,以覆盖「缺字段降级 + 证据回退顶层」等分支。
const richTopicArb = fc.record(
  {
    title: textArb,
    // hotRate 覆盖 合法 1–100 整数 / 越界 / 非整 / 0,验证净化在往返下稳定。
    hotRate: fc.oneof(
      fc.integer({ min: 1, max: 100 }),
      fc.integer({ min: -50, max: 200 }),
      fc.double(),
      fc.constant(0),
    ),
    angle: textArb,
    kw: textArb,
    rationale: textArb,
    emotional: textArb,
    // 含空数组（对应 insufficient_relevance 的证据为空）与缺失（触发顶层回退）。
    evidence: fc.array(richEvidenceArb, { maxLength: 4 }),
    evidence_mode: fc.constantFrom<string>(...RETRIEVAL_MODES, "invalid_mode", ""),
    gaps: textArb,
  },
  { requiredKeys: [] },
);

// 单个 topics 项:字符串（旧格式）或富选题对象。
const topicItemArb = fc.oneof(textArb, richTopicArb);

// 顶层 xhs_topics 载荷。
const payloadArb = fc.record(
  {
    intro: textArb,
    topics: fc.array(topicItemArb, { maxLength: 5 }),
    evidence: fc.array(sourceEvidenceArb, { maxLength: 4 }),
  },
  { requiredKeys: ["topics"] },
);

function fenced(payload: unknown): string {
  return "```xhs_topics\n" + JSON.stringify(payload) + "\n```";
}

function topicsSegment(content: string): TopicsSegment {
  const segment = parseXhsBlocks(content).find(
    (s): s is TopicsSegment => s.kind === "topics",
  );
  if (!segment) throw new Error("expected a topics segment");
  return segment;
}

test("Property 1: parse→serialize→parse 是选题/证据契约的幂等不动点", () => {
  fc.assert(
    fc.property(payloadArb, (payload) => {
      // 首次解析（对随机原始载荷归一化）。
      const segment1 = topicsSegment(fenced(payload));
      // 合法 JSON + topics 数组 ⇒ 必须走完整解析路径,而非增量/pending 降级。
      assert.notEqual(segment1.isPending, true);

      // 把首次解析结果按同样的 ```xhs_topics {JSON}``` 形态再序列化并二次解析。
      const segment2 = topicsSegment(fenced(segment1.data));

      // 不动点:两次解析结果逐字段等价（键顺序无关,deepStrictEqual 按值比较）。
      assert.deepStrictEqual(segment2.data, segment1.data);
    }),
    { numRuns: 200 },
  );
});
