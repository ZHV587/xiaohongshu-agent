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
  assert.match(presentation.userSummary, /查完/);
  assert.equal(presentation.userStages[0].title, "查找相关素材");
  assert.equal(presentation.userStages[0].metricsText, "找到 12 条，采用 3 条");
  assert.deepEqual(presentation.userStages[0].sourceEventIds, ["e2"]);
});
