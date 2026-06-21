# Universal Scheduler Tenant Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure scheduler work discovery, embedding reconciliation, and ready outbox processing work for universal Postgres resources even when a tenant has no Feishu sync source.

**Architecture:** Keep source discovery in `SourceRepository`, ready outbox discovery in `OutboxRepository`, and profile-aware missing-embedding discovery in `EmbeddingIndexService`. `Scheduler` merges bounded lists with source ordering plus one non-source reservation, then uses its existing source -> processor -> outbox sequence. Embedding completion counts are recomputed from current resource versions so revisions cannot drift index state.

**Tech Stack:** Python 3.12, psycopg/PostgreSQL, pgvector, pytest, LangGraph ASGI lifespan, PM2.

---

### Task 1: Add Bounded Work-Tenant Repository Queries

**Files:**
- Modify: `data_foundation/schema.sql`
- Modify: `data_foundation/outbox_repository.py`
- Modify: `data_foundation/embedding_service.py`
- Test: `tests/data_foundation/test_schema.py`
- Test: `tests/data_foundation/test_outbox_repository.py`
- Test: `tests/data_foundation/test_embedding_service.py`

- [ ] **Step 1: Write failing schema and repository tests**

```python
def test_schema_declares_universal_work_discovery_indexes():
    schema = Path("data_foundation/schema.sql").read_text(encoding="utf-8").lower()
    assert "idx_resources_embedding_work_tenants" in schema
    assert "idx_resource_outbox_ready_tenants" in schema

def test_ready_tenants_returns_due_pending_and_retry_once(migrated_conn):
    repo = OutboxRepository(migrated_conn)
    # Seed due pending/retry work for alpha and non-ready work for other tenants.
    assert repo.discover_ready_tenants(limit=10) == ["alpha"]

def test_embedding_reconcile_tenants_excludes_currently_covered_resources(migrated_conn):
    service = EmbeddingIndexService(migrated_conn, profile=_profile("cfg-v1"))
    # Seed one current resource missing cfg-v1 coverage and one fully covered resource.
    assert service.discover_reconcile_tenants(limit=10) == ["needs-index"]
```

- [ ] **Step 2: Verify the tests fail**

Run: `uv run pytest tests/data_foundation/test_schema.py tests/data_foundation/test_outbox_repository.py tests/data_foundation/test_embedding_service.py -q`

Expected: failures for missing indexes and discovery methods.

- [ ] **Step 3: Add partial indexes and repository methods**

Add:

```sql
create index if not exists idx_resources_embedding_work_tenants
  on resources (tenant_id, id)
  where status = 'active'
    and nullif(trim(coalesce(content_text, '')), '') is not null;

create index if not exists idx_resource_outbox_ready_tenants
  on resource_outbox (next_attempt_at, tenant_id)
  where status in ('pending', 'retry');
```

Implement `OutboxRepository.discover_ready_tenants(limit)` with a due `pending/retry` grouped query ordered by `min(next_attempt_at), tenant_id` and bounded to 1..100.

Implement `EmbeddingIndexService.discover_reconcile_tenants(limit)`. Select only tenants where a current active/nonblank resource version lacks embeddings in an index matching the service profile's model, config version, and chunker version. Order by tenant id and bound the query.

- [ ] **Step 4: Verify repository tests pass**

Run: `uv run pytest tests/data_foundation/test_schema.py tests/data_foundation/test_outbox_repository.py tests/data_foundation/test_embedding_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/schema.sql data_foundation/outbox_repository.py data_foundation/embedding_service.py tests/data_foundation/test_schema.py tests/data_foundation/test_outbox_repository.py tests/data_foundation/test_embedding_service.py
git commit -m "feat: discover universal scheduler work tenants"
```

### Task 2: Merge Universal Worklists Fairly in Scheduler

**Files:**
- Modify: `data_foundation/scheduler.py`
- Test: `tests/data_foundation/test_scheduler.py`

- [ ] **Step 1: Write failing scheduler tests**

Extend fakes with `discover_ready_tenants()` and `discover_reconcile_tenants()`, then add:

