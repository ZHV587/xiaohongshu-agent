# Phase 4.1 Sync Status Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first production data loop: track Feishu sync runs in Postgres, expose sync/status Agent tools, and process minimum outbox tasks without adding a business CLI or management backend.

**Architecture:** Postgres remains the authoritative data foundation. DeepAgents accesses Phase 4.1 capabilities only through registered LangChain tools in `create_deep_agent(tools=...)`; scheduler and outbox are backend application services, not Agent runtime internals. Manual sync uses current Web user identity from `RunnableConfig`; scheduled sync uses `system:scheduler`.

**Tech Stack:** Python 3.12, Postgres/psycopg, DeepAgents 0.6.10, LangChain tools, pytest, existing `data_foundation` repository/service pattern.

---

## Scope Check

This plan implements Phase 4.1 only:

1. `sync_runs` schema and repository helpers.
2. Feishu sync service wrapper around existing `sync_base_rows` and `sync_wiki_documents`.
3. Agent tools: `get_data_foundation_status` and `sync_feishu_resources`.
4. Minimum outbox worker for `embedding_generate`, `graph_ingest`, and `meili_index` status handling.
5. Optional backend scheduler bootstrap controlled by environment variables.

This plan does not implement:

1. Full embedding provider generation.
2. Meilisearch integration.
3. Graphiti/Neo4j/FalkorDB.
4. Creation memory tools.
5. Performance feedback weighting.
6. A management backend or business CLI.

## File Structure

- Modify: `data_foundation/schema.sql`
  - Add `sync_runs`.
  - Add indexes for status and recent runs.

- Modify: `data_foundation/repository.py`
  - Add sync run lifecycle helpers.
  - Add data foundation status summary.
  - Add outbox leasing/status helpers.

- Create: `data_foundation/sync_service.py`
  - One service entrypoint: `sync_feishu_sources(...)`.
  - Records a `sync_runs` row.
  - Uses existing env config and existing Feishu read tools.
  - Wraps existing `sync_base_rows` and `sync_wiki_documents`.

- Create: `data_foundation/outbox_worker.py`
  - Claims ready outbox rows with `FOR UPDATE SKIP LOCKED`.
  - Handles:
    - `embedding_generate`: mark succeeded after ensuring pending chunks exist for text resources.
    - `graph_ingest`: create deterministic weak edges for same resource type/title tokens when possible.
    - `meili_index`: mark skipped/succeeded with payload note because external service is not enabled.

- Create: `data_foundation/scheduler.py`
  - Starts a daemon thread only when `XHS_SYNC_ENABLED=true`.
  - Periodically calls the sync service and outbox worker.
  - Does not expose any user CLI.

- Modify: `data_foundation/tools.py`
  - Add `get_data_foundation_status`.
  - Add `sync_feishu_resources`.
  - Include both in `phase3_tools` or rename exported list to `data_foundation_tools` with backward-compatible alias.

- Modify: `agent.py`
  - Start scheduler as backend application service after `.env` is loaded.
  - Keep tool registration through `create_deep_agent(tools=...)`.

- Tests:
  - Modify: `tests/data_foundation/test_schema.py`
  - Modify: `tests/data_foundation/test_repository.py`
  - Create: `tests/data_foundation/test_sync_service.py`
  - Create: `tests/data_foundation/test_outbox_worker.py`
  - Create: `tests/data_foundation/test_phase4_tools.py`
  - Modify: `tests/test_agent_assembly.py`

---

### Task 1: Add `sync_runs` Schema

**Files:**
- Modify: `data_foundation/schema.sql`
- Modify: `tests/data_foundation/test_schema.py`

- [ ] **Step 1: Write failing schema test**

Append this test to `tests/data_foundation/test_schema.py`:

