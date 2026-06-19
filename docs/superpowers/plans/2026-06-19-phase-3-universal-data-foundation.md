# Phase 3 Universal Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Implementation Status

Completed on 2026-06-19.

- Postgres schema and migrations are in `data_foundation/schema.sql`.
- Repository writes resources, versions, events, mappings, outbox rows, permissions, embeddings, and edges.
- Feishu Base/Wiki/Doc ingestion writes through the shared data access layer.
- Keyword search, pgvector interface, and graph expansion are available through DeepAgents-native LangChain tools.
- Postgres is the authoritative universal data foundation; Feishu and future database-backed sources are ingestion adapters into the same resource model.
- Meilisearch, Graphiti, Neo4j/FalkorDB, and Dagster remain outbox-backed future adapters.

**Goal:** Build the first working Phase 3 loop: Postgres authoritative resource storage, Feishu ingestion, Postgres keyword/vector retrieval, graph expansion, and DeepAgents-native tools.

**Architecture:** Keep DeepAgents/LangGraph as the only agent runtime and keep Web conversation as the product entrypoint. Add a focused Python `data_foundation` package that owns schema migrations, repository access, permissions, Feishu ingestion, retrieval, graph expansion, and LangChain tool wrappers. Agents never receive SQL/Cypher access; they call DeepAgents tools that resolve actor identity from `RunnableConfig.server_info.user.identity`.

**Tech Stack:** Python 3.12, pytest, psycopg 3, Postgres, pgcrypto, pgvector, LangChain tools, DeepAgents/LangGraph, existing Feishu `lark-cli` adapter.

---

## Implementation Boundary

This plan implements Phase 3.1 through Phase 3.4 only.

- Included: Postgres schema/DAL, `resource_outbox`, Feishu Base/Wiki/Doc ingestion into Postgres, Postgres full-text search, pgvector query interface, `resource_edges`, `graph_expand`, and DeepAgents tools.
- Interface-only in this plan: Meilisearch, Graphiti, Neo4j/FalkorDB, Dagster. They appear as outbox topics and adapter boundaries, not runtime dependencies.
- Explicitly excluded: project-owned CLI runtime entrypoint, free-form Agent SQL/Cypher, replacing/forking DeepAgents, full organization-grade governance.

## Required Local Environment

Use a real Postgres test database. SQLite is not a valid Phase 3 path.

```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/xhs_test"
$env:XHS_DATABASE_URL=$env:TEST_XHS_DATABASE_URL
```

The database must allow:

```sql
create extension if not exists pgcrypto;
create extension if not exists vector;
```

## File Map

- Create `data_foundation/__init__.py`: package exports.
- Create `data_foundation/schema.sql`: authoritative initial schema, extensions, indexes, and constraints.
- Create `data_foundation/db.py`: database URL loading, psycopg connection helper, explicit migration runner, transaction helper.
- Create `data_foundation/models.py`: dataclasses for resources, mappings, events, outbox, search results, and graph results.
- Create `data_foundation/repository.py`: resource upsert, versioning, events, mappings, outbox, permissions, embeddings, and edges.
- Create `data_foundation/permissions.py`: actor/tenant resolution and SQL permission filter fragments.
- Create `data_foundation/search.py`: keyword search, vector search, RRF fusion boundary, and result shaping.
- Create `data_foundation/graph.py`: recursive CTE graph expansion with permission filtering.
- Create `data_foundation/feishu_sync.py`: Feishu Base/Wiki/Doc ingestion adapters that call existing Feishu tools/bridge behavior without becoming a runtime entrypoint.
- Create `data_foundation/tools.py`: DeepAgents/LangChain tools wrapping the DAL.
- Create `tests/data_foundation/conftest.py`: Postgres test fixture that migrates a clean schema.
- Create `tests/data_foundation/test_schema.py`: migration and extension tests.
- Create `tests/data_foundation/test_repository.py`: resource, version, mapping, event, outbox, and permission tests.
- Create `tests/data_foundation/test_feishu_sync.py`: mocked Feishu ingestion tests.
- Create `tests/data_foundation/test_search_graph_tools.py`: search, pgvector interface, graph expansion, and tool identity tests.
- Modify `pyproject.toml`: add `psycopg[binary]`.
- Modify `.env.example`: document `XHS_DATABASE_URL`, `XHS_DEFAULT_TENANT_ID`, and `TEST_XHS_DATABASE_URL`.
- Modify `README.md`: document Phase 3 data foundation setup and test commands.
- Modify `agent.py`: append Phase 3 DeepAgents tools to the existing tool list without changing runtime assembly.

## Task 1: Postgres Dependency And Schema

**Files:**
- Modify: `pyproject.toml`
- Create: `data_foundation/__init__.py`
- Create: `data_foundation/schema.sql`
- Create: `data_foundation/db.py`
- Create: `tests/data_foundation/conftest.py`
- Create: `tests/data_foundation/test_schema.py`

- [x] **Step 1: Add failing schema tests**

Create `tests/data_foundation/conftest.py`:

```python
from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from data_foundation.db import run_migrations


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_XHS_DATABASE_URL")
    if not url:
        pytest.skip("TEST_XHS_DATABASE_URL is required for Phase 3 Postgres tests")
    return url


@pytest.fixture()
def migrated_conn(database_url: str):
    schema = f"test_{uuid.uuid4().hex}"
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(f'create schema "{schema}"')
    try:
        with psycopg.connect(database_url) as conn:
            conn.execute(f'set search_path to "{schema}", public')
            run_migrations(conn)
            yield conn
            conn.rollback()
    finally:
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(f'drop schema if exists "{schema}" cascade')
```

Create `tests/data_foundation/test_schema.py`:

