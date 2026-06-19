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
