import assert from "node:assert/strict";
import test from "node:test";

import { resolveStandaloneOutput } from "../next-config-options.mjs";

test("keeps standalone output for Linux container builds", () => {
  assert.equal(resolveStandaloneOutput("linux"), "standalone");
});

test("disables standalone output for Windows local builds", () => {
  assert.equal(resolveStandaloneOutput("win32"), undefined);
});
