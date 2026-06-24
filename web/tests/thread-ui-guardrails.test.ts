import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const src = (...parts: string[]) =>
  readFileSync(join(process.cwd(), "src", ...parts), "utf8");

test("thread shell exposes stable main and navigation landmarks", () => {
  const thread = src("components", "thread", "index.tsx");
  const history = src("components", "thread", "history", "index.tsx");
  const chat = src("components", "thread", "ChatTimeline.tsx");

  assert.match(thread, /<main\b[^>]*aria-label="创作工作台"/);
  assert.match(history, /<nav\b[^>]*aria-label="会话历史"/);
  assert.match(chat, /<h1 className="sr-only">\{BRAND\.name\}创作工作台<\/h1>/);
});

test("right workbench is not left focusable in the mobile layout", () => {
  const thread = src("components", "thread", "index.tsx");

  assert.match(thread, /lg:grid-cols-\[minmax\(0,1fr\)_480px\]/);
  assert.match(thread, /hidden lg:flex/);
  assert.doesNotMatch(thread, /grid-cols-\[1fr_0px\]/);
});

test("command palette uses dialog semantics with labelled content", () => {
  const thread = src("components", "thread", "index.tsx");

  assert.match(thread, /@radix-ui\/react-dialog/);
  assert.match(thread, /Dialog\.Title/);
  assert.match(thread, /Dialog\.Description/);
  assert.match(thread, /aria-modal="true"/);
});

test("primary mobile controls preserve at least a 44px touch target", () => {
  const thread = src("components", "thread", "index.tsx");
  const history = src("components", "thread", "history", "index.tsx");
  const chat = src("components", "thread", "ChatTimeline.tsx");
  const composer = src("components", "thread", "ComposerPanel.tsx");
  const sheet = src("components", "ui", "sheet.tsx");
  const tooltipIconButton = src(
    "components",
    "thread",
    "tooltip-icon-button.tsx",
  );
  const sonner = src("components", "ui", "sonner.tsx");
  const globals = src("app", "globals.css");

  assert.match(thread, /min-h-12/);
  assert.match(history, /min-h-11/);
  assert.match(chat, /min-h-11/);
  assert.match(composer, /min-h-11/);
  assert.match(sheet, /size-11/);
  assert.match(tooltipIconButton, /min-h-11/);
  assert.match(sonner, /closeButton:\s*"[^"]*size-12/);
  assert.match(globals, /\[data-close-button="true"\]/);
  assert.match(globals, /min-height:\s*3rem\s*!important/);
});

test("browser providers pass an absolute same-origin api url to the LangGraph SDK", () => {
  const threadProvider = src("providers", "Thread.tsx");
  const streamProvider = src("providers", "Stream.tsx");

  assert.match(threadProvider, /toBrowserApiUrl/);
  assert.match(streamProvider, /toBrowserApiUrl/);
});

test("phone preview does not include decorative social follow like or collect actions", () => {
  const thread = src("components", "thread", "index.tsx");
  const context = src("components", "thread", "ThreadContext.tsx");

  assert.doesNotMatch(thread, />\s*关注\s*<\/button>/);
  assert.doesNotMatch(
    thread,
    /likeCount|isLiked|showPlusOne|collectCount|isCollected/,
  );
  assert.doesNotMatch(thread, /\bHeart\b|\bStar\b/);
  assert.doesNotMatch(
    context,
    /likeCount|isLiked|showPlusOne|collectCount|isCollected/,
  );
});
