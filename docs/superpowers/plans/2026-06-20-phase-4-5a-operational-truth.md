# Phase 4.5A Operational Truth Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder single-tenant scheduler and fake-success outbox with a multi-tenant, leased, observable runtime that performs real pgvector embedding and scheduled Feishu/PostgreSQL ingestion.

**Architecture:** LangGraph's official `http.app` ASGI lifespan owns a background supervisor. Focused PostgreSQL repositories implement source and outbox leases, processors perform idempotent work, and immutable execution facts support later health APIs. DeepAgents remains the orchestration layer and does not start or own background services.

**Tech Stack:** Python 3.12, DeepAgents/LangGraph, Starlette ASGI, PostgreSQL 16, pgvector, psycopg 3, httpx, pytest, respx

---

## Implementation Revision: Atomic Persistence Switch

During implementation, PostgreSQL validation showed that Task 1 could not be committed independently: the new schema removed and renamed fields still used by `ResourceRepository`, outbox leasing, sync run tracking, and direct embedding writes. The durable boundary is therefore an atomic persistence switch:

- schema, immutable models, and reset allowlist
- `ResourceRepository` resource/version/event/mapping writes
- structured `OutboxRequest` enqueue and leased `OutboxRepository`
- removal of legacy `lease_outbox()`, `complete_outbox()`, `replace_embedding_chunks()`, and direct `set_embedding()`
- sync run status fields using the new operational enum
- semantic search filtering by active embedding index and current resource version

This switch must be validated together against real PostgreSQL before commit. The first verified implementation slice ran the repository/schema/outbox/sync/search test set against the server PostgreSQL with isolated schemas: `123 passed`.

## File Map

### Create

- `data_foundation/errors.py`: standardized error codes, retry classification, and recursive secret redaction.
- `data_foundation/config.py`: immutable embedding configuration snapshots and active/building profile lookup.
- `data_foundation/outbox_repository.py`: enqueue, lease, renew, transition, recover, unblock, and cleanup SQL.
- `data_foundation/outbox_requests.py`: canonical request/dedupe builders shared by every resource producer.
- `data_foundation/embedding_repository.py`: embedding index lifecycle and atomic vector batch storage.
- `data_foundation/embedding_service.py`: desired-profile reconciliation, complete-resource backfill, and atomic activation.
- `data_foundation/source_repository.py`: sync source registration, fair discovery, source leases, cursors, and sync runs.
- `data_foundation/telemetry_repository.py`: service instances, heartbeats, executions, aggregates, and retention.
- `data_foundation/processors/base.py`: processor protocol and processing result types.
- `data_foundation/processors/registry.py`: explicit enabled/disabled/misconfigured topic registry.
- `data_foundation/processors/embedding.py`: real OpenAI-compatible embedding processor.
- `data_foundation/sources/base.py`: source processor protocol and source result types.
- `data_foundation/sources/registry.py`: explicit source type registry.
- `data_foundation/sources/feishu.py`: scheduled Base/Wiki ingestion through existing loaders and repository writes.
- `data_foundation/sources/postgres.py`: read-only structured PostgreSQL table/view ingestion.
- `data_foundation/supervisor.py`: async lifecycle, scheduler loop, graceful shutdown, and lease renewal.
- `data_foundation/http_app.py`: Starlette app whose lifespan owns the supervisor.
- `tests/data_foundation/test_errors.py`
- `tests/data_foundation/test_config.py`
- `tests/data_foundation/test_outbox_repository.py`
- `tests/data_foundation/test_outbox_requests.py`
- `tests/data_foundation/test_embedding_repository.py`
- `tests/data_foundation/test_embedding_service.py`
- `tests/data_foundation/test_embedding_processor.py`
- `tests/data_foundation/test_source_repository.py`
- `tests/data_foundation/test_feishu_source_processor.py`
- `tests/data_foundation/test_postgres_source_processor.py`
- `tests/data_foundation/test_telemetry_repository.py`
- `tests/data_foundation/test_supervisor.py`
- `tests/data_foundation/test_http_app.py`

### Rewrite or Modify

- `data_foundation/schema.sql`: replace the old Phase 3/4 schema with the clean operational schema.
- `data_foundation/db.py`: add explicit development reset and connection helpers.
- `data_foundation/models.py`: add immutable outbox, source, embedding index, and execution records.
- `data_foundation/repository.py`: remove old embedding/outbox/sync-run methods; enqueue through focused repositories in the same transaction.
- `data_foundation/outbox_worker.py`: replace placeholder topic validation with registry-driven processing.
- `data_foundation/scheduler.py`: replace the daemon-thread singleton with one-cycle orchestration used by the supervisor.
- `data_foundation/search.py`: query only the current resource version and active embedding index.
- `data_foundation/tools.py`: remove chat-model embedding fallback and resolve the active embedding profile.
- `data_foundation/sync_service.py`: route manual Feishu sync through the same source processor contract.
- `data_foundation/feishu_sync.py`: enqueue versioned embedding work instead of pending vector rows.
- `data_foundation/creation_memory.py`: replace string topic lists with versioned `OutboxRequest` values.
- `data_foundation/performance_feedback.py`: replace string topic lists with versioned `OutboxRequest` values.
- `config_center.py`: add embedding keys, secret redaction, and version lookup.
- `web/src/lib/server/config-store.ts`: allow the same embedding keys in the existing admin config API.
- `langgraph.json`: register `data_foundation.http_app:app` under `http.app`.
- `pyproject.toml`: declare Starlette because the project imports it directly.
- `agent.py`: remove background-service startup on import.
- `.env.example`: document embedding and scheduler settings without secret values.
- `README.md`: document the new lifecycle, clean reset, and disabled optional adapters.
- `tests/data_foundation/conftest.py`: expose schema-isolated PostgreSQL helpers and a database clock helper.
- `tests/data_foundation/test_schema.py`: replace old nine-table expectations.
- `tests/data_foundation/test_repository.py`: assert versioned dedupe enqueue behavior.
- `tests/data_foundation/test_search_graph_tools.py`: assert active-index/current-version filtering.
- `tests/data_foundation/test_feishu_sync.py`: assert versioned outbox enqueue.
- `tests/data_foundation/test_outbox_worker.py`: delete old fake-success tests and test real processor outcomes.
- `tests/data_foundation/test_scheduler.py`: delete daemon-thread tests and test fair one-cycle orchestration.
- `tests/test_agent_assembly.py`: assert importing the graph does not start background services.

