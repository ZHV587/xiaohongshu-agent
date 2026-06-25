# Specification - pgvector HNSW Index Upgrade

This document outlines the design specification for upgrading the PostgreSQL vector index type in the data foundation from `ivfflat` to `hnsw` using high recall and high accuracy configuration parameters.

---

## 1. Problem Description

Currently, the vector similarity index on the `resource_embeddings` table is defined using `ivfflat`:
```sql
create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using ivfflat (embedding public.vector_cosine_ops) with (lists = 100);
```

While `ivfflat` has low memory requirements and fast build times, it exhibits two key issues:
1. **Recall Degradation**: As the dataset grows, query recall drops unless the index is frequently rebuilt with updated clustering (`lists`).
2. **Build Restrictions**: `ivfflat` requires the table to have existing data when the index is created to cluster correctly.

### Objective
Upgrade to `hnsw` (Hierarchical Navigable Small World) index to achieve:
- High query recall regardless of dataset size growth.
- Fast query performance under scale.
- Incremental build capability from 0 rows.

---

## 2. Proposed Changes

### 2.1 Database Schema Update
Modify [schema.sql](file:///e:/小红书智能体/data_foundation/schema.sql) to define the vector index using the `hnsw` index type with high accuracy parameters:
- **`m`** = 24 (Max connections per node in the graph)
- **`ef_construction`** = 128 (Size of dynamic candidate list for building)

```sql
-- data_foundation/schema.sql
drop index if exists idx_resource_embeddings_vector;
create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using hnsw (embedding public.vector_cosine_ops) with (m = 24, ef_construction = 128);
```

### 2.2 Test Environment Updates
Update the monkeypatch regular expression in [conftest.py](file:///e:/小红书智能体/tests/data_foundation/conftest.py) to match both `ivfflat` and `hnsw` index creation strings, preventing failure on local Postgres test environments where `pgvector` extension is not present.

```python
# tests/data_foundation/conftest.py
    schema_sql = re.sub(
        r"create index if not exists idx_resource_embeddings_vector\s+on resource_embeddings using (ivfflat|hnsw)[^;]+;",
        "",
        schema_sql
    )
```

---

## 3. Verification Plan

### 3.1 Automated Tests
Run the entire data foundation test suite:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/
```
Verify that:
1. Schema initialization in local testing succeeds (the index definition is correctly stripped by `conftest.py`).
2. All 313 unit/integration tests pass without errors.
