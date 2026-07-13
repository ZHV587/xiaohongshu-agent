# Knowledge retrieval online metrics: privacy and retention

## Data boundary

`knowledge_retrieval_runs` stores only tenant-scoped SHA-256 correlation keys,
the fixed `success` or `error` outcome, one of the four successful retrieval
modes, numeric engine/degradation counts, evidence count, latency, and time.
An error row never stores an exception class, exception message, provider
response, query, tool arguments, or partial result.

The DeepAgents trace hook projects the result synchronously, then submits only
the fixed measurement plus exact evidence UUID/version pairs to a bounded
background dispatcher. Runtime config, raw OpenID, query, evidence text and the
raw result never cross that queue. PostgreSQL connections belong to worker
threads and use short connect, statement and lock timeouts. Queue saturation
drops measurements without delaying the user request and emits rate-limited,
identity-free operational warnings. Evidence identities and exposures are
written in fixed-key-order batches, keeping one job to a small fixed number of
SQL statements and avoiding reverse-order row locks. The application lifespan
stops new submissions, cancels queued work and waits only for the bounded
in-flight writes during shutdown. The run timestamp is captured before the job
is queued, so database delay cannot shift cohort or retention time.

The replay identity is the tenant, actor and turn-scoped tool-call fingerprint.
The first write also stores a digest of the complete safe result projection
(outcome, retrieval mode, engine counts and every numeric exposure field). A
retry with the same projection is idempotent and keeps the earlier observation
time; a retry with a different projection is rejected as a conflict. Latency
and observation time are deliberately excluded from this digest because they
can legitimately differ when the same tool call is replayed.

`knowledge_retrieval_exposures` stores ranks, numeric scores, engine flags, and
an `evidence_key`. It does not store a resource ID, resource version, title,
summary, or body.

`knowledge_retrieval_evidence_keys` is an internal identity map. It is the only
metrics-owned table containing exact resource IDs and versions. A key is added
only after the exact version passes the current-knowledge and actor ACL gates.
The map exists to make reporting an indexed join; reports must never recreate
it by hashing every row in `resource_versions`.

An `actor_key` or `evidence_key` is pseudonymous, not anonymous. Anyone with an
identity candidate and the hashing convention can test that candidate. These
keys therefore receive the same access control as resource metadata and must
not be written to logs, traces, analytics exports, or user-facing responses.
The default aggregate API returns counts and rates only. It deliberately has no
per-evidence result type or identity export.

## Attribution semantics

Runs are filtered by both tenant and actor fingerprint. Evidence is rechecked
against the requesting actor's current ACL during aggregation. A generated-copy
outcome is attributable only when all of these facts agree:

- the copy belongs to the same tenant and actor;
- its origin turn matches the retrieval turn;
- an exact `derived_from` or `imitated_from` edge targets the exposed evidence;
- the lifecycle event actor is the same actor;
- the event payload version equals the edge's `source_resource_version`.

Explicit adoption counts only the first `adopted` event. Committed use counts
the first of `adopted`, `finalized_for_schedule`, or `published`; repeated events
do not increase the count. The explicit and committed windows are 7 and 14 days.

## Retention and deletion

The production scheduler keeps raw runs and exposures for 90 days and deletes
them in bounded, `SKIP LOCKED` batches. A dedicated `(created_at, id)` index
keeps expiration scans bounded as the table grows.
Longer-lived dashboards should persist only aggregate counts and rates with the
configured minimum-sample suppression, never actor or evidence fingerprints.
Each batch deletes in this order:

1. Lock a bounded set of expired runs with `SKIP LOCKED`.
2. Collect their evidence keys and lock those identity rows in deterministic
   key order with `SKIP LOCKED`. A run is deferred when any of its keys is busy,
   so cleanup never waits behind a concurrent writer.
3. Delete only the eligible locked runs; exposures cascade with each run.
4. Delete the already-locked identity rows that are no longer referenced by any
   exposure.

Only identity keys touched by the deleted batch are considered for orphan
cleanup. Writers use the same run-then-key lock order, so a fresh exposure is
either visible to the orphan check or recreates the identity only after cleanup
commits; it cannot be silently detached. Keys still referenced by a fresh run
are retained. Deleting an exact
`resource_versions` row cascades through its identity-map row and exposures.
Deleting a tenant removes its runs first, then its remaining identity-map rows.
User erasure is deliberately not exposed as an uncoordinated repository batch:
an authorized erasure workflow must first prevent queued writes from recreating
the actor's rows (for example with an actor tombstone), then compute the
tenant-scoped actor fingerprint in memory, delete all matching runs, and perform
the same orphan cleanup. Raw OpenIDs must not be copied into a retention queue
or audit payload.

The 90-day period is the default operating policy, not a reason to delay an
authorized tenant, user, or resource deletion. Backups follow the platform's
existing encrypted-backup expiry; deleted pseudonymous rows must not be restored
into the live metrics tables outside an approved disaster-recovery operation.
