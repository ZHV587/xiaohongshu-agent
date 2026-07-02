import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";

import { ApiError, isAdminOpenId, type CurrentServerUser } from "../src/lib/server/authz";
import { signJwt, verifyJwt } from "../src/lib/server/jwt";
import { createAccountsGet } from "../src/app/api/backend/accounts/handler";
import { createRecentsGet } from "../src/app/api/backend/recents/handler";
import { createTrendsGet } from "../src/app/api/backend/trends/handler";
import { createPipelineGet, createPipelinePost } from "../src/app/api/backend/pipeline/handler";
import { createCalendarGet } from "../src/app/api/backend/calendar/handler";
import { createAnalyticsGet } from "../src/app/api/backend/analytics/handler";
import { createSchedulePost } from "../src/app/api/backend/schedule/handler";
import { createBackfillPost } from "../src/app/api/backend/backfill/handler";

// Feature: studio-data-integration, Property 14: 无效凭据拒绝且不泄露数据
// Validates: Requirements 3.1, 3.7 (studio-data-integration 17.2, 17.3)
//
// 对任意 无 cookie / 无效 / 过期 JWT 凭据：BFF studio 读/写路由响应 401 或 403，
// 响应体不含任何业务字段或令牌，且（以 spy 断言）拒绝发生在转发到内部后端之前——
// 即 internal-client 从未被调用。
//
// 设计决策 D6：P14 是合法属性测试——鉴权守卫的拒绝先于转发；对 internal-client 注入
// spy 断言「被拒时未发起后端调用」，使其不依赖任何真实后端响应（满足 R3.5 (c)）。
//
// 被测真实逻辑：
//  - server/jwt.ts::verifyJwt —— 对畸形/伪造/过期 JWT 的真实拒绝判定（安全核心）。
//  - authz.ts::requireUser/requireAdmin 的鉴权语义（此处以等价守卫驱动，因 Next 的
//    cookies() 无法在 node:test 环境取值；守卫逻辑逐行对齐 authz.ts，使用真实 verifyJwt /
//    ApiError / isAdminOpenId）。
//  - 各 studio handler + apiErrorResponse —— 拒绝时的响应形态与「不转发」闸门。

// 测试专用共享密钥（对齐 getFeishuConfig().jwtSecret 的角色）。
const TEST_SECRET = "p14-test-secret-用于签发过期与合法签名的-token";

// ── 等价鉴权守卫：逐行对齐 authz.ts 的 requireUser/requireAdmin，仅把 cookie 取值替换为
//    直接注入的 token（cookies() 依赖 Next 请求上下文，无法在单测里取值）。 ──
function makeGuards(token: string | undefined) {
  const requireUser = async (): Promise<CurrentServerUser> => {
    if (!token) throw new ApiError(401, "Unauthorized");
    const payload = verifyJwt(token, TEST_SECRET);
    if (!payload?.sub) throw new ApiError(401, "Unauthorized");
    return {
      openId: payload.sub,
      name: payload.name,
      isAdmin: isAdminOpenId(payload.sub),
    };
  };
  const requireAdmin = async (): Promise<CurrentServerUser> => {
    const user = await requireUser();
    if (!user.isAdmin) throw new ApiError(403, "Forbidden");
    return user;
  };
  return { requireUser, requireAdmin };
}

// ── internal-client 转发 spy：记录是否被调用；若被误调用则返回“满载业务字段+令牌”的
//    200 响应，使任何泄露都会被响应形态断言二次捕获。 ──
type ForwardSpy = {
  state: { called: boolean; calls: Array<{ pathName: string; method: string }> };
  forward: (
    pathName: string,
    method: "GET" | "POST",
    openId: string,
    extraBody?: unknown,
    extraHeaders?: unknown,
    query?: unknown,
  ) => Promise<Response>;
};

const LEAK_TOKEN = "SECRET-TOKEN-LEAK";
const LEAK_MARK = "leak";

