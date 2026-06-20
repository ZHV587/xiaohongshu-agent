# Embedding Config Hot Index Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development for every behavior change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a saved embedding configuration hot-effective: the next scheduler cycle creates a new building index, backfills it with the saved profile, and atomically activates it without interrupting search through the old index.

**Architecture:** The encrypted config center is the versioned profile authority when enabled; environment variables remain the bootstrap/fallback authority only. A runtime profile provider creates one immutable snapshot per scheduler cycle, and semantic search resolves the historical profile referenced by the active index. DeepAgents and LangGraph are unchanged; the LangGraph ASGI supervisor remains the only background runtime owner.

**Tech Stack:** Python 3.12, ConfigCenter/Fernet, LangGraph ASGI lifespan, PostgreSQL + pgvector, pytest, Next.js TypeScript.

---

## File Map

- Modify: `config_center.py` - atomically persist and expose current versioned snapshots, including first-run environment bootstrap.
- Modify: `data_foundation/config.py` - load current and historical immutable embedding snapshots from the config center or the explicit environment fallback.
- Modify: `data_foundation/processors/embedding.py` - convert snapshots into provider configurations without reading global environment state during requests.
- Modify: `data_foundation/processors/registry.py` - accept the cycle snapshot when constructing the embedding processor.
- Modify: `data_foundation/scheduler.py` - refresh embedding runtime components once per cycle and record the applied configuration version.
- Modify: `data_foundation/tools.py` - resolve query credentials from the active index's profile version.
- Modify: `tools/web_bridge_runner.py` - expose redacted current version in configuration status responses.
- Modify: `web/src/app/api/config/route.ts` and `web/src/app/api/backend/status/route.ts` - return truthful hot-index progress semantics rather than a restart-required claim.
- Modify: `README.md` and `.env.example` - document bootstrap, retained historical profiles, and the maximum scheduler-cycle delay.
- Test: `tests/test_config_center.py`, `tests/data_foundation/test_config.py`, `tests/data_foundation/test_scheduler.py`, `tests/data_foundation/test_search_graph_tools.py`, `tests/test_web_bridge_runner.py`, and `web/tests/config-store-phase2.test.ts`.

### Task 1: Versioned Runtime Profile Provider

**Files:** `config_center.py`, `data_foundation/config.py`, `tests/test_config_center.py`, `tests/data_foundation/test_config.py`

- [ ] **Step 1: Write failing tests** for a missing config-center file bootstrapping once from explicit `XHS_EMBEDDING_*` values, current snapshot resolution, historical snapshot resolution, and environment fallback refusing an unavailable historical version.
- [ ] **Step 2: Run focused tests** with `uv run pytest tests/test_config_center.py tests/data_foundation/test_config.py -q` and verify the failures identify the missing provider API.
- [ ] **Step 3: Implement the minimum provider API.** Keep `EmbeddingConfigSnapshot` immutable and add functions equivalent to:

```python
def runtime_embedding_snapshot() -> EmbeddingConfigSnapshot:
    """Return one current snapshot from ConfigCenter, otherwise explicit env."""

def embedding_snapshot_for_version(version: str) -> EmbeddingConfigSnapshot | None:
    """Return the saved historical profile used by an active index."""
```

The config-center branch must write an initial, versioned bootstrap snapshot only when its encrypted file is absent or empty. It must never merge a later environment value over a saved profile.

- [ ] **Step 4: Re-run focused tests** and confirm they pass.
- [ ] **Step 5: Commit** with `git add config_center.py data_foundation/config.py tests/test_config_center.py tests/data_foundation/test_config.py && git commit -m "feat: load versioned embedding profiles"`.

### Task 2: One Snapshot Per Scheduler Cycle

**Files:** `data_foundation/processors/embedding.py`, `data_foundation/processors/registry.py`, `data_foundation/scheduler.py`, `tests/data_foundation/test_scheduler.py`, `tests/data_foundation/test_embedding_processor.py`

- [ ] **Step 1: Write failing tests** asserting that a scheduler runtime factory is invoked once per cycle, a second cycle receives a newer profile, the service and registry receive the same provider config, and telemetry uses that profile version.
- [ ] **Step 2: Run** `uv run pytest tests/data_foundation/test_scheduler.py tests/data_foundation/test_embedding_processor.py -q` and verify the scheduler still freezes the environment-derived processor at startup.
- [ ] **Step 3: Implement a narrow cycle runtime factory.** It returns the cycle's provider config, `EmbeddingIndexService` only when state is enabled, and a registry built from the same config. Refresh it before tenant discovery; static constructor injection remains available for unit tests.

