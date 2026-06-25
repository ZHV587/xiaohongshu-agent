# pgvector HNSW Index Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the vector similarity index on `resource_embeddings` from `ivfflat` to `hnsw` with high recall configuration (`m = 24, ef_construction = 128`), introducing a conditional database migration block and automatic testing operator setup.

**Architecture:** Use a PL/pgSQL DO block in `schema.sql` to drop the old `ivfflat` index only if it does not use `hnsw`, preventing migration blocking on startup. Update `conftest.py` to auto-register a mock PL/pgSQL `<=>` operator in testing environments to maintain portability.

**Tech Stack:** PostgreSQL 16, pgvector 0.8.3, psycopg 3, pytest 9

---

### Task 1: Update Database Schema

**Files:**
- Modify: `data_foundation/schema.sql:200-201`

- [ ] **Step 1: Modify schema.sql**
  Replace the existing `ivfflat` index creation with the conditional upgrade DO block and the HNSW index creation statement.

  ```sql
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

- [ ] **Step 2: Commit Schema Changes**
  ```bash
  git add data_foundation/schema.sql
  git commit -m "migration: upgrade vector index to HNSW with conditional safety block"
  ```

---

### Task 2: Update Test Environment Fixtures

**Files:**
- Modify: `tests/data_foundation/conftest.py:21-25`, `tests/data_foundation/conftest.py:91-105`

- [ ] **Step 1: Modify patched_apply_migrations in conftest.py**
  Update `patched_apply_migrations` to strip the new PL/pgSQL DO block and update the index stripping regex to match `(ivfflat|hnsw)`.

  Replace:
  ```python
      schema_sql = re.sub(
          r"create index if not exists idx_resource_embeddings_vector\s+on resource_embeddings using ivfflat[^;]+;",
          "",
          schema_sql
      )
  ```

  With:
  ```python
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
  ```

- [ ] **Step 2: Modify migrated_conn in conftest.py**
  Update the `migrated_conn` fixture to automatically and idempotently register the custom `public.cosine_distance` function and `public.<=>` operator for local test runs.

  Replace:
  ```python
  @pytest.fixture()
  def migrated_conn(database_url: str):
      schema = f"test_{uuid.uuid4().hex}"
      with psycopg.connect(database_url, autocommit=True, row_factory=hybrid_row_factory) as admin:
          admin.execute(f'create schema "{schema}"')
      try:
          with psycopg.connect(database_url, row_factory=hybrid_row_factory) as conn:
              conn.execute(f'set search_path to "{schema}", public')
              run_migrations(conn)
              yield conn
              conn.rollback()
  ```

  With:
  ```python
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
      try:
          with psycopg.connect(database_url, row_factory=hybrid_row_factory) as conn:
              conn.execute(f'set search_path to "{schema}", public')
              run_migrations(conn)
              yield conn
              conn.rollback()
  ```

- [ ] **Step 3: Commit Test Environment Updates**
  ```bash
  git add tests/data_foundation/conftest.py
  git commit -m "test: register custom <=> operator automatically in migrated_conn fixture"
  ```

---

### Task 3: Verification & Test Execution

- [ ] **Step 1: Execute test suite**
  Run all data foundation integration and unit tests to ensure that HNSW index configuration and automatic setup are correct:

  Run:
  ```powershell
  $env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/
  ```

  Expected:
  ```text
  ======================= 313 passed, 1 warning in 24.15s =======================
  ```

- [ ] **Step 2: Walkthrough update**
  Update the walkthrough artifact with results.