```python
def test_schema_enables_required_extensions(migrated_conn):
    rows = migrated_conn.execute(
        "select extname from pg_extension where extname in ('pgcrypto', 'vector')"
    ).fetchall()
    assert {row[0] for row in rows} == {"pgcrypto", "vector"}


def test_schema_creates_core_tables(migrated_conn):
    rows = migrated_conn.execute(
        """
        select table_name
        from information_schema.tables
        where table_schema = current_schema()
        order by table_name
        """
    ).fetchall()
    assert [row[0] for row in rows] == [
        "resource_edges",
        "resource_embeddings",
        "resource_events",
        "resource_mappings",
        "resource_outbox",
        "resource_permissions",
        "resource_versions",
        "resources",
    ]


def test_schema_is_idempotent(migrated_conn):
    from data_foundation.db import run_migrations

    run_migrations(migrated_conn)
    count = migrated_conn.execute(
        "select count(*) from information_schema.tables where table_schema = current_schema()"
    ).fetchone()[0]
    assert count == 8
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```powershell
uv run pytest tests/data_foundation/test_schema.py -q
```

Expected before implementation: FAIL because `psycopg` or `data_foundation.db` is missing.

- [x] **Step 3: Add psycopg dependency**

In `pyproject.toml`, add this dependency in `[project].dependencies`:

```toml
    "psycopg[binary]>=3.2.0,<4.0.0",
```

Run:

```powershell
uv sync
```

- [x] **Step 4: Create package and schema**

Create `data_foundation/__init__.py`:

```python
"""Postgres-backed universal data foundation for the DeepAgents app."""
```

Create `data_foundation/schema.sql`:

```sql
create extension if not exists pgcrypto;
create extension if not exists vector;

create table if not exists resources (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  type text not null,
  title text not null,
  summary text,
  content_text text,
  content_json jsonb not null default '{}'::jsonb,
  status text not null default 'active',
  visibility text not null default 'private',
  owner_open_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_resources_tenant_type on resources (tenant_id, type);
create index if not exists idx_resources_owner on resources (tenant_id, owner_open_id);
create index if not exists idx_resources_fts on resources using gin (
  to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(summary, '') || ' ' || coalesce(content_text, ''))
);

create table if not exists resource_mappings (
  id uuid primary key default gen_random_uuid(),
  resource_id uuid not null references resources(id) on delete cascade,
  system text not null,
  external_type text not null,
  external_id text not null,
  external_url text,
  external_updated_at timestamptz,
  sync_cursor text,
  sync_status text not null default 'pending',
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(system, external_type, external_id)
);

create table if not exists resource_versions (
  id uuid primary key default gen_random_uuid(),
  resource_id uuid not null references resources(id) on delete cascade,
  version int not null,
  content_hash text not null,
  content_text text,
  content_json jsonb not null default '{}'::jsonb,
  changed_by text,
  change_summary text,
  created_at timestamptz not null default now(),
  unique(resource_id, version)
);

create table if not exists resource_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid references resources(id) on delete set null,
  event_type text not null,
  actor_open_id text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists resource_edges (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  source_resource_id uuid not null references resources(id) on delete cascade,
  target_resource_id uuid not null references resources(id) on delete cascade,
  edge_type text not null,
  weight double precision not null default 1.0,
  properties jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(source_resource_id, target_resource_id, edge_type)
);

create table if not exists resource_permissions (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid not null references resources(id) on delete cascade,
  subject_type text not null,
  subject_id text not null,
  permission text not null,
  created_at timestamptz not null default now(),
  unique(resource_id, subject_type, subject_id, permission)
);

create table if not exists resource_embeddings (
  id uuid primary key default gen_random_uuid(),
  resource_id uuid not null references resources(id) on delete cascade,
  chunk_index int not null,
  chunk_text text not null,
  embedding vector(1536),
  embedding_model text not null,
  created_at timestamptz not null default now(),
  unique(resource_id, chunk_index, embedding_model)
);

create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create table if not exists resource_outbox (
  id uuid primary key default gen_random_uuid(),
  tenant_id text not null,
  resource_id uuid references resources(id) on delete cascade,
  event_id uuid references resource_events(id) on delete set null,
  topic text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending',
  attempts int not null default 0,
  last_error text,
  available_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check(status in ('pending', 'processing', 'succeeded', 'failed')),
  check(topic in ('meili_index', 'embedding_generate', 'graph_ingest', 'feishu_writeback'))
);

create index if not exists idx_resource_outbox_ready
  on resource_outbox (status, available_at, topic);
```

- [x] **Step 5: Implement migration runner**

Create `data_foundation/db.py`:

```python
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def database_url() -> str:
    url = os.environ.get("XHS_DATABASE_URL")
    if not url:
        raise RuntimeError("XHS_DATABASE_URL is required for Phase 3 data foundation")
    return url


def connect(url: str | None = None) -> Connection:
    return psycopg.connect(url or database_url(), row_factory=dict_row)


def run_migrations(conn: Connection) -> None:
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    with conn.transaction():
        yield conn
```

- [x] **Step 6: Run schema tests**

Run:

```powershell
uv run pytest tests/data_foundation/test_schema.py -q
```

Expected: PASS when `TEST_XHS_DATABASE_URL` points to a Postgres database with permission to create extensions.

- [x] **Step 7: Commit**

```powershell
git add pyproject.toml uv.lock data_foundation tests/data_foundation
git commit -m "feat: add phase three postgres schema"
```

## Task 2: Repository, Versions, Events, Outbox, Permissions

**Files:**
- Create: `data_foundation/models.py`
- Create: `data_foundation/permissions.py`
- Create: `data_foundation/repository.py`
- Create: `tests/data_foundation/test_repository.py`

- [x] **Step 1: Write failing repository tests**

Create `tests/data_foundation/test_repository.py`:

```python
from data_foundation.repository import ResourceRepository


