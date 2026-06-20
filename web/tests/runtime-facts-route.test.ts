import assert from "node:assert/strict";
import test from "node:test";

import { ApiError } from "../src/lib/server/authz";
import { createRuntimeFactsGet } from "../src/app/api/backend/runtime-facts/route";

test("runtime facts route forwards admin requests to internal health facts", async () => {
  const calls: Array<{ pathName: string; method: string; openId: string; extraHeaders: any }> = [];
  const GET = createRuntimeFactsGet({
    requireAdmin: async () => ({ openId: "ou_admin", isAdmin: true }),
    forwardToInternalServer: async (pathName, method, openId, _body, extraHeaders) => {
      calls.push({ pathName, method, openId, extraHeaders });
      return new Response(
        JSON.stringify({
          ok: true,
          modules: {
            database: { status: "healthy", source: "database", data: { outbox: { dead: 1 } } },
          },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    },
  });

  const response = await GET();
  const payload = await response.json();

  assert.equal(response.status, 200);
  assert.equal(payload.modules.database.data.outbox.dead, 1);
  assert.equal(calls[0].pathName, "/_internal/runtime-facts");
  assert.equal(calls[0].method, "GET");
  assert.equal(calls[0].openId, "ou_admin");
  assert.equal(calls[0].extraHeaders.isAdmin, true);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
});

test("runtime facts route returns auth errors when admin check rejects", async () => {
  const GET = createRuntimeFactsGet({
    requireAdmin: async () => {
      throw new ApiError(403, "Forbidden");
    },
    forwardToInternalServer: async () => {
      throw new Error("should not forward");
    },
  });

  const response = await GET();
  const payload = await response.json();

  assert.equal(response.status, 403);
  assert.equal(payload.error, "Forbidden");
});
