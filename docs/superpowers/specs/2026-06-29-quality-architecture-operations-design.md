# Quality, Architecture, and Operations Hardening Design

## Goal

Build a three-phase hardening program for the Xiaohongshu content agent so the project becomes easier to verify, safer to present to users, easier to maintain, and more predictable in production.

This design is intentionally staged. Phase 1 fixes the quality baseline. Phase 2 reduces structural complexity. Phase 3 turns production validation and recovery into repeatable operations. Each phase should get its own implementation plan before code changes begin; later phases should not be bundled into the Phase 1 implementation batch.

## Current Context

The project is already a production-shaped content system:

- DeepAgents/LangGraph assembles the main agent, skills, tools, middleware, and two executor subagents.
- Postgres is the authority for business resources, versions, evidence, permissions, outbox, telemetry, sync state, and metrics.
- Meilisearch, pgvector, and FalkorDB are engine paths for keyword, semantic, and graph retrieval.
- Next.js acts as the authenticated BFF and creation workbench.
- Feishu is a collaboration mirror and action channel, not the authority for business facts.
- Docker Compose runs the production topology with web, langgraph, pg, redis, meili, and falkor.

The system is healthy enough to pass tests when the local proxy environment is cleared:

- Python: 538 passed, 125 skipped.
- Web unit tests: 39 passed.
- TypeScript: passes with `tsc --noEmit`.

The main issues are not missing core features. They are quality drift risks:

- Tests can fail because model client construction trusts host proxy variables.
- Some user-visible skill wording still exposes internal names and workflow details.
- The main frontend thread component owns too many independent responsibilities.
- Runtime and production operations knowledge is spread across README, prompts, code, schema, and historical plans.

## Non-Goals

This design does not change product behavior in Phase 1. It does not rewrite the agent, replace DeepAgents, change the database schema, change the Docker topology, or support multi-worker hot reload immediately.

Phase 2 and Phase 3 may add docs, tests, scripts, and small refactors, but they still avoid broad platform rewrites.

## Phase Boundaries

This document is the umbrella design. Implementation should proceed one phase at a time:

- Phase 1 is ready for an implementation plan immediately after this design is approved.
- Phase 2 requires a short follow-up implementation plan that maps the hook extraction order and preservation tests.
- Phase 3 requires a short follow-up implementation plan that maps the smoke script, health categorization, and recovery documentation work.

Do not implement Phase 2 or Phase 3 opportunistically while doing Phase 1 unless a Phase 1 test or contract directly requires a small supporting change.

## Phase 1: Quality Baseline

### Objectives

Make local and CI verification deterministic, and prevent internal implementation language from leaking into user-visible product surfaces.

### Problem 1: Proxy-Dependent Tests

Observed failure:

- `HTTPS_PROXY=socks5://127.0.0.1:7897` causes httpx/OpenAI/Google model clients to initialize through a SOCKS proxy.
- `socksio` is not installed.
- Agent assembly and provider-construction tests fail before reaching their assertions.

Root cause:

- Test setup currently normalizes `NO_PROXY`, but does not isolate `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, or lowercase variants.
- Offline assembly tests still inherit host networking configuration.

Design:

- Centralize proxy cleanup in the shared Python test setup.
- Remove `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, `http_proxy`, `https_proxy`, and `all_proxy` for test processes by default.
- Keep production code unchanged so deployed environments can still use explicit proxies if required.
- Add a regression test that sets a SOCKS proxy in the test environment and verifies offline model/agent assembly still succeeds under the shared fixture.

Acceptance:

- `uv run pytest` passes without manually clearing proxy variables.
- No test depends on the user's machine-specific proxy state.
- Production runtime behavior is not changed.
- A regression test proves that setting `HTTPS_PROXY` to a SOCKS URL does not break offline model/provider construction tests.

### Problem 2: Internal Language in User-Facing Surfaces

Observed drift:

- The main prompt correctly says users must not see skill names, tool names, section numbers, or internal routing language.
- Some skill documents still include user-facing instructions like "use xhs-copywriting" or "transfer to xhs-title".
- The frontend thinking chain can display a specific skill slug when a skill file is read.

Root cause:

- Skill files mix internal execution instructions with user-facing response snippets.
- Frontend tool rendering treats skill activation as a helpful signal but exposes the slug.
- There is no contract test that distinguishes internal-only wording from user-visible wording.

Design:

- Keep skill frontmatter names, routing metadata, tool contracts, and internal execution instructions intact.
- Rewrite user-facing snippets in core skills to use natural language.
- Replace "switch to xhs-copywriting" with "I can help you write the full note next."
- Replace "use xhs-title" with "we can work on the title separately."
- Replace explicit skill slug rendering in the frontend thinking chain with generic wording such as "organizing the method" or "preparing the next step."
- Add tests for user-facing copy surfaces so internal tokens do not appear where users see them.