```python
runtime = self.runtime_factory()
self.embedding_service = runtime.embedding_service
self.outbox_registry = runtime.outbox_registry
self._cycle_config_version = runtime.config_version
```

Do not recreate source repositories, supervisor tasks, or database connections. A disabled/misconfigured snapshot must keep jobs blocked and must not reconcile a new index.

- [ ] **Step 4: Re-run focused tests** and confirm they pass.
- [ ] **Step 5: Commit** with `git add data_foundation/processors data_foundation/scheduler.py tests/data_foundation && git commit -m "feat: refresh embedding profile each scheduler cycle"`.

### Task 3: Historical Profile Querying

**Files:** `data_foundation/tools.py`, `tests/data_foundation/test_search_graph_tools.py`

- [ ] **Step 1: Write failing tests** that create an active v1 index, make v2 the current profile, and assert query embedding still uses v1's base URL, key, timeout, and model. Add a separate assertion that a missing historical profile produces the structured `EMBEDDING_QUERY_PROFILE_UNAVAILABLE` keyword fallback.
- [ ] **Step 2: Run** `uv run pytest tests/data_foundation/test_search_graph_tools.py -q` and verify the implementation still reads `os.environ` rather than `active_index.config_version`.
- [ ] **Step 3: Implement query embedding with an explicit `EmbeddingProviderConfig` argument.** Resolve the config version before calling the provider and validate model/dimensions against the active index. Never send API keys to the response, logs, telemetry, or fallback reason.
- [ ] **Step 4: Re-run focused tests** and confirm they pass.
- [ ] **Step 5: Commit** with `git add data_foundation/tools.py tests/data_foundation/test_search_graph_tools.py && git commit -m "fix: query active indexes with historical profiles"`.

### Task 4: Truthful Config API and Documentation

**Files:** `tools/web_bridge_runner.py`, `web/src/app/api/config/route.ts`, `web/src/app/api/backend/status/route.ts`, `README.md`, `.env.example`, `tests/test_web_bridge_runner.py`, `web/tests/config-store-phase2.test.ts`

- [ ] **Step 1: Write failing tests** for a redacted `config-status` version and config API response semantics: config-center saves are immediately durable, scheduler application is automatic on the next cycle, and no response claims a backend restart is required for embedding reindexing.
- [ ] **Step 2: Run** `uv run pytest tests/test_web_bridge_runner.py -q` and `cd web && pnpm test:unit`; verify the old hard-coded `hot_apply_supported: false` response fails the expectation.
- [ ] **Step 3: Implement redacted version reporting and update UI-facing messages.** The API must report the saved version, the `config-center` apply mode, and that a matching building index is scheduled automatically. It must not promise instant provider execution or expose secrets.
- [ ] **Step 4: Document operational behavior.** Add `XHS_CONFIG_ENCRYPTION_KEY`/`XHS_CONFIG_CENTER_PATH` deployment requirements, one-cycle application latency, active/building/retired index behavior, and environment-mode restart limitation.
- [ ] **Step 5: Re-run focused tests** and confirm they pass.
- [ ] **Step 6: Commit** with `git add tools/web_bridge_runner.py web/src/app/api/config/route.ts web/src/app/api/backend/status/route.ts README.md .env.example tests/test_web_bridge_runner.py web/tests/config-store-phase2.test.ts && git commit -m "feat: report embedding config hot index status"`.

### Task 5: Integration Verification and Deployment

**Files:** no new production files expected

- [ ] **Step 1: Run local quality gates:**

```powershell
uv run pytest -q
cd web
pnpm test:unit
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

- [ ] **Step 2: Run `git diff --check`** and review the final diff for any secret values or legacy runtime paths.
- [ ] **Step 3: Deploy and validate against the server's real Postgres.** Enable the config center with a server-only Fernet key and path, bootstrap the existing SiliconFlow profile, save a new test profile version, observe one `building` index, verify old-index semantic search remains available, complete/reconcile the new index, and confirm atomic activation.
- [ ] **Step 4: Remove only test resources/indexes and restore the empty development baseline.** Preserve `lark_uat_tokens`, server-only config-center secret, and server credentials.
- [ ] **Step 5: Commit/push remaining changes** with `git add -A && git commit -m "feat: hot apply embedding index profiles" && git push origin master`.

## Self-Review

- The plan covers all confirmed requirements: versioned storage, current-cycle reindexing, active-index historical query, transparent UI behavior, docs, tests, and real-server proof.
- No new CLI, daemon, DeepAgents fork, compatibility alias, or second data store is introduced.
- Credentials remain only in encrypted config-center storage or explicit deployment environment and are redacted in every response and test assertion.
