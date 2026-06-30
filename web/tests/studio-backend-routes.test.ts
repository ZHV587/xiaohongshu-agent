import assert from "node:assert/strict";
import test from "node:test";

import { ApiError } from "../src/lib/server/authz";
import { createAnalyticsGet } from "../src/app/api/backend/analytics/handler";
import { createCalendarGet } from "../src/app/api/backend/calendar/handler";
import { createPipelineGet } from "../src/app/api/backend/pipeline/handler";
import { createAccountsGet } from "../src/app/api/backend/accounts/handler";
import { createRecentsGet } from "../src/app/api/backend/recents/handler";
import { createTrendsGet } from "../src/app/api/backend/trends/handler";

type ForwardCall = {
  pathName: string;
  method: string;
  openId: string;
  extraHeaders: any;
  query: any;
};

function recordingForward(payload: Record<string, unknown>, calls: ForwardCall[]) {
  return (async (
    pathName: string,
    method: string,
    openId: string,
    _body: any,
    extraHeaders: any,
    query: any,
  ) => {
    calls.push({ pathName, method, openId, extraHeaders, query });
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as any;
}

test("analytics matrix overview (no account) requires admin and forwards no query", async () => {
  const calls: ForwardCall[] = [];
  const GET = createAnalyticsGet({
    requireUser: async () => {
      throw new Error("should require admin for matrix overview");
    },
    requireAdmin: async () => ({ openId: "ou_admin", isAdmin: true }),
    forwardToInternalServer: recordingForward(
      { ok: true, account: null, dashboard: [], library: [], teardown: { title: "", points: [] } },
      calls,
    ),
  });

  const response = await GET(new Request("http://localhost/api/backend/analytics"));
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.ok, true);
  assert.equal(calls[0].pathName, "/_internal/studio/analytics");
  assert.equal(calls[0].extraHeaders.isAdmin, true);
  assert.equal(calls[0].query, undefined);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});

test("analytics account view requires only user and forwards account query", async () => {
  const calls: ForwardCall[] = [];
  const GET = createAnalyticsGet({
    requireUser: async () => ({ openId: "ou_user", isAdmin: false }),
    requireAdmin: async () => {
      throw new Error("should not require admin for account view");
    },
    forwardToInternalServer: recordingForward(
      { ok: true, account: "acc_1", dashboard: [], library: [], teardown: { title: "", points: [] } },
      calls,
    ),
  });

  const response = await GET(new Request("http://localhost/api/backend/analytics?account=acc_1"));
  assert.equal(response.status, 200);
  assert.equal(calls[0].openId, "ou_user");
  assert.deepEqual(calls[0].query, { account: "acc_1" });
});

test("analytics route returns auth error without forwarding", async () => {
  const GET = createAnalyticsGet({
    requireUser: async () => {
      throw new ApiError(401, "Unauthorized");
    },
    requireAdmin: async () => {
      throw new ApiError(401, "Unauthorized");
    },
    forwardToInternalServer: async () => {
      throw new Error("should not forward when auth fails");
    },
  });

  const response = await GET(new Request("http://localhost/api/backend/analytics?account=acc_1"));
  const payload = await response.json();
  assert.equal(response.status, 401);
  assert.equal(payload.error, "Unauthorized");
  assert.equal(payload.dashboard, undefined);
});

test("calendar route forwards account query for user", async () => {
  const calls: ForwardCall[] = [];
  const GET = createCalendarGet({
    requireUser: async () => ({ openId: "ou_user", isAdmin: false }),
    forwardToInternalServer: recordingForward(
      { ok: true, account: "acc_2", month: { label: "", days: 30, firstOffset: 1 }, calendar: [] },
      calls,
    ),
  });

  const response = await GET(new Request("http://localhost/api/backend/calendar?account=acc_2"));
  assert.equal(response.status, 200);
  assert.equal(calls[0].pathName, "/_internal/studio/calendar");
  assert.deepEqual(calls[0].query, { account: "acc_2" });
});

test("pipeline route forwards to internal pipeline for user", async () => {
  const calls: ForwardCall[] = [];
  const GET = createPipelineGet({
    requireUser: async () => ({ openId: "ou_user", isAdmin: false }),
    forwardToInternalServer: recordingForward({ ok: true, account: null, queue: [] }, calls),
  });

  const response = await GET(new Request("http://localhost/api/backend/pipeline"));
  assert.equal(response.status, 200);
  assert.equal(calls[0].pathName, "/_internal/studio/pipeline");
  assert.equal(calls[0].query, undefined);
});

test("accounts route forwards to internal accounts for user", async () => {
  const calls: ForwardCall[] = [];
  const GET = createAccountsGet({
    requireUser: async () => ({ openId: "ou_user", isAdmin: false }),
    forwardToInternalServer: recordingForward(
      { ok: true, accounts: [], overview: { totalFans: 0, weekNewFans: 0, weekPosts: 0, avgHotRate: 0 } },
      calls,
    ),
  });

  const response = await GET();
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(calls[0].pathName, "/_internal/studio/accounts");
  assert.deepEqual(payload.accounts, []);
});

test("recents route forwards to internal recents for user", async () => {
  const calls: ForwardCall[] = [];
  const GET = createRecentsGet({
    requireUser: async () => ({ openId: "ou_user", isAdmin: false }),
    forwardToInternalServer: recordingForward({ ok: true, recents: [] }, calls),
  });

  const response = await GET();
  assert.equal(response.status, 200);
  assert.equal(calls[0].pathName, "/_internal/studio/recents");
  assert.equal(calls[0].openId, "ou_user");
});

test("trends route forwards to internal trends for user", async () => {
  const calls: ForwardCall[] = [];
  const GET = createTrendsGet({
    requireUser: async () => ({ openId: "ou_user", isAdmin: false }),
    forwardToInternalServer: recordingForward({ ok: true, trends: [] }, calls),
  });

  const response = await GET();
  const payload = await response.json();
  assert.equal(response.status, 200);
  assert.equal(calls[0].pathName, "/_internal/studio/trends");
  assert.deepEqual(payload.trends, []);
});

test("recents route returns auth error without forwarding", async () => {
  const GET = createRecentsGet({
    requireUser: async () => {
      throw new ApiError(403, "Forbidden");
    },
    forwardToInternalServer: async () => {
      throw new Error("should not forward when auth fails");
    },
  });

  const response = await GET();
  const payload = await response.json();
  assert.equal(response.status, 403);
  assert.equal(payload.error, "Forbidden");
  assert.equal(payload.recents, undefined);
});