## Task 1: Replace the Data Foundation Schema Cleanly

**Files:**
- Modify: `data_foundation/schema.sql`
- Modify: `data_foundation/db.py`
- Modify: `data_foundation/models.py`
- Modify: `tests/data_foundation/conftest.py`
- Modify: `tests/data_foundation/test_schema.py`

- [ ] **Step 1: Replace schema tests with the complete table and constraint contract**

```python
EXPECTED_TABLES = {
    "resources", "resource_versions", "resource_events", "resource_mappings",
    "resource_permissions", "resource_embeddings", "resource_edges",
    "resource_outbox", "embedding_indexes", "sync_sources", "sync_runs",
    "service_instances", "service_executions", "service_error_aggregates",
}

def test_schema_creates_operational_tables(migrated_conn):
    rows = migrated_conn.execute(
        "select table_name from information_schema.tables where table_schema=current_schema()"
    ).fetchall()
    assert {row[0] for row in rows} == EXPECTED_TABLES

def test_outbox_rejects_legacy_status(migrated_conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        migrated_conn.execute(
            "insert into resource_outbox(tenant_id, topic, dedupe_key, status) values (%s,%s,%s,%s)",
            ("tenant-a", "embedding_generate", "key", "failed"),
        )
```

- [ ] **Step 2: Run the schema tests and verify the old schema fails**

Run: `uv run pytest tests/data_foundation/test_schema.py -q`

Expected: FAIL because the six new tables and new outbox fields/statuses do not exist.

- [ ] **Step 3: Rewrite `schema.sql` with explicit tables, indexes, foreign keys, and checks**

Use these exact state constraints and key relationships:

```sql
check (status in ('pending','processing','retry','blocked','succeeded','superseded','dead'))
unique (dedupe_key)
foreign key (resource_id, resource_version)
  references resource_versions(resource_id, version) on delete cascade
check (dimensions = 1536)
check (source_type in ('feishu_base','feishu_wiki','postgres_table'))
```

Add ready indexes on `(status, next_attempt_at, topic)`, lease indexes on `lease_expires_at`, one partial unique active embedding index per tenant, and tenant/recent indexes for all operational tables. Do not create `available_at` or raw `last_error` columns.

- [ ] **Step 4: Add an allowlisted reset function that preserves non-business tables**

```python
DATA_FOUNDATION_TABLES = (
    "service_error_aggregates", "service_executions", "service_instances",
    "sync_runs", "sync_sources", "embedding_indexes", "resource_outbox",
    "resource_edges", "resource_embeddings", "resource_permissions",
    "resource_events", "resource_versions", "resource_mappings", "resources",
)

def reset_data_foundation(conn: Connection) -> None:
    identifiers = sql.SQL(", ").join(sql.Identifier(name) for name in DATA_FOUNDATION_TABLES)
    conn.execute(sql.SQL("drop table if exists {} cascade").format(identifiers))
    run_migrations(conn)
```

- [ ] **Step 5: Add frozen records to `models.py`**

Define `OutboxItem`, `SyncSource`, `EmbeddingIndex`, `ServiceExecution`, and `ProcessorState` with explicit `datetime`, `UUID-as-str`, status, lease, and count fields. Do not expose credentials through `SyncSource`; use a separate `SourceSecrets` record only inside source processors.

Replace string topic lists with this immutable request contract:

```python
@dataclass(frozen=True)
class OutboxRequest:
    topic: str
    dedupe_parts: tuple[str, ...]
    payload: dict[str, Any]
```

Embedding requests include embedding model, config version, index ID, and chunker version in `dedupe_parts` and payload. Disabled optional adapters use stable adapter-version dedupe parts.

- [ ] **Step 6: Run schema tests twice to prove idempotence**

Run: `uv run pytest tests/data_foundation/test_schema.py -q`

Expected: PASS, including `run_migrations()` called twice in one isolated schema.

- [ ] **Step 7: Commit**

```bash
git add data_foundation/schema.sql data_foundation/db.py data_foundation/models.py tests/data_foundation/conftest.py tests/data_foundation/test_schema.py
git commit -m "feat: replace operational data schema"
```

## Task 2: Standardize Errors and Secret Redaction

**Files:**
- Create: `data_foundation/errors.py`
- Create: `tests/data_foundation/test_errors.py`

- [ ] **Step 1: Write failing redaction and classification tests**

```python
def test_redact_nested_credentials_and_dsn():
    payload = {
        "Authorization": "Bearer abc",
        "nested": {"api_key": "secret", "dsn": "postgresql://u:p@db/app"},
    }
    assert redact(payload) == {
        "Authorization": "[REDACTED]",
        "nested": {"api_key": "[REDACTED]", "dsn": "postgresql://[REDACTED]@db/app"},
    }

@pytest.mark.parametrize("status, expected", [(401, "blocked"), (403, "blocked"), (429, "retry"), (500, "retry")])
def test_http_error_classification(status, expected):
    assert classify_http_status(status).disposition == expected
```

- [ ] **Step 2: Run tests and verify missing imports fail**

Run: `uv run pytest tests/data_foundation/test_errors.py -q`

Expected: FAIL with `ModuleNotFoundError: data_foundation.errors`.

- [ ] **Step 3: Implement fixed error codes, dispositions, and recursive redaction**

