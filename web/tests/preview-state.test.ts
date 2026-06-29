import assert from "node:assert/strict";
import test from "node:test";

import { createPreviewInitialState } from "../src/components/thread/usePreviewState";

test("createPreviewInitialState keeps the current phone preview defaults", () => {
  const state = createPreviewInitialState();

  assert.equal(state.viewMode, "detail");
  assert.equal(state.isEditingText, false);
  assert.equal(state.carouselIndex, 0);
  assert.equal(state.carouselImages.length, 3);
  assert.match(state.carouselImages[0], /images\.unsplash\.com/);
});
