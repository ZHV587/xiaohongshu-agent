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

test("chooseTopic 依赖数组包含本地编辑状态/evidence/versions/topicId(闭包拿到最新依据/文案/绑定选题)", () => {
  const body = chooseTopicBody();
  // 依赖需含 topicId:守卫要按"是否同一选题"判定,闭包必须读到当前绑定的 topicId,否则读旧值误判。
  assert.match(body, /\[setLocalEditState,\s*setSection,\s*t,\s*evidence,\s*versions,\s*topicId\]/);
});

test("chooseTopic 守卫按选题区分:只在重进同一选题且已有内容时不重跑", () => {
  const body = chooseTopicBody();
  // 守卫必须**同时**满足"同一选题(sameTopicAsLoaded)"与"已有文案(alreadyHasCopy)"才 early-return。
  // 只看 alreadyHasCopy(不看选题)是老 bug:生成过 A 后点 B 也被误拦,B 永不生成、显示 A 的旧稿。
  assert.match(body, /sameTopicAsLoaded\s*=\s*topicId === topic\.id/);
  assert.match(body, /alreadyHasCopy\s*=\s*Boolean\(/);
  assert.match(body, /if\s*\(sameTopicAsLoaded && alreadyHasCopy\)\s*return;/);
  const guardIdx = body.indexOf("if (sameTopicAsLoaded && alreadyHasCopy) return;");
  const submitIdx = body.indexOf("submitText(");
  assert.ok(guardIdx !== -1 && submitIdx !== -1 && guardIdx < submitIdx, "守卫应在 submitText 之前");
});

test("chooseTopic 换选题时先清空上一个选题的残留草稿", () => {
  const body = chooseTopicBody();
  // 换不同选题(!sameTopicAsLoaded)→ 清 draftTitle/draftContent/tags/cover,避免生成期间显示旧选题正文。
  assert.match(body, /if\s*\(!sameTopicAsLoaded\)\s*\{/);
  assert.match(body, /t\.setDraftTitle\(""\)/);
  assert.match(body, /t\.setDraftContent\(""\)/);
});

test("chooseTopic 绑定选题/切 section 在守卫之前(总执行,与是否生成无关)", () => {
  const body = chooseTopicBody();
  // 现实现固定切到创作屏 setSection("create")(历史 goSection 变量已重构掉);断言它在守卫之前,
  // 保证重进同一选题也能先切过去看旧内容,再由守卫决定是否重跑生成。
  const setSectionIdx = body.indexOf('setSection("create")');
  const guardIdx = body.indexOf("if (sameTopicAsLoaded && alreadyHasCopy) return;");
  assert.ok(setSectionIdx !== -1 && setSectionIdx < guardIdx, "setSection 应在守卫之前,重进也能切过去看旧内容");
});
