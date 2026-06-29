import assert from "node:assert/strict";
import test from "node:test";

import {
  createFeishuWorkspaceInitialState,
  pickInitialChatId,
  shouldFetchFeishuChats,
} from "../src/components/thread/useFeishuWorkspaceState";

test("createFeishuWorkspaceInitialState keeps Feishu workspace defaults", () => {
  assert.deepEqual(createFeishuWorkspaceInitialState(), {
    feishuChats: [],
    selectedChatId: "",
    isFetchingChats: false,
    isSendingNotification: false,
    isFeishuActionPending: false,
  });
});

test("shouldFetchFeishuChats fetches only when Feishu tab opens without chats", () => {
  assert.equal(shouldFetchFeishuChats("feishu", 0), true);
  assert.equal(shouldFetchFeishuChats("feishu", 1), false);
  assert.equal(shouldFetchFeishuChats("mock", 0), false);
  assert.equal(shouldFetchFeishuChats("evidence", 0), false);
});

test("pickInitialChatId selects the first chat or clears selection", () => {
  assert.equal(
    pickInitialChatId([
      { chat_id: "chat-1", name: "一群" },
      { chat_id: "chat-2", name: "二群" },
    ]),
    "chat-1",
  );
  assert.equal(pickInitialChatId([]), "");
});
