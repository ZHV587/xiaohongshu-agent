// Feature: studio-data-integration, Property 2: 双时间字段不串位
// 对任意满足 source_updated_at ≠ indexed_at 的 ISO 时间串对，往返解析后两字段各自保值、绝不互换。
// Validates: Requirements 3.1, 3.7 （对应 studio-data-integration: 2.4）
import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";
import {
  parseXhsBlocks,
  type RichEvidence,
  type RichTopic,
  type SourceEvidence,
  type TopicsSegment,
} from "../src/lib/xhs-blocks";

const NUM_RUNS = 200;

// parseIsoTimestamp 仅保留匹配 /^\d{4}-\d{2}-\d{2}T/ 且 Date.parse 可解析的字符串。
// Date#toISOString() 产出形如 "2023-01-01T00:00:00.000Z"，恰好满足两项约束。
// 约束到合法可 ISO 化的范围（1970–2100），且用 noInvalidDate:true 禁止边界处生成
// Invalid Date（否则 .toISOString() 会抛 RangeError: Invalid time value）。
const isoDate = fc
  .date({
    min: new Date(0),
    max: new Date(Date.UTC(2100, 0, 1)),
    noInvalidDate: true,
  })
  // 双保险：即便任何边界仍漏出非法日期，也在 .toISOString() 之前过滤掉。
  .filter((d) => !Number.isNaN(d.getTime()));

// 生成一对「互不相等」的合法 ISO 时间串：[source_updated_at, indexed_at]。
const distinctIsoPair = fc
  .tuple(isoDate, isoDate)
  .filter(([a, b]) => a.getTime() !== b.getTime())
  .map(([a, b]) => [a.toISOString(), b.toISOString()] as const);

// 非空、trim 后非空的字符串（解析器要求 resource_id/title/summary 非空白）。
const nonEmpty = (prefix: string) => fc.string().map((s) => prefix + s.replace(/\s/g, "_"));

interface EvidenceSpec {
  rid: string;
  title: string;
  summary: string;
  src: string;
  idx: string;
}

const evidenceArb: fc.Arbitrary<EvidenceSpec> = fc
  .record({
    rid: nonEmpty("rid-"),
    title: nonEmpty("title-"),
    summary: nonEmpty("summary-"),
    pair: distinctIsoPair,
  })
  .map(({ rid, title, summary, pair }) => ({
    rid,
    title,
    summary,
    src: pair[0],
    idx: pair[1],
  }));

function wrapTopics(payload: unknown): string {
  return "前置说明文字\n```xhs_topics\n" + JSON.stringify(payload) + "\n```\n后置说明";
}

function firstTopicsSegment(content: string): TopicsSegment {
  const segments = parseXhsBlocks(content);
  const seg = segments.find((s): s is TopicsSegment => s.kind === "topics");
  assert.ok(seg, "应解析出 topics 片段");
  return seg;
}

test("Property 2: 富选题内证据的 source_updated_at / indexed_at 往返后保值且不互换", () => {
  fc.assert(
    fc.property(fc.array(evidenceArb, { minLength: 1, maxLength: 6 }), (specs) => {
      const payload = {
        topics: [
          {
            title: "选题标题",
            evidence: specs.map((s) => ({
              resource_id: s.rid,
              title: s.title,
              summary: s.summary,
              source_updated_at: s.src,
              indexed_at: s.idx,
            })),
          },
        ],
      };

      const seg = firstTopicsSegment(wrapTopics(payload));
      const topic = seg.data.topics[0] as RichTopic;
      assert.equal(typeof topic, "object");
      const evidence = topic.evidence ?? [];
      assert.equal(evidence.length, specs.length, "证据数量应守恒");

      evidence.forEach((ev: RichEvidence, i) => {
        const spec = specs[i];
        // 各自保值
        assert.equal(ev.source_updated_at, spec.src, "source_updated_at 应保留源端值");
        assert.equal(ev.indexed_at, spec.idx, "indexed_at 应保留索引值");
        // 绝不互换（由 src ≠ idx 保证：若串位则会等于对方）
        assert.notEqual(ev.source_updated_at, spec.idx, "source_updated_at 不得取到 indexed_at 的值");
        assert.notEqual(ev.indexed_at, spec.src, "indexed_at 不得取到 source_updated_at 的值");
      });
    }),
    { numRuns: NUM_RUNS },
  );
});

test("Property 2: 顶层共享证据(SourceEvidence)的双时间字段往返后保值且不互换", () => {
  fc.assert(
    fc.property(fc.array(evidenceArb, { minLength: 1, maxLength: 6 }), (specs) => {
      const payload = {
        topics: ["纯字符串选题"],
        evidence: specs.map((s) => ({
          resource_id: s.rid,
          title: s.title,
          summary: s.summary,
          source_updated_at: s.src,
          indexed_at: s.idx,
        })),
      };

      const seg = firstTopicsSegment(wrapTopics(payload));
      const evidence = seg.data.evidence;
      assert.equal(evidence.length, specs.length, "证据数量应守恒");

      evidence.forEach((ev: SourceEvidence, i) => {
        const spec = specs[i];
        assert.equal(ev.source_updated_at, spec.src, "source_updated_at 应保留源端值");
        assert.equal(ev.indexed_at, spec.idx, "indexed_at 应保留索引值");
        assert.notEqual(ev.source_updated_at, spec.idx, "source_updated_at 不得取到 indexed_at 的值");
        assert.notEqual(ev.indexed_at, spec.src, "indexed_at 不得取到 source_updated_at 的值");
      });
    }),
    { numRuns: NUM_RUNS },
  );
});