```python
class Disposition(StrEnum):
    RETRY = "retry"
    BLOCKED = "blocked"
    DEAD = "dead"

@dataclass(frozen=True)
class OperationalError:
    code: str
    disposition: Disposition
    summary: str
    retry_after_seconds: float | None = None

SECRET_KEYS = frozenset({"authorization", "api_key", "password", "token", "access_token", "refresh_token", "dsn"})
MAX_ERROR_SUMMARY = 500
```

Handle httpx timeout/network as retry, 401/403 as blocked, 429/5xx as retry, malformed payload/dimension mismatch as dead, and truncate only after redaction.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/data_foundation/test_errors.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/errors.py tests/data_foundation/test_errors.py
git commit -m "feat: add operational error redaction"
```

## Task 3: Add Versioned Embedding Configuration

**Files:**
- Create: `data_foundation/config.py`
- Create: `tests/data_foundation/test_config.py`
- Modify: `config_center.py`
- Modify: `web/src/lib/server/config-store.ts`
- Modify: `.env.example`

- [ ] **Step 1: Write failing tests for independent configuration and historical lookup**

```python
def test_embedding_snapshot_requires_independent_keys():
    with pytest.raises(EmbeddingConfigError, match="XHS_EMBEDDING_API_KEY"):
        embedding_snapshot({"LLM_API_KEY": "must-not-fallback"}, version="v1")

def test_embedding_snapshot_rejects_non_1536_dimensions():
    values = complete_embedding_values() | {"XHS_EMBEDDING_DIMENSIONS": "3072"}
    snapshot = embedding_snapshot(values, version="v2")
    assert snapshot.state == "misconfigured"

def test_config_center_gets_historical_profile(config_center):
    first = config_center.save("admin", complete_embedding_values(model="model-a"))
    config_center.save("admin", complete_embedding_values(model="model-b"))
    assert config_center.get_version(first.version).values["XHS_EMBEDDING_MODEL"] == "model-a"
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `uv run pytest tests/data_foundation/test_config.py tests/test_config_center.py -q`

Expected: FAIL because embedding keys and `get_version()` are absent.

- [ ] **Step 3: Add editable/secret keys in Python and TypeScript**

Add exactly:

```text
XHS_EMBEDDING_BASE_URL
XHS_EMBEDDING_API_KEY
XHS_EMBEDDING_MODEL
XHS_EMBEDDING_DIMENSIONS
XHS_EMBEDDING_BATCH_SIZE
XHS_EMBEDDING_TIMEOUT_SECONDS
```

Mark only `XHS_EMBEDDING_API_KEY` secret. Add `ConfigCenter.get_version(version)` that searches encrypted history and raises `KeyError` when absent.

- [ ] **Step 4: Implement immutable embedding snapshots**

```python
@dataclass(frozen=True)
class EmbeddingConfigSnapshot:
    version: str
    state: Literal["enabled", "disabled", "misconfigured"]
    base_url: str
    api_key: str
    model: str
    dimensions: int
    batch_size: int
    timeout_seconds: float
```

Do not read `LLM_*` as fallback. Empty required keys return disabled; invalid numeric values and dimensions other than 1536 return misconfigured.

- [ ] **Step 5: Run Python and Web config tests**

Run: `uv run pytest tests/data_foundation/test_config.py tests/test_config_center.py -q`

