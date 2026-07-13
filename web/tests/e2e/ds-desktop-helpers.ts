import { expect, type Page, type Route, type TestInfo } from "@playwright/test";

type FixtureMode = "dense" | "empty";

export type Diagnostics = {
  pageErrors: string[];
  consoleErrors: string[];
  failedRequests: string[];
};

const topicEvidence = {
  resource_id: "res-camp-001",
  resource_version: 3,
  type: "爆款笔记",
  asset_kind: "example",
  source_kind: "user_adopted",
  niche: "户外露营",
  title: "露营装备清单高收藏样本",
  summary: "评论集中在轻量化、收纳和新手避坑。",
  score: 0.92,
  quality: 0.84,
  relevance: 0.88,
  freshness: 0.76,
  performance: 0.81,
  retrieval_sources: ["semantic", "keyword"],
  source_updated_at: "2026-07-01T00:00:00Z",
  indexed_at: "2026-07-02T00:00:00Z",
  why_selected: "与用户输入的露营装备选题高度相关，且收藏表现高。",
};

export const fixtureMessages = [
  { id: "m-human-1", type: "human", content: "帮我按露营装备方向出 3 个小红书选题" },
  {
    id: "m-ai-tool-1",
    type: "ai",
    content: "",
    tool_calls: [{ id: "call-search-1", name: "retrieve_knowledge", args: { query: "露营装备 新手 避坑" } }],
  },
  {
    id: "m-tool-1",
    type: "tool",
    name: "retrieve_knowledge",
    tool_call_id: "call-search-1",
    content: JSON.stringify({ retrieval_mode: "hybrid", evidence: [topicEvidence] }),
  },
  {
    id: "m-ai-final-1",
    type: "ai",
    content: [
      "```xhs_topics",
      JSON.stringify({
        topics: [
          {
            title: "第一次露营别乱买：这 7 件装备先准备",
            rationale: "新手高频痛点 · 收藏导向强",
            hotRate: 86,
            angle: "新手避坑",
            kw: "露营 装备 清单 新手",
            emotional: "省钱安心",
            retrieval_mode: "hybrid",
            evidence: [topicEvidence],
          },
          {
            title: "露营收纳怎么做才不崩溃",
            rationale: "场景强 · 评论互动空间大",
            hotRate: 78,
            angle: "收纳整理",
            kw: "露营 收纳 装备",
            retrieval_mode: "hybrid",
            evidence: [topicEvidence],
          },
          {
            title: "周末轻露营，一包就能出发",
            rationale: "低门槛 · 适合转化清单",
            hotRate: 72,
            angle: "轻量出行",
            kw: "轻露营 周末 装备",
            retrieval_mode: "hybrid",
            evidence: [topicEvidence],
          },
        ],
        evidence: [topicEvidence],
      }),
      "```",
      "```xhs_copy",
      JSON.stringify({
        resource_id: "11111111-1111-1111-1111-111111111111",
        versions: [
          {
            label: "版本 A",
            title: "第一次露营别乱买",
            body: "第一次露营真的别一上来就买一堆。先把睡眠、照明、收纳、防潮这几件事解决，体验会稳定很多。\n\n1. 睡垫比帐篷更影响睡得好不好\n2. 头灯比氛围灯更实用\n3. 收纳袋按场景分，比按品类分更省心\n\n收藏起来，周末出发前照着检查。",
            tags: ["露营装备", "新手露营", "露营清单", "户外生活", "周末露营"],
            cover: "第一次露营别乱买",
          },
          {
            label: "版本 B",
            title: "露营装备新手清单",
            body: "新手露营最怕买了很多，却到现场发现真正缺的是基础体验。我的建议是先从防潮、睡眠、照明、收纳四件事入手。",
            tags: ["露营", "装备清单", "新手避坑"],
            cover: "新手露营清单",
          },
        ],
      }),
      "```",
      "已基于数据底座生成选题与草稿，右侧已进入编辑器。",
    ].join("\n"),
  },
];

const denseData = {
  analytics: {
    dashboard: [
      { label: "总浏览", value: "12.8w", unit: "次", delta: 12, tone: "coral", icon: "eye" },
      { label: "收藏", value: "8,420", unit: "次", delta: 8, tone: "success", icon: "bookmark" },
      { label: "互动率", value: 18, unit: "%", delta: 3, tone: "topic", icon: "activity" },
      { label: "新增粉丝", value: 936, unit: "人", delta: 6, tone: "neutral", icon: "user-plus" },
    ],
    library: [
      { id: 1, title: "露营装备新手清单", angle: "新手避坑", hot: 86, likes: "1.2w", saves: "8600", status: "已发布" },
      { id: 2, title: "周末轻露营打包法", angle: "轻量出行", hot: 73, likes: "8600", saves: "4200", status: "排期中" },
    ],
    teardown: {
      title: "露营装备新手清单",
      points: [
        { label: "钩子", detail: "用第一次露营踩坑切入，降低理解成本。" },
        { label: "结构", detail: "按睡眠、照明、收纳、防潮分组。" },
      ],
    },
  },
  calendar: {
    month: { label: "2026 年 7 月", days: 31, firstOffset: 3 },
    calendar: [
      { date: 6, items: [{ t: "露营清单", time: "19:00", tone: "coral", acct: "A" }] },
      { date: 12, items: [{ t: "收纳教程", time: "20:30", tone: "topic", acct: "B" }] },
    ],
  },
  accounts: {
    accounts: [
      { id: "acct-a", handle: "露营研究所", niche: "户外", fans: "8.2w", fansNum: 82000, dFans: 360, posts: 4, hot: 38, status: "主力", initial: "露", tone: "coral" },
      { id: "acct-b", handle: "周末生活家", niche: "生活方式", fans: "3.1w", fansNum: 31000, dFans: 120, posts: 3, hot: 24, status: "成长", initial: "周", tone: "topic" },
    ],
  },
  pipeline: {
    queue: [
      { id: "q1", resourceId: "11111111-1111-1111-1111-111111111111", title: "露营清单", acct: "露", time: "7/6 19:00", stage: "scheduled" },
      { id: "q2", resourceId: "22222222-2222-2222-2222-222222222222", title: "收纳教程", acct: "周", link: "https://xhs.example/note/1", stage: "published" },
    ],
  },
  trends: {
    trends: [
      { tag: "轻露营", heat: "热", note: "周末短途内容上升", rising: 28, tone: "hot" },
      { tag: "户外收纳", heat: "升", note: "清单类收藏强", rising: 19, tone: "topic" },
    ],
  },
};