```python
@pytest.mark.asyncio
async def test_cycle_processes_embedding_tenant_without_sync_source():
    scheduler = _scheduler(source_tenants=[], embedding_tenants=["generated"], ready_tenants=[])
    stats = await scheduler.run_cycle()
    assert stats.tenants_visited == 1
    assert scheduler.embedding_service.calls == ["generated"]

@pytest.mark.asyncio
async def test_cycle_reserves_non_source_slot_when_due_sources_fill_limit():
    scheduler = _scheduler(
        source_tenants=["s1", "s2", "s3"],
        embedding_tenants=["generated"],
        ready_tenants=[],
        tenant_limit=3,
    )
    await scheduler.run_cycle()
    assert scheduler.outbox_runner.calls == ["s1", "s2", "generated"]

@pytest.mark.asyncio
async def test_cycle_deduplicates_tenants_across_work_categories():
    scheduler = _scheduler(
        source_tenants=["shared"], embedding_tenants=["shared"], ready_tenants=["shared"]
    )
    assert (await scheduler.run_cycle()).tenants_visited == 1
```

- [ ] **Step 2: Verify tests fail**

Run: `uv run pytest tests/data_foundation/test_scheduler.py -q`

Expected: failures because the scheduler uses only `discover_due_tenants()`.

- [ ] **Step 3: Implement bounded worklist merge**

Add `Scheduler._discover_work_tenants()`:

```python
source = self.source_repo.discover_due_tenants(limit=limit)
embedding = self.embedding_service.discover_reconcile_tenants(limit=limit) if self.embedding_service else []
ready = self.outbox_repo.discover_ready_tenants(limit=limit)
non_source = _unique(embedding + ready, excluded=set(source))
source_budget = limit if limit == 1 or not non_source else limit - 1
return _unique(source[:source_budget] + non_source + source[source_budget:])[:limit]
```

Use the method in `_run_cycle_body()`. Leave `_process_one_source()` unchanged: it already reports zero source work for a non-source tenant.

- [ ] **Step 4: Verify scheduler tests pass**

Run: `uv run pytest tests/data_foundation/test_scheduler.py -q`

Expected: PASS, including existing source ordering and disabled processor coverage.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/scheduler.py tests/data_foundation/test_scheduler.py
git commit -m "feat: schedule universal tenant work fairly"
```

### Task 3: Make Embedding Counts Version-Consistent

**Files:**
- Modify: `data_foundation/embedding_repository.py`
- Test: `tests/data_foundation/test_embedding_repository.py`

- [ ] **Step 1: Write failing revision-count test**

```python
def test_storing_revised_resource_keeps_index_completion_equal_to_current_resources(migrated_conn):
    # Create one-index/one-resource coverage, then store version 2 for that resource.
    index = repository.get_index(index_id)
    assert index.expected_resources == 1
    assert index.completed_resources == 1
```

- [ ] **Step 2: Verify it fails**

Run: `uv run pytest tests/data_foundation/test_embedding_repository.py::test_storing_revised_resource_keeps_index_completion_equal_to_current_resources -q`

Expected: FAIL because completion is currently a monotonic increment across versions.

- [ ] **Step 3: Recompute counters transactionally**

After `store_batch()` replaces vectors, recompute the target index's expected and completed count from active/nonblank resources and their current maximum `resource_versions.version`. Count coverage only for vectors belonging to that index and current resource versions; do not increment a historical counter.

- [ ] **Step 4: Verify embedding tests pass**

Run: `uv run pytest tests/data_foundation/test_embedding_repository.py tests/data_foundation/test_embedding_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/embedding_repository.py tests/data_foundation/test_embedding_repository.py
git commit -m "fix: keep embedding index counts version-consistent"
```

### Task 4: Full Verification and Server Smoke Test

**Files:**
- Modify: documentation only if verification exposes a corrected design fact.

- [ ] **Step 1: Run local checks**

```bash
uv run pytest -q
cd web && corepack pnpm test:unit
cd web && corepack pnpm exec tsc --noEmit
cd web && corepack pnpm lint
cd web && corepack pnpm build
git diff --check
```

Expected: commands exit 0; record existing warnings separately.

- [ ] **Step 2: Push and run server regression**

Run the full test suite with `TEST_XHS_DATABASE_URL` loaded from the server's `.env`.

Expected: real PostgreSQL integration tests pass.

- [ ] **Step 3: Run universal-resource smoke test**

Insert one `generated_copy` via `ResourceRepository` for the default tenant, wait two scheduler intervals, then verify one active 1536-dimensional index has vectors and `semantic_search_resources` returns the resource id.

- [ ] **Step 4: Restore empty baseline**

Stop only `xhs-backend`, call `reset_data_foundation()`, restart it, wait two scheduler intervals, and verify resources, sync sources, outbox, vectors, and indexes are zero while scheduler heartbeat advances.

- [ ] **Step 5: Confirm clean Git**

```bash
git status --short
git log -1 --oneline
```

Expected: clean working tree and pushed `master`.