Run: `cd web && pnpm test:unit`

Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add data_foundation/config.py config_center.py web/src/lib/server/config-store.ts .env.example tests/data_foundation/test_config.py tests/test_config_center.py
git commit -m "feat: add versioned embedding configuration"
```

## Task 4: Implement the Leased Outbox Repository

**Files:**
- Create: `data_foundation/outbox_repository.py`
- Create: `tests/data_foundation/test_outbox_repository.py`
- Modify: `data_foundation/repository.py`
- Modify: `tests/data_foundation/test_repository.py`

- [ ] **Step 1: Write failing PostgreSQL tests for dedupe, tenant isolation, lease ownership, and recovery**

```python
def test_enqueue_is_idempotent(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    first = repo.enqueue(tenant_id="a", topic="embedding_generate", dedupe_key="a:r:1:m:c", payload={})
    second = repo.enqueue(tenant_id="a", topic="embedding_generate", dedupe_key="a:r:1:m:c", payload={})
    assert first.id == second.id

def test_lost_lease_cannot_complete(migrated_conn):
    item = seeded_processing_item(migrated_conn, tenant_id="a", owner="worker-a")
    repo = OutboxRepository(migrated_conn)
    assert repo.complete(item.id, tenant_id="a", lease_owner="worker-b", status="succeeded") is False
```

Add a two-connection test proving `FOR UPDATE SKIP LOCKED` never leases one row twice.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_outbox_repository.py -q`

Expected: FAIL because `OutboxRepository` does not exist.

- [ ] **Step 3: Implement conditional state transitions**

Expose these methods with tenant required on every operation:

```python
enqueue(...)->OutboxItem
lease_ready(*, tenant_id, topics, lease_owner, batch_size, lease_seconds)->list[OutboxItem]
renew(*, item_id, tenant_id, lease_owner, lease_seconds)->bool
complete(*, item_id, tenant_id, lease_owner, status)->bool
fail(*, item_id, tenant_id, lease_owner, error, now=None)->bool
recover_expired(*, limit)->int
block_unavailable(*, topic, reason_code)->int
unblock_available(*, topic)->int
```

Every mutation includes current status and lease owner in `WHERE`. `fail()` computes retry/dead/blocked from `OperationalError`; retry 8 transitions to dead. Use PostgreSQL `now()` for leases and scheduling.

- [ ] **Step 4: Route `ResourceRepository.upsert_resource()` enqueue through structured requests**

Change `outbox_topics: list[str]` to `outbox_requests: list[OutboxRequest]`. Inside the existing resource transaction, prepend tenant/resource/version/topic to each request's `dedupe_parts`, hash the canonical sequence, and insert through `OutboxRepository` using the same connection. Remove `lease_outbox()` and `complete_outbox()` from `ResourceRepository` rather than wrapping them.

Create `data_foundation/outbox_requests.py` with `CHUNKER_VERSION = "text-v1"`, canonical Meilisearch/graph requests, and `embedding_request(snapshot, index_id)`. Update `creation_memory.py`, `performance_feedback.py`, and `feishu_sync.py` to use these builders. When no embedding profile exists, omit the embedding request; profile creation later enqueues a complete backfill. Never create an embedding task with an `unconfigured` model key.

- [ ] **Step 5: Run repository tests**

Run: `uv run pytest tests/data_foundation/test_outbox_repository.py tests/data_foundation/test_repository.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data_foundation/outbox_repository.py data_foundation/outbox_requests.py data_foundation/repository.py data_foundation/creation_memory.py data_foundation/performance_feedback.py data_foundation/feishu_sync.py tests/data_foundation/test_outbox_repository.py tests/data_foundation/test_outbox_requests.py tests/data_foundation/test_repository.py tests/data_foundation/test_creation_memory.py tests/data_foundation/test_performance_feedback.py tests/data_foundation/test_feishu_sync.py
git commit -m "feat: add leased multi-tenant outbox"
```

## Task 5: Replace the Fake Worker with a Processor Registry

**Files:**
- Create: `data_foundation/processors/base.py`
- Create: `data_foundation/processors/registry.py`
- Modify: `data_foundation/outbox_worker.py`
- Rewrite: `tests/data_foundation/test_outbox_worker.py`

- [ ] **Step 1: Delete fake-success tests and write registry-driven failing tests**

```python
async def test_unregistered_topic_is_blocked(repo, registry):
    item = outbox_item(topic="meili_index")
    result = await process_item(item, repo=repo, registry=registry, lease_owner="worker")
    assert result.status == "blocked"
    assert result.error_code == "PROCESSOR_DISABLED"

async def test_processor_result_controls_terminal_state(repo):
    registry = ProcessorRegistry({"embedding_generate": SucceedingProcessor()})
    result = await process_item(outbox_item(), repo=repo, registry=registry, lease_owner="worker")
    assert result.status == "succeeded"
```

- [ ] **Step 2: Run tests and verify the old worker fails**

Run: `uv run pytest tests/data_foundation/test_outbox_worker.py -q`

Expected: FAIL because the old worker marks known topics successful without a processor.

- [ ] **Step 3: Implement processor contracts and registry state**

```python
class Processor(Protocol):
    topic: str
    def state(self) -> ProcessorState: ...
    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult: ...

@dataclass(frozen=True)
class ProcessResult:
    status: Literal["succeeded", "superseded"]
    processed_count: int
```

Registry lookup returns an explicit disabled state for Meilisearch, Graphiti, and unknown topics. It never returns a no-op processor.

- [ ] **Step 4: Implement `LeaseGuard` and registry-driven `process_batch()`**

`LeaseGuard.assert_owned()` calls the repository renewal/ownership check before any database commit. `process_batch()` continues after per-item errors, but stores only redacted standardized errors.

Implement `LeaseGuard` as an async context manager with a renewal task running every one-third of the lease duration. Dispatch synchronous psycopg ownership checks through `asyncio.to_thread`; cancellation stops renewal, and failed renewal sets a lost-lease event checked before commit.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/data_foundation/test_outbox_worker.py -q`

Expected: PASS with no fake-success path.

- [ ] **Step 6: Commit**

```bash
git add data_foundation/processors data_foundation/outbox_worker.py tests/data_foundation/test_outbox_worker.py
git commit -m "feat: replace placeholder outbox processing"
```

## Task 6: Add Embedding Index Lifecycle and Atomic Storage

**Files:**
- Create: `data_foundation/embedding_repository.py`
- Create: `tests/data_foundation/test_embedding_repository.py`
- Modify: `data_foundation/search.py`
- Modify: `tests/data_foundation/test_search_graph_tools.py`

- [ ] **Step 1: Write failing tests for current-version and active-index semantics**

```python
def test_building_index_does_not_replace_active_until_complete(migrated_conn):
    repo = EmbeddingRepository(migrated_conn)
    active = repo.create_index(tenant_id="a", model="old", config_version="v1", expected_resources=1)
    repo.mark_resource_complete(active.id, tenant_id="a", resource_id="resource-1")
    repo.activate_if_complete(active.id, tenant_id="a")
    building = repo.create_index(tenant_id="a", model="new", config_version="v2", expected_resources=2)
    assert repo.active_index("a").id == active.id
    assert repo.activate_if_complete(building.id, tenant_id="a") is False

def test_store_batch_rejects_stale_resource_version(migrated_conn):
    repo, resource = seeded_versioned_resource(migrated_conn, versions=2)
    assert repo.store_batch(resource_id=resource.id, resource_version=1, vectors=valid_vectors()) == "superseded"

def test_new_profile_enqueues_complete_backfill_once(migrated_conn):
    service = build_embedding_index_service(migrated_conn, profile="v2")
    first = service.reconcile_tenant("a")
    second = service.reconcile_tenant("a")
    assert first.enqueued == current_embeddable_resource_count(migrated_conn, "a")
    assert second.enqueued == 0

def test_zero_resource_index_activates_immediately(migrated_conn):
    service = build_embedding_index_service(migrated_conn, profile="v1")
    result = service.reconcile_tenant("empty-tenant")
    assert result.activated is True
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_embedding_repository.py tests/data_foundation/test_embedding_service.py -q`

Expected: FAIL because the repository and versioned schema behavior are absent.

- [ ] **Step 3: Implement index lifecycle and atomic vector batch storage**

`store_batch()` checks the current maximum resource version, validates every vector before opening the write transaction, deletes/replaces only the target index/resource/version rows, and increments completed resources once. `activate_if_complete()` locks tenant indexes and switches building/active/retired in one transaction only when completed equals expected and failed is zero.

Create `EmbeddingIndexService.reconcile_tenant(tenant_id)`. It reads the desired immutable profile, reuses an existing index for the same config/model/chunker version, or creates one building index and enqueues one deduplicated embedding request for every active resource with non-empty text. It activates an empty index immediately and never switches away from the old active index until all expected resources complete.

- [ ] **Step 4: Update semantic SQL to join current versions and the active index**

The query must join `embedding_indexes status='active'`, match tenant/model/chunker version, and join the maximum `resource_versions.version`. Remove paths that accept an arbitrary model without an active index.

- [ ] **Step 5: Run embedding and search tests**

Run: `uv run pytest tests/data_foundation/test_embedding_repository.py tests/data_foundation/test_embedding_service.py tests/data_foundation/test_search_graph_tools.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data_foundation/embedding_repository.py data_foundation/embedding_service.py data_foundation/search.py tests/data_foundation/test_embedding_repository.py tests/data_foundation/test_embedding_service.py tests/data_foundation/test_search_graph_tools.py
git commit -m "feat: add atomic embedding index lifecycle"
```

## Task 7: Implement the Real Embedding Processor

**Files:**
- Create: `data_foundation/processors/embedding.py`
- Create: `tests/data_foundation/test_embedding_processor.py`
- Modify: `data_foundation/feishu_sync.py`
- Modify: `tests/data_foundation/test_feishu_sync.py`
- Modify: `data_foundation/tools.py`

- [ ] **Step 1: Write failing HTTP and rollback tests with respx**

```python
@respx.mock
async def test_embedding_processor_writes_complete_batch(processor, item):
    respx.post("https://embed.test/v1/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [vector_row(0), vector_row(1)]})
    )
    result = await processor.process(item, OwnedLease())
    assert result.status == "succeeded"

@respx.mock
async def test_dimension_mismatch_writes_nothing(processor, item, embedding_repo):
    respx.post("https://embed.test/v1/embeddings").mock(
        return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1]}]})
    )
    with pytest.raises(PermanentProcessingError, match="EMBEDDING_DIMENSION_MISMATCH"):
        await processor.process(item, OwnedLease())
    assert embedding_repo.stored_batches == []