def test_upsert_resource_writes_version_event_mapping_and_outbox(migrated_conn):
    repo = ResourceRepository(migrated_conn)

    resource = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_base_record",
        title="露营装备清单",
        content_text="帐篷 天幕 炉具",
        content_json={"fields": {"点赞": 120}},
        visibility="private",
        owner_open_id="ou_owner",
        mapping={
            "system": "feishu",
            "external_type": "base_record",
            "external_id": "base:table:rec1",
        },
        outbox_topics=["meili_index", "embedding_generate", "graph_ingest"],
    )

    assert resource.id
    assert resource.version == 1
    assert repo.get_resource("default", "ou_owner", resource.id).title == "露营装备清单"

    counts = repo.debug_counts()
    assert counts["resource_versions"] == 1
    assert counts["resource_events"] == 1
    assert counts["resource_mappings"] == 1
    assert counts["resource_outbox"] == 3


def test_upsert_same_mapping_creates_second_version(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="旧标题",
        content_text="旧内容",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "feishu", "external_type": "docx", "external_id": "doc1"},
        outbox_topics=["meili_index"],
    )
    second = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="feishu_doc",
        title="新标题",
        content_text="新内容",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
        mapping={"system": "feishu", "external_type": "docx", "external_id": "doc1"},
        outbox_topics=["meili_index"],
    )

    assert second.id == first.id
    assert second.version == 2
    assert repo.debug_counts()["resource_versions"] == 2


def test_permission_filter_blocks_other_private_resource(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    created = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="draft",
        title="私有草稿",
        content_text="只有 owner 可读",
        content_json={},
        visibility="private",
        owner_open_id="ou_owner",
    )

    assert repo.get_resource("default", "ou_owner", created.id) is not None
    assert repo.get_resource("default", "ou_other", created.id) is None

    repo.grant_permission(
        tenant_id="default",
        resource_id=created.id,
        subject_type="user",
        subject_id="ou_other",
        permission="read",
    )
    assert repo.get_resource("default", "ou_other", created.id) is not None
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```powershell
uv run pytest tests/data_foundation/test_repository.py -q
```

Expected before implementation: FAIL because `ResourceRepository` is missing.

- [x] **Step 3: Create model dataclasses**

Create `data_foundation/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Resource:
    id: str
    tenant_id: str
    type: str
    title: str
    summary: str | None
    content_text: str | None
    content_json: dict[str, Any]
    status: str
    visibility: str
    owner_open_id: str | None
    created_at: datetime
    updated_at: datetime
    version: int | None = None


@dataclass(frozen=True)
class ResourceSearchResult:
    resource_id: str
    title: str
    summary: str | None
    score: float
    metadata: dict[str, Any]


@dataclass(frozen=True)
class GraphNode:
    resource_id: str
    title: str
    type: str
    depth: int


@dataclass(frozen=True)
class GraphEdge:
    source_resource_id: str
    target_resource_id: str
    edge_type: str
    weight: float


@dataclass(frozen=True)
class GraphExpansion:
    nodes: list[GraphNode]
    edges: list[GraphEdge]
```

- [x] **Step 4: Create permission SQL helper**

Create `data_foundation/permissions.py`:

```python
from __future__ import annotations

import os
from typing import Any


def default_tenant_id() -> str:
    return os.environ.get("XHS_DEFAULT_TENANT_ID", "default")


def actor_from_config(config: Any) -> str:
    identity = getattr(getattr(getattr(config, "server_info", None), "user", None), "identity", None)
    if not identity:
        raise PermissionError("Missing LangGraph user identity")
    return str(identity)


def readable_resource_where(alias: str = "r") -> str:
    return f"""
    {alias}.tenant_id = %(tenant_id)s
    and (
      {alias}.owner_open_id = %(actor_open_id)s
      or {alias}.visibility = 'team'
      or exists (
        select 1 from resource_permissions rp
        where rp.resource_id = {alias}.id
          and rp.tenant_id = {alias}.tenant_id
          and rp.subject_type = 'user'
          and rp.subject_id = %(actor_open_id)s
          and rp.permission in ('read', 'write', 'admin')
      )
      or exists (
        select 1 from resource_permissions rp
        where rp.resource_id = {alias}.id
          and rp.tenant_id = {alias}.tenant_id
          and rp.subject_type = 'role'
          and rp.subject_id = 'admin'
          and rp.permission = 'admin'
          and %(actor_open_id)s = any(string_to_array(coalesce(current_setting('app.admin_open_ids', true), ''), ','))
      )
    )
    """
```

- [x] **Step 5: Implement repository**

Create `data_foundation/repository.py` with the exact public methods used by tests:

```python
from __future__ import annotations

import hashlib
import json
from typing import Any

from psycopg import Connection

from data_foundation.models import Resource
from data_foundation.permissions import readable_resource_where


def _hash_content(content_text: str | None, content_json: dict[str, Any]) -> str:
    payload = json.dumps({"text": content_text or "", "json": content_json}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _resource_from_row(row: dict[str, Any], version: int | None = None) -> Resource:
    return Resource(
        id=str(row["id"]),
        tenant_id=row["tenant_id"],
        type=row["type"],
        title=row["title"],
        summary=row["summary"],
        content_text=row["content_text"],
        content_json=row["content_json"],
        status=row["status"],
        visibility=row["visibility"],
        owner_open_id=row["owner_open_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        version=version,
    )


class ResourceRepository:
    def __init__(self, conn: Connection) -> None:
        self.conn = conn

    def upsert_resource(
        self,
        *,
        tenant_id: str,
        actor_open_id: str,
        resource_type: str,
        title: str,
        content_text: str | None,
        content_json: dict[str, Any],
        visibility: str,
        owner_open_id: str | None,
        mapping: dict[str, str] | None = None,
        outbox_topics: list[str] | None = None,
    ) -> Resource:
        with self.conn.transaction():
            resource_id = None
            if mapping:
                mapped = self.conn.execute(
                    """
                    select resource_id from resource_mappings
                    where system = %(system)s and external_type = %(external_type)s and external_id = %(external_id)s
                    """,
                    mapping,
                ).fetchone()
                if mapped:
                    resource_id = mapped["resource_id"]

            if resource_id:
                row = self.conn.execute(
                    """
                    update resources
                    set title=%s, content_text=%s, content_json=%s::jsonb, visibility=%s, owner_open_id=%s, updated_at=now()
                    where id=%s
                    returning *
                    """,
                    (title, content_text, json.dumps(content_json), visibility, owner_open_id, resource_id),
                ).fetchone()
            else:
                row = self.conn.execute(
                    """
                    insert into resources (tenant_id, type, title, content_text, content_json, visibility, owner_open_id)
                    values (%s, %s, %s, %s, %s::jsonb, %s, %s)
                    returning *
                    """,
                    (tenant_id, resource_type, title, content_text, json.dumps(content_json), visibility, owner_open_id),
                ).fetchone()
                resource_id = row["id"]

            version = self.conn.execute(
                "select coalesce(max(version), 0) + 1 as next_version from resource_versions where resource_id=%s",
                (resource_id,),
            ).fetchone()["next_version"]
            self.conn.execute(
                """
                insert into resource_versions (resource_id, version, content_hash, content_text, content_json, changed_by)
                values (%s, %s, %s, %s, %s::jsonb, %s)
                """,
                (resource_id, version, _hash_content(content_text, content_json), content_text, json.dumps(content_json), actor_open_id),
            )

            event = self.conn.execute(
                """
                insert into resource_events (tenant_id, resource_id, event_type, actor_open_id, payload)
                values (%s, %s, %s, %s, %s::jsonb)
                returning id
                """,
                (tenant_id, resource_id, "updated" if version > 1 else "imported", actor_open_id, json.dumps({"version": version})),
            ).fetchone()

            if mapping:
                self.conn.execute(
                    """
                    insert into resource_mappings (resource_id, system, external_type, external_id, sync_status)
                    values (%(resource_id)s, %(system)s, %(external_type)s, %(external_id)s, 'synced')
                    on conflict(system, external_type, external_id)
                    do update set resource_id=excluded.resource_id, sync_status='synced', updated_at=now()
                    """,
                    {**mapping, "resource_id": resource_id},
                )

            for topic in outbox_topics or []:
                self.conn.execute(
                    """
                    insert into resource_outbox (tenant_id, resource_id, event_id, topic, payload)
                    values (%s, %s, %s, %s, %s::jsonb)
                    """,
                    (tenant_id, resource_id, event["id"], topic, json.dumps({"resource_id": str(resource_id), "version": version})),
                )

        return _resource_from_row(row, version=version)

    def get_resource(self, tenant_id: str, actor_open_id: str, resource_id: str) -> Resource | None:
        row = self.conn.execute(
            f"select * from resources r where r.id=%(resource_id)s and {readable_resource_where('r')}",
            {"resource_id": resource_id, "tenant_id": tenant_id, "actor_open_id": actor_open_id},
        ).fetchone()
        return _resource_from_row(row) if row else None

    def grant_permission(self, *, tenant_id: str, resource_id: str, subject_type: str, subject_id: str, permission: str) -> None:
        self.conn.execute(
            """
            insert into resource_permissions (tenant_id, resource_id, subject_type, subject_id, permission)
            values (%s, %s, %s, %s, %s)
            on conflict do nothing
            """,
            (tenant_id, resource_id, subject_type, subject_id, permission),
        )
        self.conn.commit()

    def debug_counts(self) -> dict[str, int]:
        names = ["resources", "resource_versions", "resource_events", "resource_mappings", "resource_outbox"]
        return {name: self.conn.execute(f"select count(*) as c from {name}").fetchone()["c"] for name in names}
```

- [x] **Step 6: Run repository tests**

Run:

```powershell
uv run pytest tests/data_foundation/test_repository.py -q
```

Expected: PASS.

- [x] **Step 7: Commit**

```powershell
git add data_foundation tests/data_foundation
git commit -m "feat: add resource repository and permissions"
```

## Task 3: Feishu Ingestion Into Postgres

**Files:**
- Create: `data_foundation/feishu_sync.py`
- Create: `tests/data_foundation/test_feishu_sync.py`

- [x] **Step 1: Write failing sync tests**

Create `tests/data_foundation/test_feishu_sync.py`:

```python
from data_foundation.feishu_sync import sync_base_rows, sync_wiki_documents
from data_foundation.repository import ResourceRepository


def test_sync_base_rows_upserts_records(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    result = sync_base_rows(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        app_token="base1",
        table_id="tbl1",
        rows=[
            {"record_id": "rec1", "fields": {"标题": "露营标题", "正文": "露营正文", "点赞": 88}},
            {"record_id": "rec2", "fields": {"标题": "收纳标题", "正文": "收纳正文"}},
        ],
    )

    assert result.imported == 2
    assert repo.debug_counts()["resources"] == 2
    assert repo.debug_counts()["resource_mappings"] == 2


def test_sync_wiki_documents_upserts_docs_and_chunks(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    result = sync_wiki_documents(
        repo,
        tenant_id="default",
        actor_open_id="ou_sync",
        space_id="sp1",
        documents=[
            {"obj_token": "doc1", "title": "选题方法", "content": "第一段\n\n第二段"},
        ],
    )

    assert result.imported == 1
    resource = repo.search_debug_by_title("default", "ou_sync", "选题方法")
    assert resource is not None
    rows = migrated_conn.execute("select chunk_text from resource_embeddings order by chunk_index").fetchall()
    assert [row["chunk_text"] for row in rows] == ["第一段", "第二段"]
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```powershell
uv run pytest tests/data_foundation/test_feishu_sync.py -q
```

Expected before implementation: FAIL because `data_foundation.feishu_sync` is missing.

- [x] **Step 3: Add repository helper methods**

Append these methods inside `ResourceRepository`:

```python
    def add_embedding_chunk(self, *, resource_id: str, chunk_index: int, chunk_text: str, embedding_model: str = "pending") -> None:
        self.conn.execute(
            """
            insert into resource_embeddings (resource_id, chunk_index, chunk_text, embedding_model)
            values (%s, %s, %s, %s)
            on conflict(resource_id, chunk_index, embedding_model)
            do update set chunk_text=excluded.chunk_text
            """,
            (resource_id, chunk_index, chunk_text, embedding_model),
        )
        self.conn.commit()

    def search_debug_by_title(self, tenant_id: str, actor_open_id: str, title: str):
        row = self.conn.execute(
            f"select * from resources r where r.title=%(title)s and {readable_resource_where('r')}",
            {"title": title, "tenant_id": tenant_id, "actor_open_id": actor_open_id},
        ).fetchone()
        return _resource_from_row(row) if row else None
