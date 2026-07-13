from __future__ import annotations

import os
from contextlib import contextmanager
from importlib import resources
from typing import Any, Iterator

import psycopg
from psycopg import Connection
from psycopg import sql
from psycopg.rows import dict_row


DATA_FOUNDATION_TABLES = (
    "data_foundation_migrations",
    "user_skill_audit_events",
    "user_skill_publications",
    "user_skill_versions",
    "user_skills",
    "user_skill_revisions",
    "service_error_aggregates",
    "sync_runs",
    "service_executions",
    "service_instances",
    "sync_sources",
    "generated_copy_states",
    "resource_outbox",
    "resource_embeddings",
    "embedding_indexes",
    "resource_edges",
    "resource_permissions",
    "resource_events",
    "resource_versions",
    "resource_mappings",
    "resource_type_counts",
    "resources",
)

def database_url() -> str:
    url = os.environ.get("XHS_DATABASE_URL")
    if not url:
        raise RuntimeError("XHS_DATABASE_URL is required for Phase 3 data foundation")
    return url


def connect(url: str | None = None, **kwargs: Any) -> Connection:
    return psycopg.connect(url or database_url(), row_factory=dict_row, **kwargs)


def run_migrations(conn: Connection) -> None:
    _apply_migrations(conn)
    conn.commit()


def _apply_migrations(conn: Connection) -> None:
    schema_sql = resources.files("data_foundation").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.execute(schema_sql)


def reset_data_foundation(conn: Connection) -> None:
    with conn.transaction():
        for name in DATA_FOUNDATION_TABLES:
            conn.execute(sql.SQL("drop table if exists {}").format(sql.Identifier(name)))
        _apply_migrations(conn)


@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    with conn.transaction():
        yield conn