```

Add 429 `Retry-After`, timeout, 401 blocked, response ordering, and stale-version tests.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_embedding_processor.py -q`

Expected: FAIL because the processor is absent.

- [ ] **Step 3: Implement deterministic chunking and OpenAI-compatible batching**

```python
def chunk_text(text: str, max_chars: int = 2000, overlap: int = 200) -> list[str]:
    normalized = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").split("\n")).strip()
    if not normalized:
        return []
    chunks, start = [], 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = end - overlap
    return chunks
```

Import `CHUNKER_VERSION` from `data_foundation.outbox_requests`. Use one immutable config snapshot per item, `httpx.AsyncClient` with configured timeout, response-index ordering, finite numeric validation, exact dimensions, and `LeaseGuard.assert_owned()` immediately before `store_batch()`.

- [ ] **Step 4: Replace pending embedding rows with versioned outbox enqueue**

`feishu_sync.py` must stop calling `replace_embedding_chunks()`. All resource-producing services use the Task 4 `OutboxRequest` helper to enqueue `embedding_generate` with resource version, desired index/profile, and chunker version. Remove `replace_embedding_chunks()` and direct `set_embedding()` from `ResourceRepository` after call sites migrate.

- [ ] **Step 5: Remove semantic-search fallback to chat model configuration**

`data_foundation/tools.py` resolves the active index profile. If none is active, return the existing structured fallback to keyword search; never read `LLM_API_KEY` or `LLM_BASE_URL` for embeddings.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest tests/data_foundation/test_embedding_processor.py tests/data_foundation/test_feishu_sync.py tests/data_foundation/test_search_graph_tools.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add data_foundation/processors/embedding.py data_foundation/feishu_sync.py data_foundation/creation_memory.py data_foundation/performance_feedback.py data_foundation/tools.py data_foundation/repository.py tests/data_foundation/test_embedding_processor.py tests/data_foundation/test_feishu_sync.py tests/data_foundation/test_creation_memory.py tests/data_foundation/test_performance_feedback.py tests/data_foundation/test_search_graph_tools.py
git commit -m "feat: generate real versioned embeddings"
```

## Task 8: Implement Sync Source Leasing and Fair Tenant Discovery

**Files:**
- Create: `data_foundation/source_repository.py`
- Create: `tests/data_foundation/test_source_repository.py`

- [ ] **Step 1: Write failing source lease and fairness tests**

```python
def test_due_tenants_are_ordered_by_last_dispatch(migrated_conn):
    repo = SourceRepository(migrated_conn)
    seed_source(repo, tenant_id="busy", last_dispatched_at="2026-06-20T02:00:00Z")
    seed_source(repo, tenant_id="waiting", last_dispatched_at=None)
    assert repo.discover_due_tenants(limit=10)[:2] == ["waiting", "busy"]

def test_source_lease_is_tenant_scoped(migrated_conn):
    source = seed_source(SourceRepository(migrated_conn), tenant_id="a")
    assert SourceRepository(migrated_conn).renew_source(source.id, tenant_id="b", lease_owner="worker") is False
```

Add two-connection `SKIP LOCKED`, stale run recovery, and cursor persistence tests.

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_source_repository.py -q`

Expected: FAIL because `SourceRepository` is absent.

- [ ] **Step 3: Implement source registration, secrets isolation, fair discovery, and runs**

