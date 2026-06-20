import assert from "node:assert/strict";
import test from "node:test";

import { runtimeFactRows } from "../src/components/thread/history/runtime-facts-format";

test("formats runtime data without arbitrary backend fields", () => {
  const rows = runtimeFactRows({
    status: "degraded",
    source: "database",
    observed_at: "2026-06-20T00:00:00Z",
    stale_after_seconds: 30,
    data: { outbox: { dead: 1 }, payload: "secret" },
    error: { code: "OUTBOX_BLOCKED", summary: "Outbox needs attention" },
  });

  assert.deepEqual(rows, [["dead", "1"]]);
  assert.equal(JSON.stringify(rows).includes("secret"), false);
});