Initial scan targets:

- `.agents/skills/topic-content/SKILL.md`
- `.agents/skills/xhs-copywriting/SKILL.md`
- `.agents/skills/xhs-content-system/SKILL.md`
- `.agents/skills/xhs-benchmark/SKILL.md`
- `.agents/skills/xhs-content/SKILL.md`
- `.agents/skills/xhs-action/SKILL.md`
- `web/src/lib/tool-render.tsx`

The tests should not ban internal tokens globally. They should only scan clearly user-facing sections or rendered labels.

Acceptance:

- User-facing skill snippets do not mention `xhs-*`, `topic-content`, `skill`, `tool`, `selected_topic`, `resource_id`, or prompt section references.
- Frontend thinking labels do not expose skill slugs.
- Existing routing and structured output contracts still pass.
- `npm run test:unit` and `tsc --noEmit` pass.
- The wording test names the exact files and sections it scans so internal execution instructions can still use internal identifiers where required.

### Phase 1 Test Plan

Run:

```powershell
uv run pytest
cd web
npm run test:unit
.\node_modules\.bin\tsc.CMD --noEmit
```

Add or strengthen:

- Python regression coverage for proxy isolation.
- Python/text coverage for user-facing skill wording.
- Frontend unit coverage for generic skill activation labels.

## Phase 2: Architecture Load Reduction

### Objectives

Reduce maintenance load without changing user behavior. Make the frontend workbench and runtime architecture easier to understand, test, and evolve.

### Problem 1: Thread Component Has Too Many Responsibilities

`web/src/components/thread/index.tsx` currently owns:

- Thread id and history UI wiring.
- Chat input and stream submission.
- Draft title/body state.
- Local autosave and dirty detection.
- Phone preview state.
- Feishu chat list and notification state.
- Sync animation state.
- Command palette state.
- Evidence panel state.
- View switching for config/runtime pages.

This makes small changes hard to reason about and raises the risk of cross-session state bugs.

Design:

Extract focused hooks:

- `useThreadDraftState`: draft title, draft body, autosave keys, dirty state, session switching.
- `useFeishuWorkspaceState`: chat list, selected chat, loading/error states, notification intent handoff.
- `usePreviewState`: preview mode, carousel index, preview assets, editing state.
- `useCommandPaletteState`: command palette visibility, command search, command execution.
- `useWorkbenchTabsState`: right inspector tab and selected evidence.

Introduce a thin provider composition layer:

- `Thread` remains responsible for high-level layout and route/view selection.
- `ThreadContext.Provider` receives aggregated values from the focused hooks.
- Existing child components keep their external interface unless a small type cleanup is needed.

Acceptance:

- `Thread` no longer owns draft autosave, Feishu workspace, preview, command palette, and right-tab state directly; those concerns are moved behind named hooks or provider helpers.
- Draft behavior remains per-thread and does not regress.
- Feishu, preview, evidence, and command palette interactions still work.
- Existing web tests pass, and at least draft isolation plus dirty-state behavior are covered after extraction.

### Problem 2: Runtime Architecture Knowledge Is Scattered

Important invariants are real but distributed:

- `N_WORKERS=1` is required for in-process model registry hot reload.
- Config center is the runtime authority for editable config.
- Postgres is the business fact authority.
- Feishu writes require human confirmation.
- Formal evidence must come from persisted resources.
- Online notes are transient unless adopted.

Design:

Add `docs/architecture/runtime-map.md` with these flows:

- Request flow: browser -> Next BFF -> LangGraph -> agent/tools.
- Identity flow: Feishu OAuth -> JWT cookie -> Authorization -> LangGraph auth -> tool actor.
- Evidence flow: sync source -> Postgres resource -> engine indexes -> evidence package -> user output.
- Save flow: user confirmation -> `save_*` -> Postgres -> outbox -> processors -> Feishu mirror.
- Model flow: config center -> model registry -> router middleware -> main agent/subagents/rubric.
- Background flow: ASGI lifespan -> supervisor -> scheduler -> source sync/outbox processors.

Acceptance:

- A maintainer can understand the production request and data paths from one document.
- The document names the constraints that must not be changed casually.
- Tests continue to enforce these invariants: `N_WORKERS=1` in production compose, write-action interrupts for Feishu mutations, config center as editable config authority, and Postgres as business fact authority.

## Phase 3: Production Operations

### Objectives

Make deployment validation and failure recovery repeatable. Give maintainers clear health categories and recovery steps.

### Problem 1: Smoke Validation Is Distributed

README lists smoke commands, but production readiness is not a single high-signal check.

Design:

Enhance `scripts/deploy_health_check.py` as the single smoke entrypoint to verify:

