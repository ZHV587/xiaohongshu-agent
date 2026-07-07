import assert from "node:assert/strict";
import test from "node:test";

import {
  isXhsTraceEvent,
  reduceTraceEvents,
  toTracePresentation,
  type XhsTraceEvent,
} from "./agent-trace";

function event(overrides: Partial<XhsTraceEvent>): XhsTraceEvent {
  return {
    type: "xhs.trace.tool.completed",
    schema_version: 1,
    event_id: "event-1",
    trace_id: "trace-1",
    run_id: "run-1",
    turn_id: "turn-1",
    seq: 1,
    ts: "2026-07-03T12:00:00.000Z",
    label: "查找相关素材",
    visibility: "user",
    ...overrides,
  };
}

test("isXhsTraceEvent accepts only official custom trace events", () => {
  assert.equal(isXhsTraceEvent(event({})), true);
  assert.equal(isXhsTraceEvent({ type: "ui" }), false);
});

test("reduceTraceEvents dedupes by event_id and sorts by seq", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e3", seq: 3 }),
    event({ event_id: "e1", seq: 1 }),
    event({ event_id: "e3", seq: 3 }),
    event({ event_id: "e2", seq: 2 }),
  ]);

  assert.deepEqual(
    state.events.map((item) => item.event_id),
    ["e1", "e2", "e3"],
  );
});

test("presentation uses friendly Chinese and preserves source ids", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "开始处理" }),
    event({
      event_id: "e2",
      seq: 2,
      type: "xhs.trace.tool.completed",
      stage_id: "retrieve",
      metrics: { found_count: 12, used_count: 3 },
    }),
    event({ event_id: "e3", seq: 3, type: "xhs.trace.run.completed", label: "处理完成" }),
  ]);

  const presentation = toTracePresentation(state);

  assert.equal(presentation.traceId, "trace-1");
  assert.match(presentation.userSummary, /已完成素材核验/);
  assert.equal(presentation.userStages[0].title, "核验素材依据");
  assert.equal(presentation.userStages[0].metricsText, "找到 12 条，采用 3 条");
  assert.deepEqual(presentation.userStages[0].sourceEventIds, ["e2"]);
});

test("presentation explains what happened instead of naming a tool", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "run started" }),
    event({
      event_id: "e2",
      seq: 2,
      tool_name: "semantic_search_resources",
      label: "tool completed",
      metrics: { found_count: 12, used_count: 3 },
    }),
    event({ event_id: "e3", seq: 3, type: "xhs.trace.run.completed", label: "run completed" }),
  ]);

  const presentation = toTracePresentation(state);
  const [stage] = presentation.userStages;

  assert.equal(presentation.userSummary, "已完成素材核验：找到 12 条，采用 3 条");
  assert.equal(stage.title, "核验素材依据");
  assert.equal(stage.intent, "先确认有没有可用素材，避免凭空给建议。");
  assert.equal(stage.action, "从数据底座检索与你需求相关的笔记和历史素材。");
  assert.equal(stage.resultText, "找到 12 条相关素材，采用 3 条作为本次回答依据。");
});

test("presentation folds started and completed events into one user step", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "run started" }),
    event({
      event_id: "e2",
      seq: 2,
      type: "xhs.trace.tool.started",
      stage_id: "retrieve",
      tool_call_id: "call-1",
      tool_name: "semantic_search_resources",
      label: "tool started",
    }),
    event({
      event_id: "e3",
      seq: 3,
      type: "xhs.trace.tool.completed",
      stage_id: "retrieve",
      tool_call_id: "call-1",
      tool_name: "semantic_search_resources",
      label: "tool completed",
      metrics: { found_count: 12, used_count: 3 },
    }),
    event({ event_id: "e4", seq: 4, type: "xhs.trace.run.completed", label: "run completed" }),
  ]);

  const presentation = toTracePresentation(state);

  assert.equal(presentation.userStages.length, 1);
  assert.deepEqual(presentation.userStages[0].sourceEventIds, ["e2", "e3"]);
  assert.equal(presentation.userStages[0].statusText, "已完成");
  assert.equal(presentation.userStages[0].resultText, "找到 12 条相关素材，采用 3 条作为本次回答依据。");
});

test("each stage carries its own real state (done vs active), not one run-level verdict", () => {
  // 第一步已完成(有 completed),第二步刚开始(只有 started 无终态)。
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "run started" }),
    event({
      event_id: "e2", seq: 2, type: "xhs.trace.tool.completed",
      stage_id: "retrieve", tool_call_id: "call-1", tool_name: "semantic_search_resources",
      metrics: { found_count: 8, used_count: 3 },
    }),
    event({
      event_id: "e3", seq: 3, type: "xhs.trace.tool.started",
      stage_id: "compose", tool_call_id: "call-2", tool_name: "save_generated_topic",
    }),
  ]);

  const presentation = toTracePresentation(state);
  assert.equal(presentation.userStages.length, 2);
  assert.equal(presentation.userStages[0].state, "done", "first stage completed → done");
  assert.equal(presentation.userStages[1].state, "active", "second stage only started → active");
  assert.equal(presentation.status, "active", "run not terminated → active overall");
});

test("a failed stage surfaces as error state on that step", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "run started" }),
    event({
      event_id: "e2", seq: 2, type: "xhs.trace.tool.failed",
      stage_id: "retrieve", tool_call_id: "call-1", tool_name: "semantic_search_resources",
      status: "error",
    }),
  ]);
  const presentation = toTracePresentation(state);
  assert.equal(presentation.userStages[0].state, "error");
});

test("ordinary presentation hides engineering words", () => {
  const state = reduceTraceEvents(undefined, [
    event({ event_id: "e1", seq: 1, type: "xhs.trace.run.started", label: "run started" }),
    event({
      event_id: "e2",
      seq: 2,
      tool_name: "semantic_search_resources",
      label: "tool completed",
      metrics: { found_count: 12, used_count: 3 },
    }),
    event({ event_id: "e3", seq: 3, type: "xhs.trace.run.completed", label: "run completed" }),
  ]);

  const presentation = toTracePresentation(state);
  const visible = JSON.stringify({ summary: presentation.userSummary, stages: presentation.userStages });

  for (const word of [
    "Agent",
    "trace",
    "run",
    "tool",
    "custom",
    "debug",
    "schema",
    "payload",
    "warning",
    "error",
    "retry",
  ]) {
    assert.equal(visible.includes(word), false, `ordinary UI leaked ${word}`);
  }
  assert.match(visible, /核验素材依据/);
  assert.match(visible, /找到 12 条/);
});
