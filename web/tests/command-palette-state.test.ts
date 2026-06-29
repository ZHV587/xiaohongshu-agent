import assert from "node:assert/strict";
import test from "node:test";

import { getCommandPaletteKeyboardAction } from "../src/components/thread/useCommandPaletteState";

test("getCommandPaletteKeyboardAction toggles on Ctrl+P and Meta+P", () => {
  assert.equal(
    getCommandPaletteKeyboardAction({ ctrlKey: true, metaKey: false, key: "p" }),
    "toggle",
  );
  assert.equal(
    getCommandPaletteKeyboardAction({ ctrlKey: false, metaKey: true, key: "P" }),
    "toggle",
  );
});

test("getCommandPaletteKeyboardAction closes on Escape", () => {
  assert.equal(
    getCommandPaletteKeyboardAction({
      ctrlKey: false,
      metaKey: false,
      key: "Escape",
    }),
    "close",
  );
});

test("getCommandPaletteKeyboardAction ignores plain p and unrelated shortcuts", () => {
  assert.equal(
    getCommandPaletteKeyboardAction({ ctrlKey: false, metaKey: false, key: "p" }),
    null,
  );
  assert.equal(
    getCommandPaletteKeyboardAction({ ctrlKey: true, metaKey: false, key: "k" }),
    null,
  );
});