- Public web URL responds.
- LangGraph `/ok` responds.
- Internal health facts can be queried with internal credentials.
- Postgres is reachable and schema facts are readable.
- Config center is readable when enabled.
- Model status exposes at least one active model when configured.
- Meili/Falkor/embedding status is distinguishable from total failure.
- Outbox backlog and processor state are visible.
- Secrets are not printed.

Acceptance:

- A deployer can run one command after deployment and know whether the system can serve users.
- The script reports actionable module-level failures.
- The script never prints API keys, JWT secrets, Feishu tokens, or stored credentials.
- The script exits non-zero only for `blocked` production readiness states; `degraded` states are reported clearly but do not masquerade as healthy.

### Problem 2: Health Needs Product-Level Categories

Raw module facts are useful, but operators need to know whether the product is usable.

Design:

Introduce health categories:

- `healthy`: core chat, model routing, database, and required auth paths are working.
- `degraded`: core chat works, but an enhancement is unavailable, such as semantic retrieval falling back to keyword search.
- `blocked`: the product cannot serve core workflows, such as missing model pool, database unavailable, invalid auth secret, or unreadable config center in config-center mode.

Expose this categorization in the runtime facts UI and smoke output.

Acceptance:

- Runtime Facts distinguishes usable degraded states from blocking failures.
- Smoke output uses the same language.
- Operators can see next actions for degraded or blocked modules.
- The categorization rules are implemented in one shared module or documented mapping so the UI and smoke script do not drift.

### Problem 3: Recovery Steps Are Tribal Knowledge

Design:

Add `docs/operations/recovery-playbook.md` with recovery procedures for:

- Model pool has no available model.
- Config center cannot decrypt or read.
- Feishu UAT is missing or expired.
- Meilisearch unavailable.
- FalkorDB unavailable.
- Embedding index stuck in `building`.
- Outbox backlog grows or processors are blocked.
- Postgres unreachable.
- Web loads but agent runs fail.

Each section should include:

- Symptoms.
- Likely causes.
- Commands or pages to inspect.
- Safe recovery steps.
- Escalation criteria.

Acceptance:

- Common incidents can be handled without reading source code.
- Recovery steps avoid leaking secrets.
- Destructive database actions are not included unless explicitly marked as last-resort and manual.

### Problem 4: Future Multi-Worker Path Is Undefined

Current production pins `N_WORKERS=1`. That is correct for the current in-process registry design, but future scale needs a path.

Design:

Do not enable multi-worker in Phase 3. Document the future design:

- Persist model registry version and active pool metadata to Postgres as the first-choice shared authority.
- Broadcast config changes through Postgres notify as the first-choice control channel, reusing the existing database-centered runtime model.
- Each worker reloads from the shared config version.
- Runtime facts reports registry version per worker.
- Admin save succeeds only when reload convergence is visible or explicitly reported as partial.

Acceptance:

- The project does not accidentally raise `N_WORKERS` without implementing broadcast.
- The future expansion path names the shared authority, the broadcast mechanism, worker convergence check, and admin partial-reload behavior.

## Rollout Order

1. Phase 1: quality baseline.
2. Phase 2: architecture load reduction.
3. Phase 3: production operations.

This order matters. Phase 1 makes validation trustworthy. Phase 2 uses that trustworthy validation to refactor safely. Phase 3 then adds operational confidence on top of a clearer system.

## Risks

### Risk: Over-Cleaning Skill Files

If all internal tokens are removed from skills, routing and tool behavior may regress.

Mitigation:

- Only clean user-facing snippets.
- Keep frontmatter, internal instructions, tool names, and structured output contracts where they are required for execution.
- Add tests that enforce behavior contracts separately from wording contracts.

### Risk: Proxy Cleanup Hides Real Integration Behavior

If a future integration test requires a proxy, global cleanup could block that test.

Mitigation:

- Default tests are proxy-free.
- Tests that require proxy behavior must opt in explicitly and locally.

### Risk: Frontend Extraction Changes Behavior

Moving state into hooks can accidentally change effect ordering or localStorage keys.

Mitigation:

- Preserve existing storage keys and state transitions.
- Extract one concern at a time.
- Add hook-level tests around draft isolation and dirty state before moving more state.

### Risk: Operations Scripts Leak Secrets

Health checks may accidentally print raw config or credentials.

Mitigation:

- Reuse existing redaction conventions.
- Test smoke output for forbidden secret-like keys.
- Prefer status summaries over full payload dumps.

## Success Criteria

The hardening program is successful when:

- Tests pass without manual environment cleanup.
- User-visible product text no longer exposes internal workflow names.
- The frontend thread shell has clear state boundaries.
- Runtime architecture is documented in one place.
- Deployment readiness can be checked with one smoke command.
- Common production failures have documented recovery steps.
- The single-worker registry constraint is explicit and protected until a broadcast design exists.