Expose `register_source`, `get_source_with_secrets`, `discover_due_tenants`, `lease_due_source`, `renew_source`, `finish_source`, `start_run`, `finish_run`, and `recover_stale_runs`. Public source records exclude credentials; only `get_source_with_secrets()` returns them to a source processor.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/data_foundation/test_source_repository.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/source_repository.py tests/data_foundation/test_source_repository.py
git commit -m "feat: add leased sync source registry"
```

## Task 9: Implement Feishu Source Processors

**Files:**
- Create: `data_foundation/sources/base.py`
- Create: `data_foundation/sources/registry.py`
- Create: `data_foundation/sources/feishu.py`
- Create: `tests/data_foundation/test_feishu_source_processor.py`
- Modify: `data_foundation/sync_service.py`
- Modify: `tests/data_foundation/test_sync_service.py`

- [ ] **Step 1: Write failing Base/Wiki source contract tests**

```python
async def test_feishu_base_source_uses_registered_identity_and_repository(source, repo):
    result = await FeishuBaseSourceProcessor(loader=fake_base_loader, repo=repo).sync(source, OwnedLease())
    assert result.created == 2
    assert repo.upserts[0]["mapping"]["system"] == "feishu"

async def test_feishu_credentials_never_appear_in_result(source_with_secret):
    result = await failing_feishu_processor.sync(source_with_secret, OwnedLease())
    assert source_with_secret.credentials["access_token"] not in result.error_summary
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_feishu_source_processor.py -q`

Expected: FAIL because source contracts/processors are absent.

- [ ] **Step 3: Implement Feishu source processors around existing loaders**

Base and Wiki processors validate source config, construct runtime identity from source credentials, call existing loader functions, and pass normalized rows/documents through `sync_base_rows()`/`sync_wiki_documents()`. They renew the source lease between pages/documents and return counts/cursor without credentials.

- [ ] **Step 4: Route manual sync through the same processor registry**

Keep the DeepAgents tool contract unchanged, but make `sync_feishu_sources()` create an in-memory source request and invoke the registered source processor. Manual and scheduled paths must share normalization and repository writes.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/data_foundation/test_feishu_source_processor.py tests/data_foundation/test_sync_service.py tests/data_foundation/test_feishu_sync.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data_foundation/sources data_foundation/sync_service.py tests/data_foundation/test_feishu_source_processor.py tests/data_foundation/test_sync_service.py
git commit -m "feat: schedule Feishu source ingestion"
```

## Task 10: Implement Read-Only PostgreSQL Source Ingestion

**Files:**
- Create: `data_foundation/sources/postgres.py`
- Create: `tests/data_foundation/test_postgres_source_processor.py`

- [ ] **Step 1: Write failing validation, read-only, pagination, and redaction tests**

```python
def test_postgres_source_rejects_arbitrary_sql():
    with pytest.raises(SourceConfigError):
        PostgresTableConfig.from_dict({"sql": "drop table users"})

def test_postgres_source_rejects_dangerous_identifier():
    with pytest.raises(SourceConfigError):
        PostgresTableConfig.from_dict(valid_mapping() | {"table": "records;drop table x"})

async def test_postgres_source_keyset_paginates_and_updates_cursor(source, external_postgres):
    result = await processor.sync(source, OwnedLease())
    assert result.read == 3
    assert result.cursor == "3"
    assert external_postgres.observed_transaction_read_only is True
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_postgres_source_processor.py -q`

Expected: FAIL because the processor is absent.

- [ ] **Step 3: Implement structured mapping and safe SQL composition**

```python
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

@dataclass(frozen=True)
class PostgresTableConfig:
    schema: str
    table: str
    primary_key: str
    title_column: str
    content_columns: tuple[str, ...]
    updated_at_column: str | None
    resource_type: str
    page_size: int
```

Build SELECT statements only with `psycopg.sql.Identifier`; values use parameters. Start `SET TRANSACTION READ ONLY`, set local statement timeout, use keyset `primary_key > cursor`, and renew the lease after every page. Reject non-PostgreSQL DSNs before connecting.

Dispatch blocking external psycopg page reads through `asyncio.to_thread` so ingestion cannot block the LangGraph event loop.

- [ ] **Step 4: Upsert external rows through the universal repository**

Use mapping system `postgres`, external type `<schema>.<table>`, and primary key as external ID. Store configured content fields in `content_json`, deterministic joined text in `content_text`, and the external timestamp when configured.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/data_foundation/test_postgres_source_processor.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data_foundation/sources/postgres.py tests/data_foundation/test_postgres_source_processor.py
git commit -m "feat: ingest structured PostgreSQL sources"
```

## Task 11: Persist Service Telemetry and Retention Aggregates

**Files:**
- Create: `data_foundation/telemetry_repository.py`
- Create: `tests/data_foundation/test_telemetry_repository.py`

- [ ] **Step 1: Write failing instance, execution, redaction, and retention tests**

```python
def test_heartbeat_is_scoped_to_instance_and_deployment(migrated_conn):
    repo = TelemetryRepository(migrated_conn)
    repo.register_instance(component="scheduler", instance_id="i1", deployment_id="d1", config_version="v1")
    repo.heartbeat(component="scheduler", instance_id="i1", deployment_id="d1")
    assert repo.instance("scheduler", "i1").deployment_id == "d1"

def test_finish_execution_redacts_secrets(migrated_conn):
    repo = TelemetryRepository(migrated_conn)
    repo.finish_execution("e1", outcome="failed", error=OperationalError("AUTH_INVALID", BLOCKED, "password=secret"))
    assert "secret" not in repo.execution("e1").error_summary
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_telemetry_repository.py -q`

Expected: FAIL because the repository is absent.

- [ ] **Step 3: Implement factual telemetry only**

Expose register/heartbeat/stop instance, start/finish execution, aggregate expired errors, and batched cleanup. Do not store health labels. Cleanup limits each statement, uses `SKIP LOCKED`, and aggregates dead/blocked facts before deleting 90-day details.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/data_foundation/test_telemetry_repository.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/telemetry_repository.py tests/data_foundation/test_telemetry_repository.py
git commit -m "feat: persist operational execution facts"
```