const emptyData = {
  analytics: { dashboard: [], library: [], teardown: { title: "", points: [] } },
  calendar: { month: { label: "2026 年 7 月", days: 31, firstOffset: 3 }, calendar: [] },
  accounts: { accounts: [] },
  pipeline: { queue: [] },
  trends: { trends: [] },
};

function threadState(mode: FixtureMode) {
  const messages = mode === "dense" ? fixtureMessages : [];
  return {
    values: { messages },
    checkpoint: { thread_id: "fixture-thread", checkpoint_id: "checkpoint-1", checkpoint_ns: "" },
    metadata: {},
    next: [],
    tasks: [],
    created_at: "2026-07-02T10:00:00.000Z",
  };
}

function threadSearch(mode: FixtureMode) {
  if (mode === "empty") return [];
  return [
    {
      thread_id: "fixture-thread",
      created_at: "2026-07-02T10:00:00.000Z",
      updated_at: "2026-07-02T10:10:00.000Z",
      metadata: { graph_id: "agent" },
      values: { messages: fixtureMessages },
      status: "idle",
    },
  ];
}

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}

async function fulfillSse(route: Route) {
  await route.fulfill({
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: [
      "event: values",
      `data: ${JSON.stringify({ messages: fixtureMessages })}`,
      "",
      "event: end",
      "data: {}",
      "",
    ].join("\n"),
  });
}

export async function installDsMocks(page: Page, mode: FixtureMode = "dense") {
  const data = mode === "dense" ? denseData : emptyData;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/me") {
      return fulfillJson(route, { ok: true, user: { openId: "ou_e2e_fixture", name: "测试用户", team: "内容中台", handle: "露营研究所", fans: "8.2w", isAdmin: true } });
    }
    if (path === "/api/info") return fulfillJson(route, { ok: true, assistant_id: "agent" });
    if (path === "/api/threads/search") return fulfillJson(route, threadSearch(mode));
    if (path === "/api/threads/fixture-thread/history") return fulfillJson(route, [threadState(mode)]);
    if (path === "/api/threads/fixture-thread/state") return fulfillJson(route, threadState(mode));
    if (path.endsWith("/runs/stream") || path === "/api/runs/stream") return fulfillSse(route);

    if (path === "/api/backend/analytics") return fulfillJson(route, { ok: true, ...data.analytics });
    if (path === "/api/backend/calendar") return fulfillJson(route, { ok: true, ...data.calendar });
    if (path === "/api/backend/accounts") return fulfillJson(route, { ok: true, ...data.accounts });
    if (path === "/api/backend/pipeline" && request.method() === "GET") return fulfillJson(route, { ok: true, ...data.pipeline });
    if (path === "/api/backend/pipeline") return fulfillJson(route, { ok: true });
    if (path === "/api/backend/trends") return fulfillJson(route, { ok: true, ...data.trends });
    if (path === "/api/backend/schedule" || path === "/api/backend/backfill") return fulfillJson(route, { ok: true });

    return fulfillJson(route, { ok: true });
  });
}

export function captureDiagnostics(page: Page): Diagnostics {
  const diagnostics: Diagnostics = { pageErrors: [], consoleErrors: [], failedRequests: [] };
  page.on("pageerror", (error) => diagnostics.pageErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") diagnostics.consoleErrors.push(message.text());
  });
  page.on("requestfailed", (request) => {
    const errorText = request.failure()?.errorText ?? "";
    if (errorText === "net::ERR_ABORTED") return;
    diagnostics.failedRequests.push(`${request.method()} ${request.url()} ${errorText}`.trim());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) diagnostics.failedRequests.push(`${response.status()} ${response.url()}`);
  });
  return diagnostics;
}

export async function expectDesktopHealthy(page: Page, diagnostics: Diagnostics) {
  await expect(page.locator("main")).toHaveCount(1);
  await expect(page.locator("h1")).toHaveCount(1);
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2)).toBeTruthy();
  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.failedRequests).toEqual([]);
  expect(diagnostics.consoleErrors).toEqual([]);
}

export async function expectNoPrototypeExploration(page: Page) {
  await expect(page.getByRole("button", { name: /Tweaks/ })).toHaveCount(0);
  await expect(page.getByText("Tweaks · 方案探索")).toHaveCount(0);
  await expect(page.getByText("方案探索")).toHaveCount(0);
}

export async function screenshotNonBlank(page: Page, testInfo: TestInfo, name: string) {
  const buffer = await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: false });
  expect(buffer.byteLength).toBeGreaterThan(1000);
}