```

- [x] **Step 4: Implement Feishu sync adapters**

Create `data_foundation/feishu_sync.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from data_foundation.repository import ResourceRepository


@dataclass(frozen=True)
class SyncResult:
    imported: int
    errors: list[str]


def _field(fields: dict[str, Any], names: list[str]) -> str:
    for name in names:
        value = fields.get(name)
        if value:
            return str(value)
    return ""


def sync_base_rows(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    app_token: str,
    table_id: str,
    rows: list[dict[str, Any]],
) -> SyncResult:
    imported = 0
    errors: list[str] = []
    for row in rows:
        try:
            record_id = str(row["record_id"])
            fields = dict(row.get("fields") or {})
            title = _field(fields, ["标题", "title", "Title"]) or record_id
            body = _field(fields, ["正文", "正文内容", "视频文案", "content", "Content"])
            repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_type="feishu_base_record",
                title=title,
                content_text=body,
                content_json={"fields": fields},
                visibility="team",
                owner_open_id=actor_open_id,
                mapping={
                    "system": "feishu",
                    "external_type": "base_record",
                    "external_id": f"{app_token}:{table_id}:{record_id}",
                },
                outbox_topics=["meili_index", "embedding_generate", "graph_ingest"],
            )
            imported += 1
        except Exception as exc:
            errors.append(str(exc))
    return SyncResult(imported=imported, errors=errors)


def sync_wiki_documents(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    space_id: str,
    documents: list[dict[str, Any]],
) -> SyncResult:
    imported = 0
    errors: list[str] = []
    for doc in documents:
        try:
            obj_token = str(doc["obj_token"])
            title = str(doc.get("title") or obj_token)
            content = str(doc.get("content") or "")
            resource = repo.upsert_resource(
                tenant_id=tenant_id,
                actor_open_id=actor_open_id,
                resource_type="feishu_doc",
                title=title,
                content_text=content,
                content_json={"space_id": space_id, "obj_token": obj_token},
                visibility="team",
                owner_open_id=actor_open_id,
                mapping={"system": "feishu", "external_type": "docx", "external_id": obj_token},
                outbox_topics=["meili_index", "embedding_generate", "graph_ingest"],
            )
            chunks = [chunk.strip() for chunk in content.split("\n\n") if chunk.strip()]
            for index, chunk in enumerate(chunks):
                repo.add_embedding_chunk(resource_id=resource.id, chunk_index=index, chunk_text=chunk)
            imported += 1
        except Exception as exc:
            errors.append(str(exc))
    return SyncResult(imported=imported, errors=errors)
```

- [x] **Step 5: Run sync tests**

Run:

```powershell
uv run pytest tests/data_foundation/test_feishu_sync.py -q
```

Expected: PASS.

- [x] **Step 6: Commit**

```powershell
git add data_foundation tests/data_foundation
git commit -m "feat: ingest feishu resources into postgres"
```

## Task 4: Keyword Search, Pgvector Interface, Graph Expansion

**Files:**
- Create: `data_foundation/search.py`
- Create: `data_foundation/graph.py`
- Modify: `data_foundation/repository.py`
- Create: `tests/data_foundation/test_search_graph_tools.py`

- [x] **Step 1: Write failing search and graph tests**

Create the first half of `tests/data_foundation/test_search_graph_tools.py`:

```python
from data_foundation.graph import expand_graph
from data_foundation.repository import ResourceRepository
from data_foundation.search import keyword_search, semantic_search


def _seed_search_resources(repo: ResourceRepository):
    first = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="topic",
        title="露营装备",
        content_text="帐篷 天幕 炉具",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )
    second = repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="topic",
        title="厨房收纳",
        content_text="抽屉 分隔盒 标签",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )
    return first, second