## Task 12: Rewrite Scheduler Orchestration

**Files:**
- Rewrite: `data_foundation/scheduler.py`
- Rewrite: `tests/data_foundation/test_scheduler.py`
- Modify: `data_foundation/outbox_worker.py`

- [ ] **Step 1: Delete daemon-thread tests and write one-cycle orchestration tests**

```python
async def test_cycle_dispatches_one_batch_per_tenant_in_fair_order(scheduler):
    scheduler.discovery.tenants = ["waiting", "busy"]
    stats = await scheduler.run_cycle()
    assert scheduler.outbox.calls == ["waiting", "busy"]
    assert stats.tenants_visited == 2

async def test_cycle_records_exception_instead_of_swallowing(scheduler):
    scheduler.outbox.raise_error = RuntimeError("token=secret")
    stats = await scheduler.run_cycle()
    assert stats.failed == 1
    assert "secret" not in scheduler.telemetry.finished[0].error_summary
```

- [ ] **Step 2: Run tests and verify the old scheduler fails**

Run: `uv run pytest tests/data_foundation/test_scheduler.py -q`

Expected: FAIL because the old scheduler owns a daemon loop and default tenant.

- [ ] **Step 3: Implement a finite `run_cycle()`**

The cycle order is: heartbeat, recover expired source/outbox leases, unblock available processors, discover fair tenants, lease at most one due source and one outbox batch per tenant, record each execution, attempt index activation, run bounded retention cleanup, and return immutable stats. No `while True`, `threading.Thread`, module `_started`, or empty exception handler remains in this file.

- [ ] **Step 4: Run scheduler and worker tests**

Run: `uv run pytest tests/data_foundation/test_scheduler.py tests/data_foundation/test_outbox_worker.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/scheduler.py data_foundation/outbox_worker.py tests/data_foundation/test_scheduler.py
git commit -m "feat: orchestrate fair multi-tenant cycles"
```

## Task 13: Move Lifecycle into LangGraph `http.app`

**Files:**
- Create: `data_foundation/supervisor.py`
- Create: `data_foundation/http_app.py`
- Create: `tests/data_foundation/test_supervisor.py`
- Create: `tests/data_foundation/test_http_app.py`
- Modify: `langgraph.json`
- Modify: `pyproject.toml`
- Modify: `agent.py`
- Modify: `tests/test_agent_assembly.py`

- [ ] **Step 1: Write failing lifecycle and import-safety tests**

```python
async def test_supervisor_starts_once_and_stops_gracefully():
    supervisor = BackgroundServiceSupervisor(fake_scheduler, interval_seconds=1)
    await supervisor.start()
    await supervisor.start()
    assert supervisor.start_count == 1
    await supervisor.stop(grace_seconds=1)
    assert supervisor.accepting_work is False

def test_agent_import_does_not_start_background_services(monkeypatch):
    monkeypatch.setattr("data_foundation.supervisor.BackgroundServiceSupervisor.start", forbidden)
    importlib.reload(importlib.import_module("agent"))
```

- [ ] **Step 2: Run tests and verify failure**

Run: `uv run pytest tests/data_foundation/test_supervisor.py tests/data_foundation/test_http_app.py tests/test_agent_assembly.py -q`

Expected: FAIL because `agent.py` still calls `start_background_services()`.

- [ ] **Step 3: Implement async supervisor and Starlette lifespan**

```python
@asynccontextmanager
async def lifespan(_: Starlette):
    supervisor = build_supervisor()
    await supervisor.start()
    try:
        yield {"supervisor": supervisor}
    finally:
        await supervisor.stop(grace_seconds=settings.shutdown_grace_seconds)

app = Starlette(routes=[], lifespan=lifespan)
```

Supervisor owns one asyncio task, waits with `asyncio.Event` rather than blocking sleep, and records stopped instance state in `finally`.

Dispatch all synchronous repository calls through `asyncio.to_thread`; the supervisor event loop must not execute blocking psycopg calls directly.

- [ ] **Step 4: Register the official custom app and remove graph-import startup**

```json
"http": {
  "app": "./data_foundation/http_app.py:app",
  "enable_custom_route_auth": false
}
```

Remove the scheduler import and `start_background_services()` call from `agent.py`. Do not add a CLI service entrypoint.

Add `starlette>=0.46.0,<1.0.0` to project dependencies because `data_foundation/http_app.py` imports Starlette directly.

- [ ] **Step 5: Run lifecycle and agent tests**

Run: `uv run pytest tests/data_foundation/test_supervisor.py tests/data_foundation/test_http_app.py tests/test_agent_assembly.py -q`

Expected: PASS.

- [ ] **Step 6: Start LangGraph locally and verify lifespan logs exactly once**

Run: `uv run langgraph dev --port 2030 --no-browser`

Expected: `/ok` returns 200, one scheduler instance is registered, and stopping the process records `stopped_at`.

- [ ] **Step 7: Commit**

```bash
git add data_foundation/supervisor.py data_foundation/http_app.py langgraph.json pyproject.toml uv.lock agent.py tests/data_foundation/test_supervisor.py tests/data_foundation/test_http_app.py tests/test_agent_assembly.py
git commit -m "feat: run background services in LangGraph lifespan"
```

## Task 14: Complete Integration and Remove Legacy APIs

**Files:**
- Modify: `data_foundation/repository.py`
- Modify: `data_foundation/sync_service.py`
- Delete obsolete code from: `data_foundation/outbox_worker.py`, `data_foundation/scheduler.py`
- Modify: `README.md`
- Modify: `tests/data_foundation/test_tools.py`
- Modify: `tests/data_foundation/test_repository.py`

- [ ] **Step 1: Add contract tests proving legacy methods and globals are gone**

