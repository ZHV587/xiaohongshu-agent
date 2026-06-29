import assert from "node:assert/strict";
import test from "node:test";

import { createWorkbenchTabsInitialState } from "../src/components/thread/useWorkbenchTabsState";

test("createWorkbenchTabsInitialState starts on mock tab with no selected evidence", () => {
  assert.deepEqual(createWorkbenchTabsInitialState(), {
    rightTab: "mock",
    selectedEvidence: null,
  });
});
