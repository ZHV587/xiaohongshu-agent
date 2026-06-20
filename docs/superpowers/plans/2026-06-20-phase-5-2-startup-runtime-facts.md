# Phase 5.2 Startup Determinism and Runtime Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Make graph startup deterministic and give administrators truthful, redacted runtime facts through existing LangGraph HTTP and Web boundaries.

**Architecture:** \`agent.py\` becomes a pure graph declaration. The LangGraph ASGI lifespan owns a process-local supervisor snapshot, while fixed Postgres aggregation queries provide global persisted facts. The internal health route merges modules independently; Next and the existing chat app consume it without another admin runtime.

**Tech Stack:** Python, DeepAgents, LangGraph ASGI/Starlette, Postgres/psycopg, Next.js, React, TypeScript, pytest, node:test.

---

## File Map

- \`agent.py\`: remove Lark auto-update work from imports.
- \`data_foundation/runtime_facts.py\`: new JSON-safe module-fact and process snapshot helpers.
- \`data_foundation/supervisor.py\`: safe current-instance cycle state.
- \`data_foundation/http_app.py\`: create and expose snapshot in lifespan.
- \`data_foundation/repository.py\`: fixed read-only database aggregates.
- \`data_foundation/internal_api.py\`: module-degraded health facts response.
- \`web/src/app/api/backend/runtime-facts/route.ts\`: existing Next admin boundary.
- \`web/src/components/thread/history/RuntimeFactsPage.tsx\`: read-only existing-app panel.

### Task 1: Make Agent Import Pure

**Files:**
- Modify: \`agent.py\`
- Modify: \`tests/test_agent_assembly.py\`

- [x] **Step 1: Write the failing regression test**

\`\`\`python
def test_agent_import_does_not_update_lark_adapters(monkeypatch):
    import importlib
    import tools.lark_cli as lark_cli

    _set_assembly_env(monkeypatch)
    calls = []
    monkeypatch.setattr(lark_cli, "auto_update_lark_skills", lambda: calls.append("skills"))
    monkeypatch.setattr(lark_cli, "auto_update_lark_cli", lambda: calls.append("cli"))

    import agent as agent_module
    importlib.reload(agent_module)

    assert calls == []
\`\`\`

- [x] **Step 2: Verify the test is red**

Run: \`uv run pytest tests/test_agent_assembly.py::test_agent_import_does_not_update_lark_adapters -q\`

Expected: FAIL because import currently calls both updater functions.

- [x] **Step 3: Remove the import side effect**

Delete this import and conditional execution from \`agent.py\`:

\`\`\`python
from tools.lark_cli import auto_update_lark_skills, auto_update_lark_cli

if os.environ.get("DISABLE_AUTO_UPDATE") != "true":
    auto_update_lark_skills()
    auto_update_lark_cli()
\`\`\`

Keep \`load_lark_mcp_tools\`, all DeepAgents assembly, and explicit maintenance adapters unchanged.

- [x] **Step 4: Verify green**

Run: \`uv run pytest tests/test_agent_assembly.py -q\`

Expected: PASS.

- [x] **Step 5: Commit**

\`\`\`bash
git add agent.py tests/test_agent_assembly.py
git commit -m "fix: make agent import side-effect free"
\`\`\`

### Task 2: Create Process-Local Runtime Snapshot

**Files:**
- Create: \`data_foundation/runtime_facts.py\`
- Modify: \`data_foundation/supervisor.py\`
- Modify: \`data_foundation/http_app.py\`
- Create: \`tests/data_foundation/test_runtime_facts.py\`
- Modify: \`tests/data_foundation/test_http_app.py\`

- [x] **Step 1: Write failing snapshot tests**

\`\`\`python
def test_supervisor_fact_reports_safe_cycle_state():
    supervisor = BackgroundServiceSupervisor(enabled=False)
    supervisor.instance_id = "instance-1"
    supervisor.last_cycle_started_at = "2026-06-20T00:00:00+00:00"
    supervisor.last_cycle_finished_at = "2026-06-20T00:00:01+00:00"
    supervisor.last_cycle_status = "failed"
    supervisor.last_cycle_error_code = "SCHEDULER_CYCLE_FAILED"

    fact = supervisor_runtime_fact(supervisor, observed_at="2026-06-20T00:00:02+00:00")

    assert fact["status"] == "degraded"
    assert fact["source"] == "instance"
    assert fact["data"]["instance_id"] == "instance-1"
    assert "RuntimeError" not in str(fact)
\`\`\`

Extend lifespan test to assert yielded state has \`supervisor\` and \`runtime_snapshot\`, and shutdown marks the latter stopped.

- [x] **Step 2: Verify red**

Run: \`uv run pytest tests/data_foundation/test_runtime_facts.py tests/data_foundation/test_http_app.py -q\`

Expected: FAIL because snapshot helpers and lifecycle state do not exist.

- [x] **Step 3: Implement minimal safe state**

Create helpers:

\`\`\`python
def module_fact(*, status, source, observed_at, stale_after_seconds, data, error=None):
    result = {"status": status, "source": source, "observed_at": observed_at,
              "stale_after_seconds": stale_after_seconds, "data": data}
    if error is not None:
        result["error"] = error
    return result

def supervisor_runtime_fact(supervisor, *, observed_at):
    cycle_status = supervisor.last_cycle_status or "never_run"
    status = "unavailable" if not supervisor.enabled else (
        "degraded" if cycle_status == "failed" else "healthy"
    )
    return module_fact(
        status=status, source="instance", observed_at=observed_at,
        stale_after_seconds=max(30, int(supervisor.interval_seconds * 2)),
        data={"instance_id": supervisor.instance_id, "accepting_work": supervisor.accepting_work,
              "last_cycle_started_at": supervisor.last_cycle_started_at,
              "last_cycle_finished_at": supervisor.last_cycle_finished_at,
              "last_cycle_status": cycle_status},
        error=None if supervisor.last_cycle_error_code is None else
        {"code": supervisor.last_cycle_error_code, "summary": "Scheduler cycle failed"},
    )
\`\`\`

In \`BackgroundServiceSupervisor\`, use \`uuid4().hex\` for \`instance_id\`; record ISO-UTC start/finish/status and only fixed error code. Never retain exception text. Lifespan creates a snapshot, records safe startup state, yields it, then marks it stopped after supervisor shutdown.

- [x] **Step 4: Verify green**

Run: \`uv run pytest tests/data_foundation/test_runtime_facts.py tests/data_foundation/test_http_app.py -q\`

Expected: PASS.

- [x] **Step 5: Commit**

\`\`\`bash
git add data_foundation/runtime_facts.py data_foundation/supervisor.py data_foundation/http_app.py tests/data_foundation/test_runtime_facts.py tests/data_foundation/test_http_app.py
git commit -m "feat: capture safe supervisor runtime facts"
\`\`\`

### Task 3: Add Bounded Postgres Runtime Aggregates

**Files:**
- Modify: \`data_foundation/repository.py\`
- Modify: \`tests/data_foundation/test_repository.py\`

- [x] **Step 1: Write failing aggregate test**

\`\`\`python
def test_runtime_fact_aggregates_are_bounded_and_redacted(repo, tenant_id):
    facts = repo.runtime_fact_aggregates(tenant_id)

    assert facts["outbox"]["dead"] == 1
    assert facts["sources"]["expired"] == 1
    assert facts["embedding"]["active"]["config_version"] == "cfg-1"
    assert facts["resources"]["total"] == 2
    assert facts["errors"][0]["error_code"] == "SYNC_FAILED"
    assert "payload" not in str(facts)
    assert "credentials" not in str(facts)
\`\`\`

Set up fixture rows for every outbox status, enabled/expired sources, active/building indexes, indexed resources, and an error aggregate.

- [x] **Step 2: Verify red**

Run: \`uv run pytest tests/data_foundation/test_repository.py::test_runtime_fact_aggregates_are_bounded_and_redacted -q\`

Expected: FAIL because \`runtime_fact_aggregates\` does not exist.

- [x] **Step 3: Implement fixed, safe queries**

Add \`OUTBOX_STATUSES = ("pending", "retry", "processing", "blocked", "dead", "succeeded", "superseded")\` and \`ResourceRepository.runtime_fact_aggregates(tenant_id)\`.

It must use only count/group-by or bounded most-recent queries and return:

\`\`\`python
{
  "sources": {"enabled": enabled, "expired": expired, "running": running, "last_status": last_status},
  "outbox": {status: outbox.get(status, 0) for status in OUTBOX_STATUSES},
  "embedding": {"active": active_index, "building": building_index},
  "resources": {"total": total, "by_type": by_type, "last_indexed_at": last_indexed_at},
  "errors": error_rows[:20],
}
\`\`\`

Select neither \`resource_outbox.payload\` nor \`sync_sources.credentials\`. Error rows expose only component, operation, error code, count, and window bounds. Embedding rows expose only model, config version, status, progress counts, and timestamps.

- [x] **Step 4: Verify green**

Run: \`uv run pytest tests/data_foundation/test_repository.py -q\`

Expected: PASS.

- [x] **Step 5: Commit**

\`\`\`bash
git add data_foundation/repository.py tests/data_foundation/test_repository.py
git commit -m "feat: aggregate database runtime facts"
\`\`\`

### Task 4: Replace Static Internal Health Facts

**Files:**
- Modify: \`data_foundation/internal_api.py\`
- Modify: \`data_foundation/http_app.py\`
- Modify: \`tests/data_foundation/test_internal_api.py\`

- [x] **Step 1: Write failing internal health tests**

\`\`\`python
def test_internal_health_facts_combines_instance_and_database_modules(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(internal_api, "database_runtime_fact", lambda: {
        "status": "healthy", "source": "database", "data": {"outbox": {"dead": 1}},
    })

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json()["modules"]["scheduler"]["source"] == "instance"
    assert response.json()["modules"]["database"]["data"]["outbox"]["dead"] == 1

def test_internal_health_facts_keeps_partial_result_when_database_fails(monkeypatch):
    client = _client(monkeypatch)
    monkeypatch.setattr(
        internal_api, "database_runtime_fact",
        lambda: (_ for _ in ()).throw(RuntimeError("postgresql://db-secret")),
    )

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json()["modules"]["database"]["status"] == "unavailable"
    assert "db-secret" not in response.text
\`\`\`

- [x] **Step 2: Verify red**

Run: \`uv run pytest tests/data_foundation/test_internal_api.py -q\`

Expected: FAIL because current health facts are static zero values.

- [x] **Step 3: Implement module-isolated collector**

Replace \`runtime_facts_payload\` with an async collector which reads lifespan snapshot and creates three modules: \`startup\`, \`scheduler\`, and \`database\`. Use \`connect()\`, \`ResourceRepository\`, and \`default_tenant_id()\` only inside the database helper. On database failure return:

\`\`\`python
module_fact(
    status="unavailable", source="database", observed_at=utc_now(),
    stale_after_seconds=30, data={},
    error={"code": "RUNTIME_FACTS_DATABASE_UNAVAILABLE",
           "summary": "Database runtime facts unavailable"},
)
\`\`\`

Return \`{"ok": True, "observed_at": utc_now(), "modules": modules}\`. Preserve \`require_admin\` and \`Cache-Control: no-store\`.

- [x] **Step 4: Verify green**

Run: \`uv run pytest tests/data_foundation/test_internal_api.py tests/data_foundation/test_http_app.py -q\`

Expected: PASS.

- [x] **Step 5: Commit**

\`\`\`bash
git add data_foundation/internal_api.py data_foundation/http_app.py tests/data_foundation/test_internal_api.py
git commit -m "feat: expose truthful internal runtime facts"
\`\`\`

### Task 5: Add Next Administrator Runtime Facts API

**Files:**
- Modify: \`web/src/lib/server/internal-client.ts\`
- Create: \`web/src/app/api/backend/runtime-facts/route.ts\`
- Modify: \`web/tests/internal-client-http.test.ts\`
- Create: \`web/tests/runtime-facts-route.test.ts\`

- [x] **Step 1: Write failing HTTP map and route tests**

\`\`\`typescript
test("maps runtime facts to internal health facts", async () => {
  await forwardToInternalServer("/_internal/runtime-facts", "GET", "ou_admin", undefined, { isAdmin: true });
  assert.equal(calls[0].url, "http://127.0.0.1:2030/internal/health/facts");
});
\`\`\`

Mock \`requireAdmin\` and forwarding in the new route test. Assert a 200 module payload for an administrator and a 403 path when \`requireAdmin\` rejects.

- [x] **Step 2: Verify red**

Run: \`cd web && corepack pnpm test:unit\`

Expected: FAIL because no map key or route exists.

- [x] **Step 3: Implement no-store forwarding**

Add:

\`\`\`typescript
"/_internal/runtime-facts": { path: "/internal/health/facts", method: "GET" },
\`\`\`

Create the route:

\`\`\`typescript
export async function GET() {
  try {
    const user = await requireAdmin();
    const upstream = await forwardToInternalServer(
      "/_internal/runtime-facts", "GET", user.openId, undefined, { isAdmin: true },
    );
    return jsonNoStore(await upstream.json(), { status: upstream.status });
  } catch (error) {
    return apiErrorResponse(error);
  }
}
\`\`\`

Do not add config fallback.

- [x] **Step 4: Verify green**

Run: \`cd web && corepack pnpm test:unit && corepack pnpm exec tsc --noEmit\`

Expected: PASS.

- [x] **Step 5: Commit**

\`\`\`bash
git add web/src/lib/server/internal-client.ts web/src/app/api/backend/runtime-facts/route.ts web/tests/internal-client-http.test.ts web/tests/runtime-facts-route.test.ts
git commit -m "feat: add administrator runtime facts api"
\`\`\`

### Task 6: Add Read-Only Existing-App Runtime Facts View

**Files:**
- Create: \`web/src/components/thread/history/RuntimeFactsPage.tsx\`
- Modify: \`web/src/components/thread/index.tsx\`
- Create: \`web/tests/runtime-facts-page.test.ts\`

- [x] **Step 1: Write failing safe-render helper test**

\`\`\`typescript
test("formats runtime data without arbitrary backend fields", () => {
  const rows = runtimeFactRows({
    status: "degraded", source: "database", observed_at: "2026-06-20T00:00:00Z",
    data: { outbox: { dead: 1 }, payload: "secret" },
    error: { code: "OUTBOX_BLOCKED", summary: "Outbox needs attention" },
  });
  assert.deepEqual(rows, [["dead", "1"]]);
  assert.equal(JSON.stringify(rows).includes("secret"), false);
});
\`\`\`

- [x] **Step 2: Verify red**

Run: \`cd web && corepack pnpm test:unit\`

Expected: FAIL because view and helper do not exist.

- [x] **Step 3: Implement the scoped panel**

Create a client component that fetches \`/api/backend/runtime-facts\`, polls every 15 seconds, cleans up the interval, and exposes an icon-only refresh button with tooltip. Render stable ordered sections \`startup\`, \`scheduler\`, \`database\`. Render only explicitly allowed fields, source, observed time, stale threshold, safe error code, and safe summary.

In \`index.tsx\`, add \`"runtime-facts"\` to the local view union, render \`RuntimeFactsPage\` next to existing LLM/Feishu panels, and add the entry only after \`/api/me\` reports administrator status. Do not derive permissions from browser-controlled input.

- [x] **Step 4: Verify green**

Run: \`cd web && corepack pnpm test:unit && corepack pnpm exec tsc --noEmit && corepack pnpm lint && corepack pnpm build\`

Expected: PASS.

- [x] **Step 5: Commit**

\`\`\`bash
git add web/src/components/thread/history/RuntimeFactsPage.tsx web/src/components/thread/index.tsx web/tests/runtime-facts-page.test.ts
git commit -m "feat: show administrator runtime facts"
\`\`\`

### Task 7: Security, Documentation, and Deployment Verification

**Files:**
- Modify: \`README.md\`
- Modify: \`tests/test_agent_assembly.py\`
- Modify: \`tests/data_foundation/test_internal_api.py\`

- [x] **Step 1: Add final security regressions**

Use representative strings \`sk-runtime-secret\`, \`postgresql://user:db-secret@host/db\`, and \`Authorization: Bearer token\`. Assert no health response or captured health log includes them. Assert a non-admin internal health request receives 403.

- [x] **Step 2: Verify focused behavior**

Run:

\`\`\`bash
uv run pytest tests/test_agent_assembly.py tests/data_foundation/test_runtime_facts.py tests/data_foundation/test_http_app.py tests/data_foundation/test_internal_api.py -q
cd web && corepack pnpm test:unit && corepack pnpm exec tsc --noEmit && corepack pnpm lint && corepack pnpm build
\`\`\`

Expected: PASS.

- [x] **Step 3: Document operational truth**

Update README: graph import has no external update side effect; \`/internal/ok\` is liveness only; \`/internal/health/facts\` is administrator-only, redacted, and module-degraded; administrators use the existing Web app surface.

- [x] **Step 4: Run final local suite**

Run: \`uv run pytest -q && git diff --check\`

Expected: PASS with only existing framework deprecation warnings.

- [x] **Step 5: Commit and push**

\`\`\`bash
git add README.md tests/test_agent_assembly.py tests/data_foundation/test_internal_api.py
git commit -m "docs: document runtime facts operations"
git push origin master
\`\`\`

- [x] **Step 6: Deploy and verify server**

On \`/home/ubuntu/xiaohongshu-agent\`, without printing secrets:

\`\`\`bash
git pull --ff-only origin master
set -a && . ./.env && set +a
TEST_XHS_DATABASE_URL="$XHS_DATABASE_URL" .venv/bin/python -m pytest -q
cd web && corepack pnpm build && corepack pnpm test:unit && cd ..
pm2 restart xhs-backend xhs-frontend --update-env && pm2 save
\`\`\`

Smoke: authenticated administrator \`/internal/health/facts\` returns 200; anonymous returns 401; non-admin returns 403. Do not print response bodies or configuration values.

## Plan Self-Review

- Spec coverage: Tasks 1-2 provide pure import and controlled lifespan; Tasks 3-4 provide source-aware, bounded, partial runtime facts; Tasks 5-6 provide double authorization and existing-app UI; Task 7 covers redaction, docs, local/server tests, build, and deployment.
- Placeholder scan: no unresolved work markers or deferred implementation wording remains.
- Type consistency: \`module_fact\`, \`supervisor_runtime_fact\`, \`runtime_fact_aggregates\`, \`/_internal/runtime-facts\`, and \`/api/backend/runtime-facts\` are consistent across tasks.
