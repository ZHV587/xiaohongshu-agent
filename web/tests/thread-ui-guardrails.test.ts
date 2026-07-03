import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = (...parts: string[]) =>
  readFileSync(join(process.cwd(), "src", ...parts), "utf8");

test("browser providers pass an absolute same-origin api url to the LangGraph SDK", () => {
  const threadProvider = src("providers", "Thread.tsx");
  const streamProvider = src("providers", "Stream.tsx");

  assert.match(threadProvider, /toBrowserApiUrl/);
  assert.match(streamProvider, /toBrowserApiUrl/);
});

test("ThreadContext does not carry decorative social follow/like/collect state", () => {
  const context = src("components", "thread", "ThreadContext.tsx");

  assert.doesNotMatch(
    context,
    /likeCount|isLiked|showPlusOne|collectCount|isCollected/,
  );
});

test("desktop conversation panes wrap long responses and render explicit state notes", () => {
  const creation = src("components", "studio", "CreationScreen.tsx");
  const workbench = src("components", "workbench", "WorkbenchShell.tsx");

  for (const [name, source] of [["CreationScreen", creation], ["WorkbenchShell", workbench]] as const) {
    assert.match(source, /StateNote/, `${name} should render explicit empty/loading/error notes`);
    assert.match(source, /overflowWrap:\s*"anywhere"/, `${name} should wrap long response text`);
    assert.match(source, /item\.kind === "error"/, `${name} should handle response errors explicitly`);
    assert.match(source, /响应失败，请稍后重试/, `${name} should have a visible response error fallback`);
  }
});