function makeForwardSpy(): ForwardSpy {
  const state = { called: false, calls: [] as Array<{ pathName: string; method: string }> };
  const forward = (async (pathName: string, method: "GET" | "POST") => {
    state.called = true;
    state.calls.push({ pathName, method });
    return new Response(
      JSON.stringify({
        ok: true,
        accounts: [{ id: LEAK_MARK }],
        overview: { totalFans: 999, weekNewFans: 1, weekPosts: 1, avgHotRate: 1 },
        recents: [{ id: LEAK_MARK }],
        trends: [{ id: LEAK_MARK }],
        dashboard: [{ v: 1 }],
        library: [{ id: LEAK_MARK }],
        queue: [{ id: LEAK_MARK }],
        calendar: [{ d: 1 }],
        versions: { A: { title: LEAK_MARK } },
        token: LEAK_TOKEN,
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  }) as ForwardSpy["forward"];
  return { state, forward };
}

// ── 受守卫的 studio 路由清单（读 + 写），覆盖 requireUser 与 requireAdmin 两类闸门。 ──
// 各 handler 的参数形态不一（无参 / 需 Request）；用「需 Request」的统一签名承接：
// 无参 handler 属于其子类型（少参可赋值给多参），需 Request 的直接匹配。
type HandlerFn = (req: Request) => Promise<Response>;

type RouteCase = {
  name: string;
  build: (g: ReturnType<typeof makeGuards>, f: ForwardSpy["forward"]) => HandlerFn;
  call: (h: HandlerFn) => Promise<Response>;
};

const postInit = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
  headers: { "Content-Type": "application/json" },
});

const ROUTES: RouteCase[] = [
  {
    name: "accounts(read/requireUser)",
    build: (g, f) => createAccountsGet({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) => h(new Request("http://localhost/api/backend/accounts")),
  },
  {
    name: "recents(read/requireUser)",
    build: (g, f) => createRecentsGet({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) => h(new Request("http://localhost/api/backend/recents")),
  },
  {
    name: "trends(read/requireUser)",
    build: (g, f) => createTrendsGet({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) => h(new Request("http://localhost/api/backend/trends")),
  },
  {
    name: "pipeline(read/requireUser)",
    build: (g, f) => createPipelineGet({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) => h(new Request("http://localhost/api/backend/pipeline")),
  },
  {
    name: "calendar(read/requireUser)",
    build: (g, f) => createCalendarGet({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) => h(new Request("http://localhost/api/backend/calendar?account=acc_1")),
  },
  {
    name: "analytics-account(read/requireUser)",
    build: (g, f) =>
      createAnalyticsGet({ requireUser: g.requireUser, requireAdmin: g.requireAdmin, forwardToInternalServer: f }),
    call: (h) => h(new Request("http://localhost/api/backend/analytics?account=acc_1")),
  },
  {
    name: "analytics-matrix(read/requireAdmin)",
    build: (g, f) =>
      createAnalyticsGet({ requireUser: g.requireUser, requireAdmin: g.requireAdmin, forwardToInternalServer: f }),
    call: (h) => h(new Request("http://localhost/api/backend/analytics")),
  },
  {
    name: "schedule(write/requireUser)",
    build: (g, f) => createSchedulePost({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) =>
      h(
        new Request(
          "http://localhost/api/backend/schedule",
          postInit({ resourceId: "r1", date: "2025-01-01", time: "10:00", account: "acc_1" }),
        ),
      ),
  },
  {
    name: "backfill(write/requireUser)",
    build: (g, f) => createBackfillPost({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) =>
      h(new Request("http://localhost/api/backend/backfill", postInit({ resourceId: "r1", metrics: { views: 1 } }))),
  },
  {
    name: "pipeline-advance(write/requireUser)",
    build: (g, f) => createPipelinePost({ requireUser: g.requireUser, forwardToInternalServer: f }),
    call: (h) =>
      h(new Request("http://localhost/api/backend/pipeline", postInit({ resourceId: "r1", toStage: "measured" }))),
  },
];

// ── 无效凭据生成器 ──
type Cred = { kind: string; token: string | undefined };

const b64url = (s: string): string => Buffer.from(s, "utf8").toString("base64url");

// 结构合法但非 HS256/伪造/过期 —— 用于构造“看似 JWT 实则无效”的凭据。
function assemble(header: unknown, payload: unknown, sig: string): string {
  return `${b64url(JSON.stringify(header))}.${b64url(JSON.stringify(payload))}.${sig}`;
}

// 无 cookie。
const noneArb: fc.Arbitrary<Cred> = fc.constant({ kind: "none", token: undefined });

// 随机垃圾串（可能无点、可能像 token）。
const garbageArb: fc.Arbitrary<Cred> = fc.string({ maxLength: 300 }).map((token) => ({ kind: "garbage", token }));

// 段数错误（≠3 段）。
const segmentsArb: fc.Arbitrary<Cred> = fc
  .array(fc.string({ maxLength: 40 }), { minLength: 0, maxLength: 5 })
  .filter((parts) => parts.length !== 3)
  .map((parts) => ({ kind: "segments", token: parts.join(".") }));

// 结构完整但 alg 非 HS256（none/RS256/…），verifyJwt 必拒。
const wrongAlgArb: fc.Arbitrary<Cred> = fc
  .record({ alg: fc.constantFrom("none", "RS256", "HS512", "ES256", "HS384"), sub: fc.string({ maxLength: 24 }) })
  .map(({ alg, sub }) => {
    const now = Math.floor(Date.now() / 1000);
    return { kind: "alg", token: assemble({ alg, typ: "JWT" }, { sub, exp: now + 3600, iat: now }, "deadbeef") };
  });

// HS256 结构合法、未过期，但用错误密钥签名 → 签名校验失败。
const badSigArb: fc.Arbitrary<Cred> = fc
  .record({ sub: fc.string({ minLength: 1, maxLength: 24 }), salt: fc.string({ maxLength: 16 }) })
  .map(({ sub, salt }) => ({ kind: "badsig", token: signJwt({ sub }, `wrong-secret-${salt}`) }));

// 用正确密钥签名但已过期（结构+签名均合法，仅 exp 在过去）。
const expiredArb: fc.Arbitrary<Cred> = fc
  .record({
    sub: fc.string({ minLength: 1, maxLength: 24 }),
    name: fc.option(fc.string({ maxLength: 20 }), { nil: undefined }),
    age: fc.integer({ min: 1, max: 100_000 }),
  })
  .map(({ sub, name, age }) => ({ kind: "expired", token: signJwt({ sub, name }, TEST_SECRET, -age) }));

// 带 token 的无效凭据（用于直接验证 verifyJwt 的拒绝）。
const tokenCredArb = fc.oneof(garbageArb, segmentsArb, wrongAlgArb, badSigArb, expiredArb);
// 全部无效凭据（含无 cookie，用于端到端路由断言）。
const anyCredArb = fc.oneof(noneArb, tokenCredArb);

// 业务字段/令牌键名——响应体中任一存在即视为泄露。
const BUSINESS_KEYS = [
  "accounts",
  "overview",
  "recents",
  "trends",
  "dashboard",
  "library",
  "teardown",
  "queue",
  "calendar",
  "month",
  "versions",
  "token",
  "jwt",
  "sub",
  "openId",
  "configs",
  "ok",
];

test("Property 14: server/jwt.ts verifyJwt 拒绝一切无效/过期/伪造凭据（返回 null）", () => {
  fc.assert(
    fc.property(tokenCredArb, (cred) => {
      const payload = verifyJwt(cred.token as string, TEST_SECRET);
      // 随机垃圾串极小概率恰好构成对 TEST_SECRET 的合法签名 —— 排除该退化例。
      if (cred.kind === "garbage") fc.pre(payload === null);
      assert.equal(payload, null, `无效凭据(${cred.kind})必须被 verifyJwt 拒绝`);
    }),
    { numRuns: 200 },
  );
});

test("Property 14: 无效凭据 → 路由 401/403、体内无业务字段/令牌、且未转发内部后端", async () => {
  await fc.assert(
    fc.asyncProperty(anyCredArb, fc.integer({ min: 0, max: ROUTES.length - 1 }), async (cred, routeIdx) => {
      // 仅测真正应被拒的凭据（守卫的拒绝条件：无 token 或 verifyJwt 无有效 sub）。
      fc.pre(cred.token === undefined || !verifyJwt(cred.token, TEST_SECRET)?.sub);

      const route = ROUTES[routeIdx];
      const { state, forward } = makeForwardSpy();
      const guards = makeGuards(cred.token);
      const handler = route.build(guards, forward);

      const res = await route.call(handler);

      // 1) 状态必为 401 或 403。
      assert.ok(
        res.status === 401 || res.status === 403,
        `${route.name}/${cred.kind} 应返回 401 或 403，实际 ${res.status}`,
      );

      // 2) 拒绝先于转发：internal-client 从未被调用。
      assert.equal(state.called, false, `${route.name}/${cred.kind} 被拒时不得转发内部后端`);

      // 3) 响应体只含 error，无任何业务字段/令牌。
      const body = (await res.json()) as Record<string, unknown>;
      assert.deepEqual(Object.keys(body).sort(), ["error"], `${route.name}/${cred.kind} 响应体应只含 error 字段`);
      assert.equal(typeof body.error, "string");
      for (const key of BUSINESS_KEYS) {
        assert.equal(body[key], undefined, `${route.name}/${cred.kind} 响应体不得含业务字段/令牌: ${key}`);
      }
      const serialized = JSON.stringify(body);
      assert.ok(!serialized.includes(LEAK_TOKEN), `${route.name}/${cred.kind} 响应体不得含令牌`);
      assert.ok(!serialized.includes(LEAK_MARK), `${route.name}/${cred.kind} 响应体不得含业务数据`);
    }),
    { numRuns: 200 },
  );
});
