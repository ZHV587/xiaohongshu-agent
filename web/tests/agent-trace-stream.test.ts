import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const streamContext = readFileSync(
  join(process.cwd(), "src", "providers", "stream-context.ts"),
  "utf8",
);
const streamProvider = readFileSync(
  join(process.cwd(), "src", "providers", "Stream.tsx"),
  "utf8",
);

test("custom stream type includes XhsTraceEvent", () => {
  assert.match(streamContext, /XhsTraceEvent/);
  assert.match(
    streamContext,
    /CustomEventType:\s*UIMessage \| RemoveUIMessage \| XhsTraceEvent/,
  );
});

test("Stream routes xhs trace events separately from UI events", () => {
  assert.match(streamProvider, /isXhsTraceEvent/);
  assert.match(streamProvider, /appendTraceEvent/);
  assert.match(streamProvider, /TraceProvider/);
});
