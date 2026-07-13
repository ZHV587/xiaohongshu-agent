from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from data_foundation.db import run_migrations

import re
import importlib.resources
import data_foundation.db

# Monkeypatch pgvector migrations to run on local Postgres
def patched_apply_migrations(conn):
    schema_sql = importlib.resources.files("data_foundation").joinpath("schema.sql").read_text(encoding="utf-8")
    schema_sql = schema_sql.replace("create extension if not exists vector with schema public;", "")
    schema_sql = schema_sql.replace("embedding public.vector(1536) not null", "embedding double precision[] not null")
    schema_sql = schema_sql.replace("%s::public.vector", "%s::double precision[]")
    # Only the pgvector index statement is unsupported by vanilla Postgres.  The
    # surrounding PL/pgSQL migration blocks use core PostgreSQL features and must
    # still run, otherwise this fixture silently tests a different schema upgrade
    # path from production.
    schema_sql = re.sub(
        r"create index if not exists idx_resource_embeddings_vector\s+on resource_embeddings using (ivfflat|hnsw)[^;]+;",
        "",
        schema_sql
    )
    conn.execute(schema_sql)

data_foundation.db._apply_migrations = patched_apply_migrations

# Intercept and clean SQL and parameters for pgvector translation
_real_conn_execute = psycopg.Connection.execute
_real_cur_execute = psycopg.Cursor.execute
_real_cur_executemany = psycopg.Cursor.executemany

def clean_param(p):
    if isinstance(p, str) and p.startswith("[") and p.endswith("]"):
        try:
            return [float(x) for x in p[1:-1].split(",")]
        except ValueError:
            pass
    return p

def clean_params(params):
    if params is None:
        return None
    if isinstance(params, tuple):
        return tuple(clean_param(p) for p in params)
    if isinstance(params, list):
        return [clean_param(p) for p in params]
    if isinstance(params, dict):
        return {k: clean_param(v) for k, v in params.items()}
    return params

def clean_sql(sql):
    if isinstance(sql, str):
        sql = sql.replace("::public.vector", "::double precision[]")
        sql = sql.replace("::vector", "::double precision[]")
    return sql

def patched_conn_execute(self, query, params=None, *args, **kwargs):
    query = clean_sql(query)
    params = clean_params(params)
    return _real_conn_execute(self, query, params, *args, **kwargs)

def patched_cur_execute(self, query, params=None, *args, **kwargs):
    query = clean_sql(query)
    params = clean_params(params)
    return _real_cur_execute(self, query, params, *args, **kwargs)

def patched_cur_executemany(self, query, params_seq, *args, **kwargs):
    query = clean_sql(query)
    if params_seq is not None:
        params_seq = [clean_params(p) for p in params_seq]
    return _real_cur_executemany(self, query, params_seq, *args, **kwargs)

psycopg.Connection.execute = patched_conn_execute
psycopg.Cursor.execute = patched_cur_execute
psycopg.Cursor.executemany = patched_cur_executemany


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_XHS_DATABASE_URL")
    if not url:
        pytest.skip("TEST_XHS_DATABASE_URL is required for Phase 3 Postgres tests")
    return url


class HybridRow(dict):
    def __init__(self, colnames, values):
        super().__init__(zip(colnames, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)

    def __eq__(self, other):
        if isinstance(other, (tuple, list)):
            return self._values == tuple(other)
        return super().__eq__(other)

def hybrid_row_factory(cursor):
    if cursor.description is None:
        return lambda values: values
    colnames = [desc.name for desc in cursor.description]
    return lambda values: HybridRow(colnames, values)

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
    finally:
        with psycopg.connect(database_url, autocommit=True, row_factory=hybrid_row_factory) as admin:
            admin.execute(f'drop schema if exists "{schema}" cascade')