```python
def test_legacy_runtime_symbols_are_removed():
    import data_foundation.scheduler as scheduler
    import data_foundation.outbox_worker as worker
    assert not hasattr(scheduler, "start_background_services")
    assert not hasattr(scheduler, "_started")
    assert not hasattr(worker, "SUPPORTED_TOPICS")
    assert not hasattr(worker, "_process_item")

def test_resource_repository_no_longer_owns_worker_methods():
    assert not hasattr(ResourceRepository, "lease_outbox")
    assert not hasattr(ResourceRepository, "complete_outbox")
```

- [ ] **Step 2: Run contract tests and verify failure before cleanup**

Run: `uv run pytest tests/data_foundation/test_repository.py tests/data_foundation/test_tools.py -q`

Expected: FAIL while any legacy method remains.

- [ ] **Step 3: Remove all old code and update documentation**

Delete old functions, imports, comments, status names, and fallback paths. README must state: PostgreSQL is authoritative, embedding is the only active outbox processor, Meilisearch/Graphiti are disabled, source credentials are plaintext in PostgreSQL, and services start through LangGraph ASGI lifespan.

- [ ] **Step 4: Run all Python tests**

Run: `uv run pytest -q`

Expected: all enabled tests PASS; PostgreSQL tests may only skip when `TEST_XHS_DATABASE_URL` is absent.

- [ ] **Step 5: Commit**

```bash
git add data_foundation README.md tests
git commit -m "refactor: remove legacy scheduler and outbox paths"
```

## Task 15: Verify Configuration UI and Whole-Repo Quality

**Files:**
- Verify: `web/src/lib/server/config-store.ts`
- Verify: `config_center.py`

- [ ] **Step 1: Run focused Python configuration tests**

Run: `uv run pytest tests/test_config_center.py tests/data_foundation/test_config.py -q`

Expected: PASS with embedding API key redacted and historical versions readable by backend only.

- [ ] **Step 2: Run Web unit, type, lint, and build checks**

Run: `cd web && pnpm test:unit`

Run: `cd web && pnpm exec tsc --noEmit`

Run: `cd web && pnpm lint`

Run: `cd web && pnpm build`

Expected: tests/type/build PASS; lint has no new errors and only pre-existing warnings.

- [ ] **Step 3: Run the full Python suite with the existing PostgreSQL database in isolated schemas**

Set `TEST_XHS_DATABASE_URL` to the same development PostgreSQL DSN as `XHS_DATABASE_URL`; the fixture creates and drops unique schemas, so no separate test database is required.

Run: `uv run pytest -q`

Expected: no PostgreSQL skips and all tests PASS.

- [ ] **Step 4: Run formatting/diff checks**

Run: `git diff --check`

Expected: no output.

## Task 16: Clean Development Deployment and Production Smoke Test

**Files:**
- Verify: `README.md`
- Verify: `.env.example`

- [ ] **Step 1: Verify the server has no Phase 3/4 business rows before reset**

Run a read-only count across every allowlisted business table and record the result. Abort if any table contains data the user has not approved deleting. `lark_uat_tokens` and configuration files are not part of this count.

- [ ] **Step 2: Stop only the application processes, not PostgreSQL**

Run on the server: `pm2 stop xhs-backend xhs-frontend`

Expected: both application processes stop; the `pg-db` container remains running.

- [ ] **Step 3: Reset only allowlisted data foundation tables and run the new schema**

Run from the project root with the deployed virtualenv:

```bash
.venv/bin/python -c "from dotenv import load_dotenv; load_dotenv(); from data_foundation.db import connect, reset_data_foundation; c=connect(); reset_data_foundation(c); c.close()"
```

Expected: all 15 business tables exist; `lark_uat_tokens` and config-center files still exist.

- [ ] **Step 4: Install/build and restart both application processes**

Run: `.venv/bin/python -m pip install -e .`

Run: `cd web && npx -y pnpm@10.5.1 install --frozen-lockfile && npx -y pnpm@10.5.1 build`

Run: `pm2 restart xhs-backend --update-env && pm2 restart xhs-frontend --update-env && pm2 save`

Expected: both processes remain online without restart loops.

- [ ] **Step 5: Verify runtime facts rather than process status alone**

Verify:

```text
GET http://127.0.0.1:2030/ok -> 200
GET http://127.0.0.1:9091/ -> 200
service_instances has one current scheduler heartbeat
service_executions records successful cycles
unconfigured Meilisearch/Graphiti tasks cannot become succeeded
embedding processor reports disabled until all independent keys are configured
```

- [ ] **Step 6: Configure an embedding profile and run one real resource smoke test**

Save the six embedding keys through the existing admin config path. Insert or synchronize one resource, wait for one scheduler cycle, and verify a 1536-dimensional row exists for its current version under the active index. Verify semantic search returns that resource.

- [ ] **Step 7: Remove smoke data and restore an empty operational baseline**

Stop the backend, call the same allowlisted `reset_data_foundation()` function, restart the backend, and wait for a fresh scheduler heartbeat. Verify resource/source/outbox/embedding tables are empty while service instance and execution facts begin advancing again.

- [ ] **Step 8: Verify clean Git state**

Run: `git status --short`

Expected: no generated metadata or runtime files are tracked.

## Final Verification

- [ ] `uv run pytest -q` passes with PostgreSQL integration tests enabled.
- [ ] `cd web && pnpm test:unit` passes.
- [ ] `cd web && pnpm exec tsc --noEmit` passes.
- [ ] `cd web && pnpm lint` has no new errors.
- [ ] `cd web && pnpm build` passes.
- [ ] `git diff --check` produces no output.
- [ ] Server Git revision matches the pushed revision.
- [ ] Server data foundation schema contains exactly the 15 designed business tables.
- [ ] `lark_uat_tokens` and configuration data survive the clean reset.
- [ ] Scheduler heartbeat and execution facts advance over two intervals.
- [ ] No legacy daemon thread, fake-success processor, old status, or compatibility alias remains.
