from __future__ import annotations

import os
from contextlib import contextmanager
from importlib import resources
from typing import Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row

def database_url() -> str:
    url = os.environ.get("XHS_DATABASE_URL")
    if not url:
        raise RuntimeError("XHS_DATABASE_URL is required for Phase 3 data foundation")
    return url


def connect(url: str | None = None) -> Connection:
    return psycopg.connect(url or database_url(), row_factory=dict_row)


def run_migrations(conn: Connection) -> None:
    schema_sql = resources.files("data_foundation").joinpath("schema.sql").read_text(encoding="utf-8")
    conn.execute(schema_sql)
    conn.commit()


@contextmanager
def transaction(conn: Connection) -> Iterator[Connection]:
    with conn.transaction():
        yield conn