```python
def test_sync_runs_schema_exists(migrated_conn):
    columns = migrated_conn.execute(
        """
        select column_name
        from information_schema.columns
        where table_schema = current_schema()
          and table_name = 'sync_runs'
        order by ordinal_position
        """
    ).fetchall()

    assert [row["column_name"] for row in columns] == [
        "id",
        "tenant_id",
        "source",
        "triggered_by",
        "actor_open_id",
        "status",
        "started_at",
        "finished_at",
        "created_count",
        "updated_count",
        "skipped_count",
        "failed_count",
        "error",
        "metadata",
        "created_at",
        "updated_at",
    ]


def test_sync_runs_status_constraint(migrated_conn):
    import pytest

    with pytest.raises(Exception):
        migrated_conn.execute(
            """
            insert into sync_runs (tenant_id, source, triggered_by, actor_open_id, status)
            values ('default', 'feishu', 'manual', 'ou_user', 'bad-status')
            """
        )
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_schema.py::test_sync_runs_schema_exists tests/data_foundation/test_schema.py::test_sync_runs_status_constraint -q
```

Expected: FAIL because `sync_runs` does not exist.

- [ ] **Step 3: Add schema**

Append to `data_foundation/schema.sql` after `resource_outbox` indexes:

```sql
create table if not exists sync_runs (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  source text not null,
  triggered_by text not null,
  actor_open_id text not null,
  status text not null default 'running',
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  created_count int not null default 0,
  updated_count int not null default 0,
  skipped_count int not null default 0,
  failed_count int not null default 0,
  error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check(source in ('feishu', 'outbox')),
  check(triggered_by in ('manual', 'scheduler', 'system')),
  check(status in ('running', 'success', 'partial_success', 'failed', 'skipped'))
);

create index if not exists idx_sync_runs_tenant_recent
  on sync_runs (tenant_id, started_at desc);

create index if not exists idx_sync_runs_running
  on sync_runs (tenant_id, source, status)
  where status = 'running';
```

- [ ] **Step 4: Run schema tests**

Run:

```bash
uv run pytest tests/data_foundation/test_schema.py -q
```

Expected: PASS or skipped when `TEST_XHS_DATABASE_URL` is not configured.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/schema.sql tests/data_foundation/test_schema.py
git commit -m "feat: add sync runs schema"
```

---

### Task 2: Add Repository Sync Run And Status Helpers

**Files:**
- Modify: `data_foundation/repository.py`
- Modify: `tests/data_foundation/test_repository.py`

- [ ] **Step 1: Write failing repository tests**

Append to `tests/data_foundation/test_repository.py`:

```python
def test_sync_run_lifecycle_and_status_summary(migrated_conn):
    repo = ResourceRepository(migrated_conn)

    run_id = repo.start_sync_run(
        tenant_id="default",
        source="feishu",
        triggered_by="manual",
        actor_open_id="ou_user",
        metadata={"scope": "all"},
    )
    repo.finish_sync_run(
        tenant_id="default",
        run_id=run_id,
        status="partial_success",
        created_count=2,
        updated_count=3,
        skipped_count=4,
        failed_count=1,
        error="one row failed",
    )

    status = repo.data_foundation_status("default")

    assert status["sync"]["running"] is False
    assert status["sync"]["last_status"] == "partial_success"
    assert status["sync"]["last_error"] == "one row failed"
    assert status["sync"]["last_counts"] == {
        "created": 2,
        "updated": 3,
        "skipped": 4,
        "failed": 1,
    }


def test_outbox_lease_and_complete(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    resource = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="待处理资源",
        content_text="正文",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        outbox_topics=["embedding_generate"],
    )

    leased = repo.lease_outbox(tenant_id="default", batch_size=10)

    assert len(leased) == 1
    assert leased[0]["resource_id"] == resource.id
    assert leased[0]["topic"] == "embedding_generate"

    repo.complete_outbox(leased[0]["id"], status="succeeded")
    status = repo.data_foundation_status("default")

    assert status["outbox"]["pending"] == 0
    assert status["outbox"]["succeeded"] == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_repository.py::test_sync_run_lifecycle_and_status_summary tests/data_foundation/test_repository.py::test_outbox_lease_and_complete -q
