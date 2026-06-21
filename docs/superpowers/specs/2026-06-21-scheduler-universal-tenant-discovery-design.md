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
2. Tenants with an active, non-empty resource that can require embedding-index
   reconciliation.
3. Tenants with ready `pending` or `retry` outbox work.

The final list is capped by `SchedulerConfig.tenant_limit`. Due-source tenants
retain their existing precedence and ordering. The remaining candidates are
ordered deterministically by source category then tenant id. A tenant may occur
only once per cycle.

For every selected tenant, the scheduler retains its existing sequence:

1. Lease and process at most one due source, if present.
2. Prepare active processors, including embedding-index reconciliation.
3. Lease and process ready outbox work.

This keeps source ingestion behavior unchanged while allowing resources created
without a source to receive embeddings and allowing ready outbox work to drain.

## Ownership

- `SourceRepository` remains responsible only for source-specific due discovery
  and leasing.
- `ResourceRepository` exposes active-resource tenant discovery.
- `OutboxRepository` exposes ready-work tenant discovery.
- `Scheduler` merges the three bounded lists and owns priority, deduplication,
  and the global per-cycle limit.

No DeepAgents internals, private LangGraph APIs, project-owned CLI entry points,
or direct prompt-to-SQL paths are introduced.

## Storage and Performance

Resource discovery uses active resources with nonblank `content_text`, grouped
by tenant. A partial index matches that predicate and orders by `tenant_id`.
Outbox discovery uses `pending/retry` rows that are due now, grouped by tenant.
Its index starts with `next_attempt_at` and `tenant_id` under the same partial
status predicate. Existing source indexes remain the source-discovery path.

The scheduler asks each repository for at most `tenant_limit` candidates and
never scans an unbounded tenant list in application memory.

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

1. A tenant with no sync source but an active embeddable resource is selected,
   reconciled, and sent to the outbox runner.
2. A ready-outbox-only tenant is selected and processed.
3. Due-source tenants remain first, duplicates are removed, and the global
   limit is honored.
4. Repository SQL and schema indexes match the discovery predicates.
5. On the deployed server, one direct universal resource creates an active
   1536-dimensional embedding and is returned by semantic search; the
   allowlisted reset restores an empty baseline afterward.

## Self-Review

- No TODO/TBD placeholders.
- Feishu remains an optional ingestion adapter.
- Work discovery has explicit ownership and a bounded query contract.
- The design preserves the official LangGraph lifespan runtime and DeepAgents
  tool boundary.
