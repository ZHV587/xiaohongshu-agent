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