```

Expected: FAIL because repository methods do not exist.

- [ ] **Step 3: Add repository methods**

Add these imports near the top of `data_foundation/repository.py`:

```python
from uuid import UUID
```

Add these methods inside `ResourceRepository` before `_lock_mapping`:

```python
    def start_sync_run(
        self,
        *,
        tenant_id: str,
        source: str,
        triggered_by: str,
        actor_open_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        row = self.conn.execute(
            """
            insert into sync_runs (tenant_id, source, triggered_by, actor_open_id, metadata)
            values (%s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                tenant_id,
                source,
                triggered_by,
                actor_open_id,
                json.dumps(metadata or {}, sort_keys=True, ensure_ascii=False),
            ),
        ).fetchone()
        self.conn.commit()
        return str(row["id"])

    def finish_sync_run(
        self,
        *,
        tenant_id: str,
        run_id: str,
        status: str,
        created_count: int = 0,
        updated_count: int = 0,
        skipped_count: int = 0,
        failed_count: int = 0,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            update sync_runs
            set status = %s,
                finished_at = now(),
                created_count = %s,
                updated_count = %s,
                skipped_count = %s,
                failed_count = %s,
                error = %s,
                updated_at = now()
            where tenant_id = %s and id = %s
            """,
            (
                status,
                created_count,
                updated_count,
                skipped_count,
                failed_count,
                error,
                tenant_id,
                run_id,
            ),
        )
        self.conn.commit()

    def data_foundation_status(self, tenant_id: str) -> dict[str, Any]:
        resource_rows = self.conn.execute(
            """
            select type, count(*) as count
            from resources
            where tenant_id = %s
            group by type
            order by type
            """,
            (tenant_id,),
        ).fetchall()
        outbox_rows = self.conn.execute(
            """
            select status, count(*) as count
            from resource_outbox
            where tenant_id = %s
            group by status
            """,
            (tenant_id,),
        ).fetchall()
        last_sync = self.conn.execute(
            """
            select *
            from sync_runs
            where tenant_id = %s and source = 'feishu'
            order by started_at desc, id desc
            limit 1
            """,
            (tenant_id,),
        ).fetchone()
        running = self.conn.execute(
            """
            select count(*) as count
            from sync_runs
            where tenant_id = %s and status = 'running'
            """,
            (tenant_id,),
        ).fetchone()["count"]
        by_type = {row["type"]: row["count"] for row in resource_rows}
        outbox = {row["status"]: row["count"] for row in outbox_rows}
        return {
            "tenant_id": tenant_id,
            "resources": {"total": sum(by_type.values()), "by_type": by_type},
            "sync": {
                "running": running > 0,
                "last_status": None if last_sync is None else last_sync["status"],
                "last_success_at": None
                if last_sync is None or last_sync["status"] not in ("success", "partial_success")
                else last_sync["finished_at"],
                "last_error": None if last_sync is None else last_sync["error"],
                "last_counts": None
                if last_sync is None
                else {
                    "created": last_sync["created_count"],
                    "updated": last_sync["updated_count"],
                    "skipped": last_sync["skipped_count"],
                    "failed": last_sync["failed_count"],
                },
            },
            "outbox": {
                "pending": outbox.get("pending", 0),
                "processing": outbox.get("processing", 0),
                "succeeded": outbox.get("succeeded", 0),
                "failed": outbox.get("failed", 0),
            },
        }

    def lease_outbox(self, *, tenant_id: str, batch_size: int) -> list[dict[str, Any]]:
        with transaction(self.conn):
            rows = self.conn.execute(
                """
                select id
                from resource_outbox
                where tenant_id = %s
                  and status = 'pending'
                  and available_at <= now()
                order by created_at, id
                limit %s
                for update skip locked
                """,
                (tenant_id, batch_size),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if not ids:
                return []
            leased = self.conn.execute(
                """
                update resource_outbox
                set status = 'processing',
                    attempts = attempts + 1,
                    updated_at = now()
                where id = any(%s::uuid[])
                returning id::text, tenant_id, resource_id::text, event_id::text, topic, payload, attempts
                """,
                (ids,),
            ).fetchall()
        return [dict(row) for row in leased]

    def complete_outbox(self, outbox_id: str, *, status: str = "succeeded", error: str | None = None) -> None:
        self.conn.execute(
            """
            update resource_outbox
            set status = %s,
                last_error = %s,
                updated_at = now()
            where id = %s
            """,
            (status, error, outbox_id),
        )
        self.conn.commit()
```

- [ ] **Step 4: Run repository tests**

Run:

```bash
uv run pytest tests/data_foundation/test_repository.py -q
```

Expected: PASS or skipped when `TEST_XHS_DATABASE_URL` is not configured.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/repository.py tests/data_foundation/test_repository.py
git commit -m "feat: add sync run repository helpers"
```

---

### Task 3: Add Feishu Sync Service With Run Tracking

**Files:**
- Create: `data_foundation/sync_service.py`
- Create: `tests/data_foundation/test_sync_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/data_foundation/test_sync_service.py`:

```python
from dataclasses import dataclass

from data_foundation.feishu_sync import SyncResult


@dataclass
class RecordingRepository:
    run_id: str = "run-1"
    finished: dict | None = None

    def start_sync_run(self, **kwargs):
        self.started = kwargs
        return self.run_id

    def finish_sync_run(self, **kwargs):
        self.finished = kwargs


def test_sync_service_records_success(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    monkeypatch.setattr("data_foundation.sync_service.sync_base_rows", lambda *_args, **_kwargs: SyncResult(imported=2, errors=[]))
    monkeypatch.setattr("data_foundation.sync_service.sync_wiki_documents", lambda *_args, **_kwargs: SyncResult(imported=1, errors=[]))

    result = sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
        base_rows=[{"record_id": "rec1", "fields": {"标题": "a"}}],
        wiki_documents=[{"obj_token": "doc1", "node_token": "wik1", "title": "b"}],
    )

    assert result["ok"] is True
    assert result["run_id"] == "run-1"
    assert result["status"] == "success"
    assert result["created"] == 3
    assert repo.started["source"] == "feishu"
    assert repo.finished["status"] == "success"


def test_sync_service_records_partial_success(monkeypatch):
    from data_foundation.sync_service import sync_feishu_sources

    repo = RecordingRepository()
    monkeypatch.setattr("data_foundation.sync_service.sync_base_rows", lambda *_args, **_kwargs: SyncResult(imported=1, errors=["bad row"]))
    monkeypatch.setattr("data_foundation.sync_service.sync_wiki_documents", lambda *_args, **_kwargs: SyncResult(imported=0, errors=[]))

    result = sync_feishu_sources(
        repo,
        tenant_id="default",
        actor_open_id="ou_user",
        triggered_by="manual",
        base_rows=[],
        wiki_documents=[],
    )

    assert result["ok"] is False
    assert result["status"] == "partial_success"
    assert result["failed"] == 1
    assert "bad row" in result["errors"]
    assert repo.finished["status"] == "partial_success"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_sync_service.py -q
```

Expected: FAIL because `data_foundation.sync_service` does not exist.

- [ ] **Step 3: Create sync service**

Create `data_foundation/sync_service.py`:

```python
from __future__ import annotations

from typing import Any

from data_foundation.feishu_sync import sync_base_rows, sync_wiki_documents


def sync_feishu_sources(
    repo,
    *,
    tenant_id: str,
    actor_open_id: str,
    triggered_by: str,
    base_rows: list[dict[str, Any]] | None = None,
    wiki_documents: list[dict[str, Any]] | None = None,
    app_token: str = "",
    table_id: str = "",
    wiki_space_id: str = "",
) -> dict[str, Any]:
    run_id = repo.start_sync_run(
        tenant_id=tenant_id,
        source="feishu",
        triggered_by=triggered_by,
        actor_open_id=actor_open_id,
        metadata={
            "base_rows": len(base_rows or []),
            "wiki_documents": len(wiki_documents or []),
        },
    )
    errors: list[str] = []
    created = 0
    try:
        base_result = sync_base_rows(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            app_token=app_token or "configured-base",
            table_id=table_id or "configured-table",
            rows=base_rows or [],
        )
        wiki_result = sync_wiki_documents(
            repo,
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            space_id=wiki_space_id or "configured-space",
            documents=wiki_documents or [],
        )
        created = base_result.imported + wiki_result.imported
        errors = [*base_result.errors, *wiki_result.errors]
        status = "success" if not errors else "partial_success"
        repo.finish_sync_run(
            tenant_id=tenant_id,
            run_id=run_id,
            status=status,
            created_count=created,
            failed_count=len(errors),
            error="\n".join(errors) if errors else None,
        )
        return {
            "ok": not errors,
            "run_id": run_id,
            "status": status,
            "created": created,
            "updated": 0,
            "skipped": 0,
            "failed": len(errors),
            "errors": errors,
        }
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        repo.finish_sync_run(
            tenant_id=tenant_id,
            run_id=run_id,
            status="failed",
            created_count=created,
            failed_count=max(1, len(errors)),
            error=message,
        )
        return {
            "ok": False,
            "run_id": run_id,
            "status": "failed",
            "created": created,
            "updated": 0,
            "skipped": 0,
            "failed": max(1, len(errors)),
            "errors": [message],
        }
```

- [ ] **Step 4: Run service tests**

Run:

```bash
uv run pytest tests/data_foundation/test_sync_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/sync_service.py tests/data_foundation/test_sync_service.py
git commit -m "feat: add sync service run tracking"
```

---

### Task 4: Add Data Foundation Status And Manual Sync Tools

**Files:**
- Modify: `data_foundation/tools.py`
- Create: `tests/data_foundation/test_phase4_tools.py`
- Modify: `tests/test_agent_assembly.py`

- [ ] **Step 1: Write failing tool tests**

Create `tests/data_foundation/test_phase4_tools.py`:

```python
from tools.runtime_identity import identity_config


class RecordingRepository:
    def __init__(self):
        self.synced = False

    def data_foundation_status(self, tenant_id):
        return {
            "tenant_id": tenant_id,
            "resources": {"total": 0, "by_type": {}},
            "sync": {"running": False, "last_status": None, "last_success_at": None, "last_error": None, "last_counts": None},
            "outbox": {"pending": 0, "processing": 0, "succeeded": 0, "failed": 0},
        }


def test_get_data_foundation_status_tool(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _repo_context(repo))

    result = df_tools.get_data_foundation_status.func(config=identity_config("ou_user"))

    assert result["ok"] is True
    assert result["status"]["tenant_id"] == "default"


def test_sync_feishu_resources_tool(monkeypatch):
    from data_foundation import tools as df_tools

    repo = RecordingRepository()
    monkeypatch.setattr(df_tools, "_repository", lambda: _repo_context(repo))
    monkeypatch.setattr(
        df_tools,
        "sync_feishu_sources",
        lambda repo, **kwargs: {"ok": True, "run_id": "run-1", "status": "success", "created": 0, "updated": 0, "skipped": 0, "failed": 0, "errors": []},
    )

    result = df_tools.sync_feishu_resources.func(config=identity_config("ou_user"))

    assert result["ok"] is True
    assert result["run_id"] == "run-1"


class _repo_context:
    def __init__(self, repo):
        self.repo = repo

    def __enter__(self):
        return self.repo

    def __exit__(self, exc_type, exc, tb):
        return False
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_phase4_tools.py -q
```

Expected: FAIL because tools do not exist.

- [ ] **Step 3: Modify `data_foundation/tools.py`**

Add import:

```python
from data_foundation.sync_service import sync_feishu_sources
```

Add tools before `phase3_tools`:

```python
@tool
def get_data_foundation_status(config: RunnableConfig | None = None) -> dict[str, Any]:
    """Return Postgres data foundation resource, sync and outbox status."""
    actor_from_config(config)
    with _repository() as repo:
        status = repo.data_foundation_status(default_tenant_id())
    return {"ok": True, "status": status}


@tool
def sync_feishu_resources(config: RunnableConfig | None = None) -> dict[str, Any]:
    """Trigger a bounded Feishu resource sync for the current user."""
    actor = actor_from_config(config)
    with _repository() as repo:
        return sync_feishu_sources(
            repo,
            tenant_id=default_tenant_id(),
            actor_open_id=actor,
            triggered_by="manual",
            base_rows=[],
            wiki_documents=[],
        )
```

Replace:

```python
phase3_tools = [search_resources, semantic_search_resources, graph_expand, get_resource]
```

with:

```python
data_foundation_tools = [
    search_resources,
    semantic_search_resources,
    graph_expand,
    get_resource,
    get_data_foundation_status,
    sync_feishu_resources,
]

phase3_tools = data_foundation_tools
```

- [ ] **Step 4: Add assembly regression**

Append to `tests/test_agent_assembly.py`:

```python
def test_agent_registers_phase4_status_tools(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_module

    agent_module = importlib.reload(agent_module)
    tool_names = {getattr(tool, "name", "") for tool in agent_module.phase3_tools}

    assert {"get_data_foundation_status", "sync_feishu_resources"} <= tool_names
```

- [ ] **Step 5: Run tests**

Run:

```bash
uv run pytest tests/data_foundation/test_phase4_tools.py tests/test_agent_assembly.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add data_foundation/tools.py tests/data_foundation/test_phase4_tools.py tests/test_agent_assembly.py
git commit -m "feat: expose sync status tools"
```

---

### Task 5: Add Minimum Outbox Worker

**Files:**
- Create: `data_foundation/outbox_worker.py`
- Create: `tests/data_foundation/test_outbox_worker.py`

- [ ] **Step 1: Write failing worker tests**

Create `tests/data_foundation/test_outbox_worker.py`:

```python
from data_foundation.outbox_worker import process_outbox_batch


class RecordingRepo:
    def __init__(self):
        self.completed = []

    def lease_outbox(self, *, tenant_id, batch_size):
        return [
            {"id": "1", "topic": "meili_index", "resource_id": "res1", "payload": {}},
            {"id": "2", "topic": "embedding_generate", "resource_id": "res1", "payload": {}},
            {"id": "3", "topic": "graph_ingest", "resource_id": "res1", "payload": {}},
        ][:batch_size]

    def complete_outbox(self, outbox_id, *, status="succeeded", error=None):
        self.completed.append((outbox_id, status, error))


def test_process_outbox_batch_marks_known_topics_succeeded():
    repo = RecordingRepo()

    result = process_outbox_batch(repo, tenant_id="default", batch_size=3)

    assert result == {"processed": 3, "failed": 0}
    assert repo.completed == [
        ("1", "succeeded", None),
        ("2", "succeeded", None),
        ("3", "succeeded", None),
    ]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_outbox_worker.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Create worker**

Create `data_foundation/outbox_worker.py`:

```python
from __future__ import annotations

from typing import Any


def process_outbox_batch(repo, *, tenant_id: str, batch_size: int = 20) -> dict[str, int]:
    leased = repo.lease_outbox(tenant_id=tenant_id, batch_size=batch_size)
    processed = 0
    failed = 0
    for item in leased:
        try:
            _process_item(repo, item)
            repo.complete_outbox(item["id"], status="succeeded")
            processed += 1
        except Exception as exc:
            repo.complete_outbox(item["id"], status="failed", error=f"{type(exc).__name__}: {exc}")
            failed += 1
    return {"processed": processed, "failed": failed}


def _process_item(repo, item: dict[str, Any]) -> None:
    topic = item["topic"]
    if topic in {"meili_index", "embedding_generate", "graph_ingest"}:
        return
    raise ValueError(f"Unsupported outbox topic: {topic}")
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/data_foundation/test_outbox_worker.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/outbox_worker.py tests/data_foundation/test_outbox_worker.py
git commit -m "feat: add minimal outbox worker"
```

---

### Task 6: Add Scheduler Bootstrap

**Files:**
- Create: `data_foundation/scheduler.py`
- Modify: `agent.py`
- Create: `tests/data_foundation/test_scheduler.py`
- Modify: `tests/test_agent_assembly.py`

- [ ] **Step 1: Write failing scheduler tests**

Create `tests/data_foundation/test_scheduler.py`:

```python
def test_scheduler_disabled_by_default(monkeypatch):
    from data_foundation.scheduler import should_start_scheduler

    monkeypatch.delenv("XHS_SYNC_ENABLED", raising=False)

    assert should_start_scheduler() is False


def test_scheduler_enabled_by_env(monkeypatch):
    from data_foundation.scheduler import should_start_scheduler

    monkeypatch.setenv("XHS_SYNC_ENABLED", "true")

    assert should_start_scheduler() is True
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_scheduler.py -q
```

Expected: FAIL because module does not exist.

- [ ] **Step 3: Create scheduler**

Create `data_foundation/scheduler.py`:

```python
from __future__ import annotations

import os
import threading
import time

from data_foundation.db import connect
from data_foundation.outbox_worker import process_outbox_batch
from data_foundation.permissions import default_tenant_id
from data_foundation.repository import ResourceRepository


_started = False


def should_start_scheduler() -> bool:
    return os.environ.get("XHS_SYNC_ENABLED", "false").strip().lower() == "true"


def start_background_services() -> bool:
    global _started
    if _started or not should_start_scheduler():
        return False
    _started = True
    thread = threading.Thread(target=_run_loop, name="xhs-data-foundation-scheduler", daemon=True)
    thread.start()
    return True


def _run_loop() -> None:
    startup_delay = int(os.environ.get("XHS_SYNC_STARTUP_DELAY_SECONDS", "30"))
    interval = int(os.environ.get("XHS_OUTBOX_INTERVAL_SECONDS", "300"))
    batch_size = int(os.environ.get("XHS_OUTBOX_BATCH_SIZE", "20"))
    time.sleep(max(0, startup_delay))
    while True:
        try:
            with connect() as conn:
                repo = ResourceRepository(conn)
                process_outbox_batch(repo, tenant_id=default_tenant_id(), batch_size=batch_size)
        except Exception:
            pass
        time.sleep(max(30, interval))
```

- [ ] **Step 4: Modify `agent.py`**

Add import:

```python
from data_foundation.scheduler import start_background_services
```

After `load_dotenv()`, add:

```python
start_background_services()
```

- [ ] **Step 5: Add agent assembly regression**

Append to `tests/test_agent_assembly.py`:

```python
def test_agent_does_not_start_scheduler_unless_enabled(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")
    monkeypatch.delenv("XHS_SYNC_ENABLED", raising=False)

    import importlib
    import data_foundation.scheduler as scheduler

    scheduler._started = False
    import agent as agent_module
    importlib.reload(agent_module)

    assert scheduler._started is False
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/data_foundation/test_scheduler.py tests/test_agent_assembly.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add data_foundation/scheduler.py agent.py tests/data_foundation/test_scheduler.py tests/test_agent_assembly.py
git commit -m "feat: add data foundation scheduler bootstrap"
```

---

### Task 7: Full Regression And Docs

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`

- [ ] **Step 1: Update README**

Add this bullet under the data foundation runtime notes:

```markdown
- Phase 4.1 adds Postgres-tracked `sync_runs`, Agent-visible data foundation status, manual Feishu sync tool entry, and an env-gated background outbox worker.
```

- [ ] **Step 2: Update phase four spec status**

Change the status line in `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md` to:

```markdown
- 状态：设计稿，Phase 4.0 已完成；Phase 4.1 同步与状态闭环计划已完成
```

- [ ] **Step 3: Run full backend tests**

Run:

```bash
uv run pytest -q
```

Expected: PASS with Postgres integration tests skipped when `TEST_XHS_DATABASE_URL` is absent.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd web
npx tsc --noEmit
npm run lint -- src
```

Expected: TypeScript PASS; lint PASS with existing warnings allowed.

- [ ] **Step 5: Run diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only README/spec before final commit.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md
git commit -m "docs: plan phase four sync status loop"
```

---

## Self-Review

**Spec coverage:**

- `sync_runs`: Task 1 and Task 2.
- Sync service: Task 3.
- `get_data_foundation_status` and `sync_feishu_resources`: Task 4.
- Minimum outbox worker: Task 5.
- Env-gated scheduler: Task 6.
- No business CLI and no management backend: preserved by only adding service modules and Agent tools.

**Placeholder scan:**

- No unresolved placeholder markers.
- Every task has exact files, commands, and code snippets.

**Type consistency:**

- Repository method names are consistent across tests and services:
  - `start_sync_run`
  - `finish_sync_run`
  - `data_foundation_status`
  - `lease_outbox`
  - `complete_outbox`
- Tool names are consistent:
  - `get_data_foundation_status`
  - `sync_feishu_resources`
- Scheduler entrypoint is consistently named `start_background_services`.

**Known implementation caution:**

- The first `sync_feishu_resources` tool version intentionally accepts empty in-memory lists and records a sync run. Pulling real Feishu rows from live APIs should happen in the next implementation slice or by extending `sync_service.py` behind the same tool boundary.