def test_keyword_search_filters_by_query_and_permission(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    _seed_search_resources(repo)

    results = keyword_search(repo, tenant_id="default", actor_open_id="ou_other", query="露营", limit=10)

    assert [item.title for item in results] == ["露营装备"]
    assert results[0].score > 0


def test_semantic_search_uses_pgvector_query_interface(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first, _ = _seed_search_resources(repo)
    vector = [0.1] * 1536
    repo.set_embedding(resource_id=first.id, chunk_index=0, chunk_text="帐篷 天幕 炉具", embedding=vector, embedding_model="test")

    results = semantic_search(
        repo,
        tenant_id="default",
        actor_open_id="ou_owner",
        embedding=vector,
        embedding_model="test",
        top_k=3,
    )

    assert results[0].resource_id == first.id


def test_expand_graph_returns_k_hop_nodes_with_edges(migrated_conn):
    repo = ResourceRepository(migrated_conn)
    first, second = _seed_search_resources(repo)
    repo.add_edge(
        tenant_id="default",
        source_resource_id=first.id,
        target_resource_id=second.id,
        edge_type="SIMILAR_TO",
        weight=0.7,
    )

    graph = expand_graph(
        repo,
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_ids=[first.id],
        hops=1,
        edge_types=["SIMILAR_TO"],
    )

    assert {node.resource_id for node in graph.nodes} == {first.id, second.id}
    assert graph.edges[0].edge_type == "SIMILAR_TO"
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```powershell
uv run pytest tests/data_foundation/test_search_graph_tools.py -q
```

Expected before implementation: FAIL because search/graph modules and repository methods are missing.

- [x] **Step 3: Add repository search, embedding, and edge methods**

Append these methods inside `ResourceRepository`:

```python
    def keyword_rows(self, *, tenant_id: str, actor_open_id: str, query: str, limit: int):
        return self.conn.execute(
            f"""
            select r.*,
                   ts_rank(
                     to_tsvector('simple', coalesce(r.title, '') || ' ' || coalesce(r.summary, '') || ' ' || coalesce(r.content_text, '')),
                     plainto_tsquery('simple', %(query)s)
                   ) as score
            from resources r
            where {readable_resource_where('r')}
              and to_tsvector('simple', coalesce(r.title, '') || ' ' || coalesce(r.summary, '') || ' ' || coalesce(r.content_text, ''))
                  @@ plainto_tsquery('simple', %(query)s)
            order by score desc, r.updated_at desc
            limit %(limit)s
            """,
            {"tenant_id": tenant_id, "actor_open_id": actor_open_id, "query": query, "limit": limit},
        ).fetchall()

    def set_embedding(self, *, resource_id: str, chunk_index: int, chunk_text: str, embedding: list[float], embedding_model: str) -> None:
        vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
        self.conn.execute(
            """
            insert into resource_embeddings (resource_id, chunk_index, chunk_text, embedding, embedding_model)
            values (%s, %s, %s, %s::vector, %s)
            on conflict(resource_id, chunk_index, embedding_model)
            do update set chunk_text=excluded.chunk_text, embedding=excluded.embedding
            """,
            (resource_id, chunk_index, chunk_text, vector_literal, embedding_model),
        )
        self.conn.commit()

    def semantic_rows(self, *, tenant_id: str, actor_open_id: str, embedding: list[float], embedding_model: str, top_k: int):
        vector_literal = "[" + ",".join(str(value) for value in embedding) + "]"
        return self.conn.execute(
            f"""
            select r.*, 1 - (e.embedding <=> %(embedding)s::vector) as score
            from resource_embeddings e
            join resources r on r.id = e.resource_id
            where e.embedding_model = %(embedding_model)s
              and e.embedding is not null
              and {readable_resource_where('r')}
            order by e.embedding <=> %(embedding)s::vector
            limit %(top_k)s
            """,
            {
                "tenant_id": tenant_id,
                "actor_open_id": actor_open_id,
                "embedding": vector_literal,
                "embedding_model": embedding_model,
                "top_k": top_k,
            },
        ).fetchall()

    def add_edge(self, *, tenant_id: str, source_resource_id: str, target_resource_id: str, edge_type: str, weight: float = 1.0) -> None:
        self.conn.execute(
            """
            insert into resource_edges (tenant_id, source_resource_id, target_resource_id, edge_type, weight)
            values (%s, %s, %s, %s, %s)
            on conflict(source_resource_id, target_resource_id, edge_type)
            do update set weight=excluded.weight
            """,
            (tenant_id, source_resource_id, target_resource_id, edge_type, weight),
        )
        self.conn.commit()
```

- [x] **Step 4: Implement search functions**

Create `data_foundation/search.py`:

```python
from __future__ import annotations

from data_foundation.models import ResourceSearchResult
from data_foundation.repository import ResourceRepository


def _result_from_row(row) -> ResourceSearchResult:
    return ResourceSearchResult(
        resource_id=str(row["id"]),
        title=row["title"],
        summary=row["summary"],
        score=float(row["score"] or 0),
        metadata={"type": row["type"], "visibility": row["visibility"]},
    )


def keyword_search(repo: ResourceRepository, *, tenant_id: str, actor_open_id: str, query: str, limit: int = 10) -> list[ResourceSearchResult]:
    safe_limit = min(max(int(limit), 1), 20)
    return [_result_from_row(row) for row in repo.keyword_rows(tenant_id=tenant_id, actor_open_id=actor_open_id, query=query, limit=safe_limit)]


def semantic_search(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    embedding: list[float],
    embedding_model: str,
    top_k: int = 10,
) -> list[ResourceSearchResult]:
    safe_top_k = min(max(int(top_k), 1), 20)
    return [
        _result_from_row(row)
        for row in repo.semantic_rows(
            tenant_id=tenant_id,
            actor_open_id=actor_open_id,
            embedding=embedding,
            embedding_model=embedding_model,
            top_k=safe_top_k,
        )
    ]
```

- [x] **Step 5: Implement graph expansion**

Create `data_foundation/graph.py`:

```python
from __future__ import annotations

from data_foundation.models import GraphEdge, GraphExpansion, GraphNode
from data_foundation.permissions import readable_resource_where
from data_foundation.repository import ResourceRepository


def expand_graph(
    repo: ResourceRepository,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_ids: list[str],
    hops: int = 1,
    edge_types: list[str] | None = None,
) -> GraphExpansion:
    safe_hops = min(max(int(hops), 1), 3)
    rows = repo.conn.execute(
        f"""
        with recursive walk(source_id, target_id, edge_type, weight, depth) as (
          select e.source_resource_id, e.target_resource_id, e.edge_type, e.weight, 1
          from resource_edges e
          where e.tenant_id = %(tenant_id)s
            and e.source_resource_id = any(%(resource_ids)s::uuid[])
            and (%(edge_types)s::text[] is null or e.edge_type = any(%(edge_types)s::text[]))
          union all
          select e.source_resource_id, e.target_resource_id, e.edge_type, e.weight, walk.depth + 1
          from resource_edges e
          join walk on walk.target_id = e.source_resource_id
          where e.tenant_id = %(tenant_id)s
            and walk.depth < %(hops)s
            and (%(edge_types)s::text[] is null or e.edge_type = any(%(edge_types)s::text[]))
        ),
        node_ids as (
          select unnest(%(resource_ids)s::uuid[]) as id, 0 as depth
          union
          select target_id as id, min(depth) as depth from walk group by target_id
        )
        select 'node' as kind, r.id, r.title, r.type, n.depth,
               null::uuid as source_resource_id, null::uuid as target_resource_id, null::text as edge_type, null::float as weight
        from node_ids n
        join resources r on r.id = n.id
        where {readable_resource_where('r')}
        union all
        select 'edge' as kind, null::uuid as id, null::text as title, null::text as type, depth,
               source_id, target_id, edge_type, weight
        from walk
        order by kind desc, depth asc
        """,
        {
            "tenant_id": tenant_id,
            "actor_open_id": actor_open_id,
            "resource_ids": resource_ids,
            "edge_types": edge_types,
            "hops": safe_hops,
        },
    ).fetchall()

    nodes = [
        GraphNode(resource_id=str(row["id"]), title=row["title"], type=row["type"], depth=int(row["depth"]))
        for row in rows
        if row["kind"] == "node"
    ]
    visible_ids = {node.resource_id for node in nodes}
    edges = [
        GraphEdge(
            source_resource_id=str(row["source_resource_id"]),
            target_resource_id=str(row["target_resource_id"]),
            edge_type=row["edge_type"],
            weight=float(row["weight"]),
        )
        for row in rows
        if row["kind"] == "edge"
        and str(row["source_resource_id"]) in visible_ids
        and str(row["target_resource_id"]) in visible_ids
    ]
    return GraphExpansion(nodes=nodes, edges=edges)
```

- [x] **Step 6: Run search and graph tests**

Run:

```powershell
uv run pytest tests/data_foundation/test_search_graph_tools.py -q
```

Expected: PASS.

- [x] **Step 7: Commit**

```powershell
git add data_foundation tests/data_foundation
git commit -m "feat: add postgres search and graph expansion"
```

## Task 5: DeepAgents Tools Integration

**Files:**
- Create: `data_foundation/tools.py`
- Modify: `agent.py`
- Modify: `tests/data_foundation/test_search_graph_tools.py`
- Modify: `tests/test_agent_assembly.py`

- [x] **Step 1: Add failing tool tests**

Append to `tests/data_foundation/test_search_graph_tools.py`:

```python
class _User:
    identity = "ou_owner"


class _ServerInfo:
    user = _User()


class _Config:
    server_info = _ServerInfo()


def test_tools_reject_missing_identity(monkeypatch):
    from data_foundation.tools import search_resources

    try:
        search_resources.func("露营", config=None)
    except PermissionError as exc:
        assert "Missing LangGraph user identity" in str(exc)
    else:
        raise AssertionError("search_resources should reject missing identity")


def test_search_tool_returns_structured_json(monkeypatch, migrated_conn):
    from data_foundation import tools as df_tools
    from data_foundation.repository import ResourceRepository

    repo = ResourceRepository(migrated_conn)
    repo.upsert_resource(
        tenant_id="default",
        actor_open_id="ou_owner",
        resource_type="topic",
        title="露营装备",
        content_text="帐篷 天幕",
        content_json={},
        visibility="team",
        owner_open_id="ou_owner",
    )
    monkeypatch.setattr(df_tools, "connect", lambda: migrated_conn)

    result = df_tools.search_resources.func("露营", limit=10, config=_Config())

    assert result["ok"] is True
    assert result["results"][0]["title"] == "露营装备"
    assert "content_text" not in result["results"][0]
```

Append to `tests/test_agent_assembly.py`:

```python
def test_agent_registers_data_foundation_tools(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_module

    agent_module = importlib.reload(agent_module)
    tool_names = {getattr(tool, "name", "") for tool in agent_module.phase3_tools}

    assert {"search_resources", "semantic_search_resources", "graph_expand", "get_resource"} <= tool_names
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```powershell
uv run pytest tests/data_foundation/test_search_graph_tools.py tests/test_agent_assembly.py::test_agent_registers_data_foundation_tools -q
```

Expected before implementation: FAIL because `data_foundation.tools` and `agent.phase3_tools` are missing.

- [x] **Step 3: Implement DeepAgents tool wrappers**

Create `data_foundation/tools.py`:

```python
from __future__ import annotations

import os

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from data_foundation.db import connect
from data_foundation.graph import expand_graph as expand_graph_query
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.repository import ResourceRepository
from data_foundation.search import keyword_search, semantic_search


def _repo() -> ResourceRepository:
    return ResourceRepository(connect())


def _fake_embedding(query: str) -> list[float]:
    seed = sum(ord(ch) for ch in query) or 1
    return [float((seed + index) % 100) / 100.0 for index in range(1536)]


@tool
def search_resources(query: str, limit: int = 10, config: RunnableConfig = None) -> dict:
    """Search readable resources by keyword. Returns summaries only."""
    actor = actor_from_config(config)
    repo = _repo()
    results = keyword_search(repo, tenant_id=default_tenant_id(), actor_open_id=actor, query=query, limit=limit)
    return {
        "ok": True,
        "results": [
            {
                "resource_id": item.resource_id,
                "title": item.title,
                "summary": item.summary,
                "score": item.score,
                "metadata": item.metadata,
            }
            for item in results
        ],
    }


@tool
def semantic_search_resources(query: str, top_k: int = 10, config: RunnableConfig = None) -> dict:
    """Search readable resources by pgvector. Embedding provider integration is isolated behind this wrapper."""
    actor = actor_from_config(config)
    repo = _repo()
    embedding_model = os.environ.get("XHS_EMBEDDING_MODEL", "test")
    results = semantic_search(
        repo,
        tenant_id=default_tenant_id(),
        actor_open_id=actor,
        embedding=_fake_embedding(query),
        embedding_model=embedding_model,
        top_k=top_k,
    )
    return {
        "ok": True,
        "results": [
            {"resource_id": item.resource_id, "title": item.title, "summary": item.summary, "score": item.score, "metadata": item.metadata}
            for item in results
        ],
    }


@tool
def get_resource(resource_id: str, config: RunnableConfig = None) -> dict:
    """Read one resource body after permission filtering."""
    actor = actor_from_config(config)
    repo = _repo()
    resource = repo.get_resource(default_tenant_id(), actor, resource_id)
    if not resource:
        return {"ok": False, "error": "Resource not found or not permitted"}
    return {
        "ok": True,
        "resource": {
            "resource_id": resource.id,
            "type": resource.type,
            "title": resource.title,
            "summary": resource.summary,
            "content_text": resource.content_text,
            "content_json": resource.content_json,
        },
    }


@tool
def graph_expand(resource_ids: list[str], hops: int = 1, edge_types: list[str] | None = None, config: RunnableConfig = None) -> dict:
    """Expand readable graph context from resource ids."""
    actor = actor_from_config(config)
    repo = _repo()
    graph = expand_graph_query(
        repo,
        tenant_id=default_tenant_id(),
        actor_open_id=actor,
        resource_ids=resource_ids,
        hops=hops,
        edge_types=edge_types,
    )
    return {
        "ok": True,
        "nodes": [node.__dict__ for node in graph.nodes],
        "edges": [edge.__dict__ for edge in graph.edges],
    }


phase3_tools = [search_resources, semantic_search_resources, graph_expand, get_resource]
```

- [x] **Step 4: Register tools in `agent.py`**

Modify imports in `agent.py`:

```python
from data_foundation.tools import phase3_tools
```

Modify the `create_deep_agent` call:

```python
    tools=[read_xhs_data, read_feishu_wiki] + phase3_tools + get_lark_mcp_tools(),
```

This keeps DeepAgents native assembly intact and only adds normal LangChain tools.

- [x] **Step 5: Run tool and assembly tests**

Run:

```powershell
uv run pytest tests/data_foundation/test_search_graph_tools.py tests/test_agent_assembly.py -q
```

Expected: PASS.

- [x] **Step 6: Commit**

```powershell
git add agent.py data_foundation tests
git commit -m "feat: expose data foundation tools to deepagents"
```

## Task 6: Documentation And Final Verification

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-06-19-phase-3-universal-data-foundation.md`

- [x] **Step 1: Document environment**

Add to `.env.example`:

```dotenv
# Phase 3 data foundation
XHS_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/xhs
XHS_DEFAULT_TENANT_ID=default
XHS_EMBEDDING_MODEL=test

# Test-only Postgres database. Must support pgcrypto and pgvector.
TEST_XHS_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/xhs_test
```

- [x] **Step 2: Document setup and boundaries**

Add to `README.md` after the Phase 2 section:

```markdown
## 第三阶段数据底座

- `XHS_DATABASE_URL` 指向 Postgres 权威业务库。
- 数据库必须启用 `pgcrypto` 与 `vector` 扩展。
- `XHS_DEFAULT_TENANT_ID` 默认是 `default`；Agent 不允许通过 tool 参数自由传 tenant。
- DeepAgents/LangGraph 仍是唯一 agent runtime；第三阶段只新增普通 LangChain tools。
- 项目不恢复交互式 CLI 运行入口；飞书 `lark-cli` 只作为 server/worker 内部 adapter。
- Meilisearch、Graphiti、Neo4j/FalkorDB、Dagster 暂不作为第一闭环启动依赖，它们通过 `resource_outbox` 后续接入。
```

- [x] **Step 3: Run backend tests**

Run:

```powershell
uv run pytest -q
```

Expected: PASS. If `TEST_XHS_DATABASE_URL` is not set, `tests/data_foundation/*` are skipped and all existing tests still pass. In CI or Phase 3 verification, `TEST_XHS_DATABASE_URL` must be set so Postgres tests run.

- [x] **Step 4: Run frontend type/lint checks**

Run:

```powershell
cd web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
```

Expected: TypeScript passes. ESLint may still report the existing warning count, but no new errors should appear.

- [x] **Step 5: Update implementation status in this plan**

At the top of this file, after the header, add:

```markdown
## Implementation Status

Completed on 2026-06-19.

- Postgres schema and migrations are in `data_foundation/schema.sql`.
- Repository writes resources, versions, events, mappings, outbox rows, permissions, embeddings, and edges.
- Feishu Base/Wiki/Doc ingestion writes through DAL.
- Keyword search, pgvector interface, and graph expansion are available through DeepAgents tools.
- Meilisearch/Graphiti/Neo4j/Dagster remain outbox-backed future adapters.
```

- [x] **Step 6: Commit**

```powershell
git add .env.example README.md docs/superpowers/plans/2026-06-19-phase-3-universal-data-foundation.md
git commit -m "docs: document phase three data foundation"
```

## Self-Review Checklist

- Spec coverage: Phase 3.1 maps to Tasks 1-2; Phase 3.2 maps to Task 3; Phase 3.3 maps to Task 4 and Task 5; Phase 3.4 maps to Task 4 and Task 5.
- DeepAgents boundary: Task 5 adds normal LangChain tools to existing `create_deep_agent`; it does not fork, monkey-patch, or replace DeepAgents/LangGraph.
- CLI boundary: no task creates a project-owned CLI runtime entrypoint. Existing `tools/web_bridge_runner.py` remains an internal Web/server bridge only.
- Postgres boundary: tests and implementation use Postgres, `pgcrypto`, and `pgvector`; SQLite is not used.
- Permission boundary: every read path requires tenant and actor, and tools resolve actor from `RunnableConfig.server_info.user.identity`.
- Outbox boundary: external index/graph/writeback side effects are represented as `resource_outbox` topics and do not run inside the resource write transaction.
- First implementation boundary: Meilisearch, Graphiti, Neo4j/FalkorDB, and Dagster are intentionally not runtime dependencies in this plan.
