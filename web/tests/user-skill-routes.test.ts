import assert from "node:assert/strict";
import test from "node:test";

import { ApiError } from "../src/lib/server/authz";
import {
  createUserSkillActionPost,
  createUserSkillDetailGet,
  createUserSkillsGet,
  createUserSkillsPost,
  createUserSkillsValidatePost,
  createUserSkillVersionPatch,
} from "../src/app/api/skills/handler";

type Call = { path: string; method: string; openId: string; body: any; query: any };

function deps(calls: Call[]) {
  return {
    requireUser: async () => ({ openId: "ou-user", isAdmin: false }),
    forwardToInternalServer: (async (
      path: string,
      method: string,
      openId: string,
      body: any,
      _headers: any,
      query: any,
    ) => {
      calls.push({ path, method, openId, body, query });
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as any,
  };
}

const context = { params: Promise.resolve({ skillId: "skill-from-path" }) };

test("all user Skill BFF routes reject before forwarding and return no-store", async () => {
  let forwarded = 0;
  const denied = {
    requireUser: async () => {
      throw new ApiError(401, "Unauthorized");
    },
    forwardToInternalServer: (async () => {
      forwarded += 1;
      throw new Error("must not forward");
    }) as any,
  };
  const routes: Array<() => Promise<Response>> = [
    () => createUserSkillsGet(denied)(new Request("http://x/api/skills")),
    () => createUserSkillsPost(denied)(new Request("http://x/api/skills", { method: "POST", body: "{}" })),
    () => createUserSkillsValidatePost(denied)(new Request("http://x/api/skills/validate", { method: "POST", body: "{}" })),
    () => createUserSkillDetailGet(denied)(new Request("http://x"), context),
    () => createUserSkillVersionPatch(denied)(new Request("http://x", { method: "PATCH", body: "{}" }), context),
    ...["publish", "rollback", "enable", "disable", "archive"].map(
      (action) => () =>
        createUserSkillActionPost(denied, action)(
          new Request("http://x", { method: "POST", body: "{}" }),
          context,
        ),
    ),
  ];

  for (const invoke of routes) {
    const response = await invoke();
    assert.equal(response.status, 401);
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  }
  assert.equal(forwarded, 0);
});

test("collection, validation and detail routes forward through authenticated internal client", async () => {
  const calls: Call[] = [];
  const d = deps(calls);
  const definition = {
    displayName: "结构压缩",
    description: "需要压缩结构时使用",
    instructions: "删除重复信息",
  };

  const list = await createUserSkillsGet(d)(
    new Request("http://x/api/skills?includeArchived=true"),
  );
  await createUserSkillsPost(d)(
    new Request("http://x/api/skills", { method: "POST", body: JSON.stringify(definition) }),
  );
  await createUserSkillsValidatePost(d)(
    new Request("http://x/api/skills/validate", { method: "POST", body: JSON.stringify(definition) }),
  );
  await createUserSkillDetailGet(d)(new Request("http://x"), context);

  assert.equal(list.headers.get("Cache-Control"), "no-store");
  assert.deepEqual(calls.map((call) => call.path), [
    "/_internal/user-skills/list",
    "/_internal/user-skills/create",
    "/_internal/user-skills/validate",
    "/_internal/user-skills/detail",
  ]);
  assert.deepEqual(calls[0].query, { includeArchived: "true" });
  assert.deepEqual(calls[3].query, { skillId: "skill-from-path" });
  assert.equal(calls[1].openId, "ou-user");
});

test("version and action routes bind path Skill id and cannot be spoofed by body", async () => {
  const calls: Call[] = [];
  const d = deps(calls);
  await createUserSkillVersionPatch(d)(
    new Request("http://x", {
      method: "PATCH",
      body: JSON.stringify({ skillId: "spoofed", expectedLatestVersion: 1 }),
    }),
    context,
  );
  for (const action of ["publish", "rollback", "enable", "disable", "archive"]) {
    const response = await createUserSkillActionPost(d, action)(
      new Request("http://x", { method: "POST", body: "" }),
      context,
    );
    assert.equal(response.headers.get("Cache-Control"), "no-store");
  }

  assert.equal(calls[0].body.skillId, "skill-from-path");
  assert.deepEqual(
    calls.slice(1).map((call) => call.path),
    ["publish", "rollback", "enable", "disable", "archive"].map(
      (action) => `/_internal/user-skills/${action}`,
    ),
  );
  for (const call of calls) assert.equal(call.body.skillId, "skill-from-path");
});

test("malformed BFF JSON is rejected without forwarding", async () => {
  const calls: Call[] = [];
  const response = await createUserSkillsPost(deps(calls))(
    new Request("http://x", { method: "POST", body: "{" }),
  );
  assert.equal(response.status, 400);
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  assert.equal((await response.json()).code, "SKILL_INVALID_JSON");
  assert.equal(calls.length, 0);
});
