# Specification - pgvector HNSW Index Upgrade

This document outlines the design specification for upgrading the PostgreSQL vector index type in the data foundation from `ivfflat` to `hnsw` using high recall and high accuracy configuration parameters.

---

## 1. Problem Description

Currently, the vector similarity index on the `resource_embeddings` table is defined using `ivfflat`:
```sql
create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using ivfflat (embedding public.vector_cosine_ops) with (lists = 100);
```

While `ivfflat` has low memory requirements and build times, it exhibits two key issues:
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
Modify [schema.sql](file:///e:/小红书智能体/data_foundation/schema.sql). To prevent recreating/rebuilding the HNSW index on every migration check (which blocks the table and degrades startup performance), we introduce a conditional PL/pgSQL block that only drops the existing index if it is NOT currently HNSW.

```sql
-- data_foundation/schema.sql

-- 1. Conditional upgrade block: drop old ivfflat index if it exists
do $$
begin
    if exists (
        select 1 from pg_indexes 
        where indexname = 'idx_resource_embeddings_vector' 
          and indexdef not ilike '%using hnsw%'
    ) then
        drop index idx_resource_embeddings_vector;
    end if;
end $$;

-- 2. Create the HNSW index with high recall parameters
create index if not exists idx_resource_embeddings_vector
  on resource_embeddings using hnsw (embedding public.vector_cosine_ops) with (m = 24, ef_construction = 128);
```

### 2.2 Test Environment Updates
Modify [conftest.py](file:///e:/小红书智能体/tests/data_foundation/conftest.py) to achieve:
1. **Index stripping**: Update the regular expressions to strip both the upgrade PL/pgSQL DO block and the HNSW index statement.
2. **Automatic Cosine Operator Registration**: To make tests completely portable across developer machines without requiring a pre-registered custom operator, the `migrated_conn` fixture will automatically define the `cosine_distance` PL/pgSQL function and the `<=>` operator for `double precision[]` in the `public` schema of the test database.

```python
# tests/data_foundation/conftest.py

# In patched_apply_migrations:
    # Remove the PL/pgSQL upgrade block
    schema_sql = re.sub(
        r"do\s+\$\$.*?end\s+\$\$;",
        "",
        schema_sql,
        flags=re.IGNORECASE | re.DOTALL
    )
    # Remove the HNSW index creation statement
    schema_sql = re.sub(
        r"create index if not exists idx_resource_embeddings_vector\s+on resource_embeddings using (ivfflat|hnsw)[^;]+;",
        "",
        schema_sql
    )

# In migrated_conn fixture:
@pytest.fixture()
def migrated_conn(database_url: str):
    schema = f"test_{uuid.uuid4().hex}"
    with psycopg.connect(database_url, autocommit=True, row_factory=hybrid_row_factory) as admin:
        admin.execute(f'create schema "{schema}"')
        # Define cosine distance function in public schema if not exists
        admin.execute("""
            CREATE OR REPLACE FUNCTION public.cosine_distance(a double precision[], b double precision[])
            RETURNS double precision AS $$
            DECLARE
                dot double precision := 0;
                norm_a double precision := 0;
                norm_b double precision := 0;
                i integer;
            BEGIN
                FOR i IN 1..array_length(a, 1) LOOP
                    dot := dot + a[i] * b[i];
                    norm_a := norm_a + a[i] * a[i];
                    norm_b := norm_b + b[i] * b[i];
                END LOOP;
                IF norm_a = 0 OR norm_b = 0 THEN
                    RETURN 1.0;
                END IF;
                RETURN 1.0 - (dot / (sqrt(norm_a) * sqrt(norm_b)));
            END;
            $$ LANGUAGE plpgsql IMMUTABLE STRICT;
        """)
        # Idempotently define <=> operator in public schema
        res = admin.execute("""
            SELECT 1 FROM pg_operator 
            WHERE oprname = '<=>' 
              AND oprleft = 'double precision[]'::regtype 
              AND oprright = 'double precision[]'::regtype
        """).fetchone()
        if not res:
            admin.execute("""
                CREATE OPERATOR public.<=> (
                    LEFTARG = double precision[],
                    RIGHTARG = double precision[],
                    FUNCTION = public.cosine_distance,
                    COMMUTATOR = <=>
                )
            """)
```

---

## 3. Verification Plan

### 3.1 Automated Tests
Run the entire data foundation test suite:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/
```
Verify that:
1. Schema initialization in local testing succeeds (the upgrade PL/pgSQL block and HNSW index definition are correctly stripped by `conftest.py`).
2. Custom operator `<=>` is registered on the fly and semantic search tests pass successfully.
3. All 313 unit/integration tests pass without errors.
