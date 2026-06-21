# Scheduler Universal Tenant Discovery Design

## Status

- Status: approved for specification; awaiting implementation-plan review.
- Scope: make scheduler work discovery independent of Feishu sync sources.

## Problem

`Scheduler._run_cycle_body()` currently derives its tenant list exclusively from
due `sync_sources`. A tenant with only Agent-created or direct API-created
resources has no sync source, so it never reaches processor preparation,
embedding-index reconciliation, or outbox processing. This contradicts the
universal Postgres data foundation: Feishu is an ingestion adapter, not a
runtime prerequisite.

## Decision

The scheduler will build one bounded, de-duplicated worklist per cycle from:

1. Tenants with a due, unlocked enabled sync source, ordered by the existing
   source fairness rules.
2. Tenants whose current active, non-empty resource version is not represented
   by the current embedding profile's active or building index.
3. Tenants with ready `pending` or `retry` outbox work.

The final list is capped by `SchedulerConfig.tenant_limit`. Due-source tenants
retain their existing ordering, but cannot monopolize a cycle: when the limit
is greater than one and non-source work exists, at least one slot is reserved
for it. The remaining candidates are ordered deterministically by category then
tenant id. A tenant may occur only once per cycle.

For every selected tenant, the scheduler retains its existing sequence:

1. Lease and process at most one due source, if present.
2. Prepare active processors, including embedding-index reconciliation.
3. Lease and process ready outbox work.

This keeps source ingestion behavior unchanged while allowing resources created
without a source to receive embeddings and allowing ready outbox work to drain.

## Ownership

- `SourceRepository` remains responsible only for source-specific due discovery
  and leasing.
- `EmbeddingIndexService` exposes tenant discovery for resources that still
  require reconciliation under its current profile. It owns this because the
  profile version, model, and chunker version determine whether a resource is
  already indexed.
- `OutboxRepository` exposes ready-work tenant discovery.
- `Scheduler` merges the three bounded lists and owns priority, deduplication,
  and the global per-cycle limit.

No DeepAgents internals, private LangGraph APIs, project-owned CLI entry points,
or direct prompt-to-SQL paths are introduced.

## Storage and Performance

Embedding discovery uses current active resources with nonblank `content_text`
that lack a vector for the current profile and resource version, grouped by
tenant. It must not select tenants whose current resources are already complete:
otherwise the scheduler would reconcile every tenant every interval. A partial
resource index matches the active/nonblank predicate and begins with
`tenant_id`; existing version and embedding keys support the anti-join.
Outbox discovery uses `pending/retry` rows that are due now, grouped by tenant.
Its index starts with `next_attempt_at` and `tenant_id` under the same partial
status predicate. Existing source indexes remain the source-discovery path.

The scheduler asks each repository for at most `tenant_limit` candidates and
never scans an unbounded tenant list in application memory.

Embedding index counters describe current resources, not historical resource
versions. When a resource is revised under an unchanged profile, reconciliation
must replace the prior version's coverage without allowing
`completed_resources` to exceed `expected_resources`. The implementation may
recompute the completion count transactionally when updating an existing index;
it must not rely on a monotonic increment across resource versions.

## Failure Behavior

- A missing or disabled embedding profile keeps existing disabled behavior; it
  does not manufacture a successful outbox result.
- A failed reconcile increments the existing cycle failure count and does not
  prevent other selected tenants from processing.
- A tenant with no due source still reaches processor preparation and outbox
  processing.
- A tenant selected by multiple sources is processed once.

## Verification

Tests must prove:

1. A tenant with no sync source and a current resource missing from the active
   embedding profile is selected, reconciled, and sent to the outbox runner.
2. A ready-outbox-only tenant is selected and processed.
3. Due-source tenants remain first, duplicates are removed, and the global
   limit is honored.
4. Repository SQL and schema indexes match the discovery predicates.
5. A fully indexed tenant is not selected again solely because it has old
   resources.
6. With a saturated due-source list, non-source work receives its reserved
   opportunity and does not starve.
7. Revising a resource under the same profile keeps embedding index completion
   counts aligned with its current resource set.
8. On the deployed server, one direct universal resource creates an active
   1536-dimensional embedding and is returned by semantic search; the
   allowlisted reset restores an empty baseline afterward.

## Self-Review

- No TODO/TBD placeholders.
- Feishu remains an optional ingestion adapter.
- Work discovery has explicit ownership and a bounded query contract.
- The design preserves the official LangGraph lifespan runtime and DeepAgents
  tool boundary.
