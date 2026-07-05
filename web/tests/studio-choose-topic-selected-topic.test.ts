import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

// 源码断言式(与 studio-timeline.test.ts 同风格):校验 chooseTopic 会把选中选题卡的
// 权威依据(含真实 resource_id)经 selected_topic state-update 直传 graph。
// 背景:历史根因是 chooseTopic 只发纯文本、漏传 selected_topic,导致主控拿不到真实
// resource_id 只能编造,子代理 get_resource 必然 "not found"。
const ctx = readFileSync(
  join(process.cwd(), "src", "components", "studio", "StudioContext.tsx"),
  "utf8",
);

// 抽出 chooseTopic 的函数体做局部断言,避免匹配到文件别处的同名字段。
function chooseTopicBody(): string {
  const start = ctx.indexOf("const chooseTopic = useCallback(");
  assert.notEqual(start, -1, "chooseTopic 应存在");
  const end = ctx.indexOf("const adoptNotes", start);
  assert.ok(end > start, "应能界定 chooseTopic 到 adoptNotes 之间");
  return ctx.slice(start, end);
}

test("chooseTopic 经 stateUpdate 直传 selected_topic(topic+evidence)", () => {
  const body = chooseTopicBody();
  // submitText 第二参数带 selected_topic
  assert.match(body, /submitText\(\s*`写第/);
  assert.match(body, /selected_topic:\s*\{/);
  assert.match(body, /topic:\s*topic\.title/);
  assert.match(body, /evidence:\s*selectedEvidence/);
});

test("chooseTopic 从 evidence[topic.id] 取真实 resource_id,不编造", () => {
  const body = chooseTopicBody();
  // 从 evidence map 按 topic.id 取该题的依据
  assert.match(body, /evidence\[topic\.id\]/);
  // 逐条搬 resource_id / title / summary / 时效字段(对齐后端 _clean_evidence)
  assert.match(body, /resource_id:\s*it\.resource_id/);
  assert.match(body, /title:\s*it\.title/);
  assert.match(body, /summary:\s*it\.summary/);
  assert.match(body, /source_updated_at:\s*it\.source_updated_at/);
  assert.match(body, /indexed_at:\s*it\.indexed_at/);
});

test("chooseTopic 依赖数组包含 evidence(闭包拿到最新依据)", () => {
  const body = chooseTopicBody();
  // useCallback 依赖需含 evidence,否则闭包捕获旧的空依据
  assert.match(body, /\[setSection,\s*t,\s*evidence\]/);
});
