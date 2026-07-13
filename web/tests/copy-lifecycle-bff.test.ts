import assert from "node:assert/strict";
import test from "node:test";

import { createCopyLifecycleGet, createCopyLifecyclePost } from "../src/app/api/backend/copies/handler";
import { createSchedulePost } from "../src/app/api/backend/schedule/handler";

const RESOURCE_ID = "11111111-1111-4111-8111-111111111111";
const user = { openId: "ou_user", isAdmin: false };

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

function lifecyclePayload() {
  return {
    resourceId: RESOURCE_ID,
    status: "candidate",
    selectedVersion: 1,
    selectedLabel: "A",
    adoptedVersion: null,
    finalizedVersion: null,
    publishedVersion: null,
    knowledgeTargetVersion: null,
    latestResourceVersion: 1,
    stateVersion: 1,
    versions: [{ resourceVersion: 1, label: "A", title: "标题", body: "正文", tags: ["#标签"], cover: "封面", note: "说明" }],
  };
}

function post(url: string, body: unknown): Request {
  return new Request(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

test("copy lifecycle BFF 按稳定 resourceId 转发 GET，且不把动态路径开放成任意内部 URL", async () => {
  const calls: unknown[][] = [];
  const handler = createCopyLifecycleGet({
    requireUser: async () => user,
    forwardToInternalServer: async (...args: unknown[]) => {
      calls.push(args);
      return json({ ok: true, lifecycle: lifecyclePayload() });
    },
  });
  const response = await handler(new Request(`http://localhost/api/backend/copies/${RESOURCE_ID}/lifecycle`));
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], `/_internal/studio/copies/${RESOURCE_ID}/lifecycle`);
  assert.equal(calls[0][1], "GET");

  const invalid = await handler(new Request("http://localhost/api/backend/copies/../../config/lifecycle"));
  assert.equal(invalid.status, 400);
  assert.equal(calls.length, 1, "非法动态路径不得转发");
});

test("copy lifecycle BFF 拒绝缺 exact snapshots 的旧成功响应", async () => {
  const handler = createCopyLifecycleGet({
    requireUser: async () => user,
    forwardToInternalServer: async () => json({ ok: true, lifecycle: { resourceId: RESOURCE_ID } }),
  });
  const response = await handler(new Request(`http://localhost/api/backend/copies/${RESOURCE_ID}/lifecycle`));
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { ok: false, error: "internal lifecycle payload is invalid" });
});

test("copy lifecycle BFF 拒绝与请求资源不一致的成功响应", async () => {
  const handler = createCopyLifecycleGet({
    requireUser: async () => user,
    forwardToInternalServer: async () => json({
      ok: true,
      lifecycle: { ...lifecyclePayload(), resourceId: "22222222-2222-4222-8222-222222222222" },
    }),
  });
  const response = await handler(new Request(`http://localhost/api/backend/copies/${RESOURCE_ID}/lifecycle`));
  assert.equal(response.status, 502);
});

test("select/revision/adopt BFF 保留精确版本与 stateVersion，并透传 409", async () => {
  const calls: Array<{ path: unknown; body: Record<string, unknown> }> = [];
  const forward = async (path: unknown, _method: unknown, _openId: unknown, body?: unknown) => {
    calls.push({ path, body: body as Record<string, unknown> });
    return json({ ok: false, error: "Conflict: stale state" }, 409);
  };
  const cases = [
    ["select", { resourceId: RESOURCE_ID, resourceVersion: 2, expectedStateVersion: 7, label: "B" }],
    ["revision", { resourceId: RESOURCE_ID, expectedResourceVersion: 3, expectedStateVersion: 8, title: "标题", body: "正文", tags: ["#标签"], cover: "封面", note: "情绪版", label: "B" }],
    ["adopt", { resourceId: RESOURCE_ID, resourceVersion: 4, expectedStateVersion: 9 }],
  ] as const;
  for (const [action, body] of cases) {
    const handler = createCopyLifecyclePost(action, { requireUser: async () => user, forwardToInternalServer: forward as never });
    const response = await handler(post(`http://localhost/api/backend/copies/${action}`, body));
    assert.equal(response.status, 409);
  }
  assert.deepEqual(calls.map((call) => call.path), [
    "/_internal/studio/copies/select",
    "/_internal/studio/copies/revision",
    "/_internal/studio/copies/adopt",
  ]);
  assert.deepEqual(calls.map((call) => call.body), cases.map(([, body]) => body));
});

test("schedule BFF 精确转发版本/并发令牌，finalDraft 可选且存在时原样转发", async () => {
  const forwarded: Record<string, unknown>[] = [];
  const handler = createSchedulePost({
    requireUser: async () => user,
    forwardToInternalServer: async (_path, _method, _openId, body) => {
      forwarded.push(body as Record<string, unknown>);
      return json({ ok: true, scheduled: { resourceVersion: 5, stateVersion: 11 } });
    },
  });
  const base = {
    resourceId: RESOURCE_ID,
    targetResourceVersion: 2,
    expectedLatestResourceVersion: 4,
    expectedStateVersion: 10,
    date: "2026-07-20",
    time: "19:00",
    account: "acc_1",
  };
  assert.equal((await handler(post("http://localhost/api/backend/schedule", base))).status, 200);
  assert.equal(forwarded[0].finalDraft, undefined);

  const finalDraft = { title: "最终标题", body: "最终正文", tags: ["#最终"], cover: "最终封面", note: "最终说明" };
  assert.equal((await handler(post("http://localhost/api/backend/schedule", { ...base, finalDraft }))).status, 400);
  const requestId = "11111111-2222-4333-8444-555555555555";
  assert.equal((await handler(post("http://localhost/api/backend/schedule", { ...base, finalDraft, requestId }))).status, 200);
  assert.deepEqual(forwarded[1], { ...base, finalDraft, requestId });
});
