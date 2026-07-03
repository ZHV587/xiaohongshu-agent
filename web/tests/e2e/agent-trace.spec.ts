import { expect, test, type Page, type Route } from "@playwright/test";
import { captureDiagnostics, expectDesktopHealthy } from "./ds-desktop-helpers";

const threadId = "trace-thread";
const finalMessages = [
  { id: "user-turn-1", type: "human", content: "按职场穿搭出 1 个选题，要有依据" },
  {
    id: "turn-1",
    type: "ai",
    content: "这是最终定版回答：选题可以从通勤穿搭的省心清单切入。",
  },
];

function traceEvent(overrides: Record<string, unknown>) {
  return {
    type: "xhs.trace.tool.completed",
    schema_version: 1,
    event_id: "trace-event-1",
    trace_id: "trace-1",
    run_id: "run-1",
    turn_id: "turn-1",
    seq: 1,
    ts: "2026-07-03T12:00:00.000Z",
    label: "tool completed",
    visibility: "user",
    tool_name: "semantic_search_resources",
    metrics: { found_count: 12, used_count: 3 },
    ...overrides,
  };
}

async function fulfillJson(route: Route, json: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(json),
  });
}

async function fulfillTraceStream(route: Route) {
  await route.fulfill({
    status: 200,
    headers: { "content-type": "text/event-stream" },
    body: [
      "event: custom",
      `data: ${JSON.stringify(traceEvent({ type: "xhs.trace.run.started", event_id: "trace-start", seq: 1, label: "run started" }))}`,
      "",
      "event: custom",
      `data: ${JSON.stringify(traceEvent({ event_id: "trace-tool", seq: 2 }))}`,
      "",
      "event: custom",
      `data: ${JSON.stringify(traceEvent({ type: "xhs.trace.run.completed", event_id: "trace-done", seq: 3, label: "run completed" }))}`,
      "",
      "event: values",
      `data: ${JSON.stringify({ messages: finalMessages })}`,
      "",
      "event: end",
      "data: {}",
      "",
    ].join("\n"),
  });
}

async function installTraceMocks(page: Page) {
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/me") {
      return fulfillJson(route, {
        ok: true,
        user: {
          openId: "ou_trace_fixture",
          name: "测试用户",
          team: "内容中台",
          handle: "职场穿搭号",
          fans: "1.2w",
          isAdmin: true,
        },
      });
    }
    if (path === "/api/info") return fulfillJson(route, { ok: true, assistant_id: "agent" });
    if (path === "/api/threads/search") return fulfillJson(route, []);
    if (path === `/api/threads/${threadId}/history`) return fulfillJson(route, []);
    if (path === `/api/threads/${threadId}/state`) {
      return fulfillJson(route, {
        values: { messages: [] },
        checkpoint: { thread_id: threadId, checkpoint_id: "checkpoint-1", checkpoint_ns: "" },
        metadata: {},
        next: [],
        tasks: [],
        created_at: "2026-07-03T12:00:00.000Z",
      });
    }
    if (path.endsWith("/runs/stream") || path === "/api/runs/stream") return fulfillTraceStream(route);

    return fulfillJson(route, { ok: true });
  });
}

test.describe("official agent trace browser acceptance", () => {
  test("renders official custom trace below the answer with friendly Chinese", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 960 });
    const diagnostics = captureDiagnostics(page);
    await installTraceMocks(page);

    await page.goto(`/?apiUrl=/api&assistantId=agent&threadId=${threadId}`);
    const composer = page.getByPlaceholder(/按职场穿搭出 3 个选题/);
    await expect(composer).toBeVisible();

    await composer.fill("按职场穿搭出 1 个选题，要有依据");
    await Promise.all([
      page.waitForRequest((request) => request.url().includes("/runs/stream"), { timeout: 5000 }),
      composer.press("Enter"),
    ]);

    const answer = page.getByText("这是最终定版回答", { exact: false });
    const traceSummary = page.getByText("已完成素材核验：找到 12 条，采用 3 条").first();
    await expect(answer).toBeVisible();
    await expect(traceSummary).toBeVisible();

    const answerBox = await answer.boundingBox();
    const traceBox = await traceSummary.boundingBox();
    expect(answerBox, "最终回答应可见并有布局位置").toBeTruthy();
    expect(traceBox, "思考链摘要应可见并有布局位置").toBeTruthy();
    expect(traceBox!.y).toBeGreaterThan(answerBox!.y);

    await traceSummary.click();
    await expect(page.getByText("核验素材依据").first()).toBeVisible();
    await expect(page.getByText("先确认有没有可用素材，避免凭空给建议。").first()).toBeVisible();
    await expect(page.getByText("找到 12 条相关素材，采用 3 条作为本次回答依据。").first()).toBeVisible();

    const bodyText = await page.locator("body").innerText();
    for (const word of ["trace", "run", "tool", "custom", "debug", "schema", "payload"]) {
      expect(bodyText).not.toContain(word);
    }

    await expectDesktopHealthy(page, diagnostics);
  });
});
