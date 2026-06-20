# Phase 5.2: Startup Determinism and Runtime Facts

- Date: 2026-06-20
- Status: approved for implementation planning
- Scope: deterministic LangGraph startup, truthful administrator runtime facts, and an administrator-only read-only Web surface.

## 1. Goals

Phase 5.2 completes the operational half of Phase 5 without introducing another agent runtime, an independent admin backend, or a project-owned business CLI.

The deliverables are:

1. Importing `agent.py` is side-effect free.
2. Backend startup is deterministic and observable.
3. Administrators can inspect truthful scheduler, sync, outbox, embedding, resource, and error facts through the existing internal HTTP boundary.
4. Runtime facts never expose credentials, DSNs, authorization headers, outbox payloads, or exception tracebacks.

## 2. Non-Goals

- Do not fork or modify DeepAgents or LangGraph internals.
- Do not create a standalone management backend or a new authentication system.
- Do not make `lark-cli` a user-facing or Web production runtime entry.
- Do not automatically update Feishu skills or external repositories during import or backend startup.
- Do not make runtime facts an analytics warehouse or scan resource bodies.

## 3. Startup Determinism

### 3.1 Pure graph import

`agent.py` may construct and export the DeepAgents graph, tools, subagents, and middleware. It must not perform network access, subprocess execution, skill updates, external repository updates, or filesystem writes while it is imported.

The regression test imports `agent.py` with network, subprocess, and write-capable adapters guarded. Any attempted side effect fails the test.

### 3.2 Explicit maintenance boundary

Feishu skill or adapter updates are maintenance actions, not lifecycle actions. They may remain available to an operator-maintenance path when required, but the LangGraph ASGI lifespan does not invoke them automatically.

If automatic repair is ever required, it must be introduced as a separately designed maintenance job with a Postgres advisory lock, a version record, and an audit event. It is outside Phase 5.2.

### 3.3 Lifespan responsibilities

`data_foundation/http_app.py` remains the `langgraph.json` `http.app` extension point. Its lifespan owns only local lifecycle work:

- start and stop the data-foundation supervisor;
- construct a process-local runtime snapshot provider;
- validate optional adapters without mutating them;
- record an initialization fact with `instance_id`, start time, and a safe status.

Optional validation failures do not stop the LangGraph service. They produce a module-level degraded fact. Core startup failures may stop startup only when the existing runtime cannot serve its declared contract.

## 4. Runtime Facts Contract

### 4.1 Authority model

Runtime facts combine two explicit sources:

- `instance`: process-local supervisor and lifecycle state. It is real-time for the serving backend instance and includes `instance_id`.
- `database`: Postgres aggregates. It is global and survives restart, but is sampled rather than real-time.

Every module result includes `source`, `observed_at`, and `stale_after_seconds`. Consumers must not treat an old database observation as an in-process liveness signal.

### 4.2 Module result shape

Each module returns independently:

```json
{
  "status": "healthy | degraded | unavailable",
  "source": "instance | database",
  "observed_at": "RFC 3339 timestamp",
  "stale_after_seconds": 30,
  "data": {},
  "error": {"code": "SAFE_CODE", "summary": "safe summary"}
}
```

The `error` member is optional. It never contains an exception class, traceback, credential, DSN, raw provider response, or user-controlled payload.

`GET /internal/ok` remains a narrow internal-route liveness probe. It is not a health verdict. `GET /internal/health/facts` returns the module facts and does not collapse partial failure into one misleading `ok: true` result.

### 4.3 Required facts

`GET /internal/health/facts` is administrator-only and returns:

- startup: process initialization status and safe optional-adapter validation results;
- scheduler: enabled state, current instance id, latest cycle start/finish, latest outcome, and safe failure summary;
- sync sources: enabled, expired, and running counts plus the most recent outcome;
- outbox: counts for pending, retry, processing, blocked, dead, succeeded, and superseded;
- embedding: active and building indexes, model, config version, completion ratio, and failure count;
- resources: total count, count by type, and most recent `indexed_at`;
- errors: bounded recent aggregates by component, operation, and error code.

The existing `/internal/data-foundation/status` stays a resource-oriented summary. Health facts are the broader operational view and can reuse repository aggregation helpers without duplicating SQL semantics.

### 4.4 Performance and degradation

Each database aggregate uses fixed, indexed, read-only queries. It never reads resource bodies, `sync_sources.credentials`, outbox payloads, or full error logs.

Facts are collected per module. A failed or timed-out module becomes `unavailable`; unrelated modules remain available. The endpoint itself uses a short bounded collection budget and returns partial results rather than failing the whole administrator page.

## 5. Authorization and Redaction

The existing chain remains mandatory:

1. Browser request reaches a Next administrator API route.
2. Next verifies the signed user identity and administrator allowlist.
3. Next forwards `X-XHS-Internal-Key`, `X-XHS-Open-Id`, and the computed admin claim.
4. Python validates the shared key and recomputes administrator status from `XHS_ADMIN_OPEN_IDS`.

Only an administrator can read runtime facts. A claim mismatch is rejected and recorded as a credential-free security event.

The runtime facts API and Web view must not display:

- configuration values or API keys;
- database URLs;
- UATs, Authorization headers, or Feishu credentials;
- `sync_sources.credentials`;
- outbox payloads;
- raw exception messages or tracebacks.

## 6. Web Surface

The Web application adds an administrator-only, read-only runtime status entry within the existing conversation application. It is not a standalone admin system.

The Next route forwards only to `/internal/health/facts`. The UI:

- polls every 15 seconds and supports a manual refresh;
- shows sampled time, source, and partial/degraded states;
- groups modules in collapsible operational sections;
- shows safe error code and summary only;
- renders no configuration or arbitrary backend error text.

Non-administrators neither see the entry nor gain API access.

## 7. Test and Acceptance Matrix

Python tests prove:

- importing `agent.py` has no network, subprocess, external update, or write side effect;
- lifespan starts and stops supervisor state deterministically;
- every health module returns its documented shape;
- one failed aggregate produces a local `unavailable` module, not a failed endpoint;
- non-administrators receive 403;
- representative credentials, DSNs, payloads, and traceback text do not appear in responses or logs.

Web tests prove:

- the Next administrator route forwards administrator context to internal HTTP;
- non-administrators are rejected before forwarding;
- the UI renders healthy, degraded, unavailable, stale, and manual-refresh states;
- no configuration value is rendered by the runtime-status components.

Deployment acceptance proves:

- backend startup produces no automatic Feishu skill update;
- authenticated loopback health facts return 200;
- anonymous and non-admin requests are rejected;
- the server real-Postgres suite and Web production build pass.

## 8. Delivery Order

1. Remove import-time side effects and add deterministic lifecycle facts.
2. Add repository/runtime aggregation helpers and the truthful internal health endpoint.
3. Add the administrator Next route and read-only Web status surface.
4. Run local, real-Postgres server, build, and authenticated smoke validation.

