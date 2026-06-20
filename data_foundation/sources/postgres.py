from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from data_foundation.errors import classify_error
from data_foundation.outbox_requests import default_write_requests
from data_foundation.sources.base import SourceContext, SourceLease, SourceSyncResult


IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SourceConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PostgresTableConfig:
    schema: str
    table: str
    primary_key: str
    title_column: str
    content_columns: tuple[str, ...]
    updated_at_column: str | None
    resource_type: str
    page_size: int
    statement_timeout_ms: int = 5000

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PostgresTableConfig":
        if "sql" in data:
            raise SourceConfigError("sql is not allowed for PostgreSQL sources")
        required = ("schema", "table", "primary_key", "title_column", "content_columns", "resource_type")
        for key in required:
            if key not in data:
                raise SourceConfigError(f"{key} is required")

        content_columns = tuple(str(column) for column in data["content_columns"])
        if not content_columns:
            raise SourceConfigError("content_columns is required")

        values = {
            "schema": str(data["schema"]),
            "table": str(data["table"]),
            "primary_key": str(data["primary_key"]),
            "title_column": str(data["title_column"]),
            "content_columns": content_columns,
            "updated_at_column": (
                None
                if data.get("updated_at_column") in (None, "")
                else str(data.get("updated_at_column"))
            ),
            "resource_type": str(data["resource_type"]),
            "page_size": int(data.get("page_size", 100)),
            "statement_timeout_ms": int(data.get("statement_timeout_ms", 5000)),
        }
        for key in ("schema", "table", "primary_key", "title_column", "resource_type"):
            _validate_identifier(key, values[key])
        for column in content_columns:
            _validate_identifier("content_columns", column)
        if values["updated_at_column"] is not None:
            _validate_identifier("updated_at_column", values["updated_at_column"])
        if values["page_size"] < 1 or values["page_size"] > 500:
            raise SourceConfigError("page_size must be between 1 and 500")
        if values["statement_timeout_ms"] < 1:
            raise SourceConfigError("statement_timeout_ms must be positive")
        return cls(**values)


class PostgresTableSourceProcessor:
    source_type = "postgres_table"

    def __init__(self, *, resource_repo):
        self.resource_repo = resource_repo
        self.last_observed_transaction_read_only: bool | None = None

    async def sync(self, context: SourceContext, lease: SourceLease) -> SourceSyncResult:
        try:
            config = PostgresTableConfig.from_dict(context.source.config)
            dsn = _postgres_dsn(context.secrets.credentials)
            current_cursor = _cursor_value(context.source.cursor)
            read_count = 0
            created_count = 0

            while True:
                page, read_only = await asyncio.to_thread(
                    self._read_page,
                    dsn,
                    config,
                    current_cursor,
                )
                self.last_observed_transaction_read_only = (
                    read_only if self.last_observed_transaction_read_only is None
                    else self.last_observed_transaction_read_only and read_only
                )
                if not page:
                    break

                await lease.assert_owned()
                for row in page:
                    self._upsert_row(context, config, row)
                    read_count += 1
                    created_count += 1
                    current_cursor = str(row[config.primary_key])

            return SourceSyncResult(
                status="succeeded",
                read_count=read_count,
                created_count=created_count,
                updated_count=0,
                skipped_count=0,
                failed_count=0,
                errors=[],
                cursor={} if current_cursor is None else {"last_pk": current_cursor},
            )
        except Exception as exc:
            classification = classify_error(exc, component="postgres_source", operation="sync")
            return SourceSyncResult(
                status="failed",
                read_count=0,
                created_count=0,
                updated_count=0,
                skipped_count=0,
                failed_count=1,
                errors=[classification.error_summary],
                cursor=context.source.cursor,
            )

    def _read_page(
        self,
        dsn: str,
        config: PostgresTableConfig,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], bool]:
        with psycopg.connect(dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("set transaction read only")
                conn.execute("select set_config('statement_timeout', %s, true)", (str(config.statement_timeout_ms),))
                read_only = conn.execute("show transaction_read_only").fetchone()["transaction_read_only"] == "on"
                columns = _selected_columns(config)
                if cursor is None:
                    query = sql.SQL(
                        "select {columns} from {schema}.{table} order by {primary_key} limit %s"
                    ).format(
                        columns=columns,
                        schema=sql.Identifier(config.schema),
                        table=sql.Identifier(config.table),
                        primary_key=sql.Identifier(config.primary_key),
                    )
                    params: tuple[Any, ...] = (config.page_size,)
                else:
                    query = sql.SQL(
                        """
                        select {columns}
                        from {schema}.{table}
                        where {primary_key} > %s
                        order by {primary_key}
                        limit %s
                        """
                    ).format(
                        columns=columns,
                        schema=sql.Identifier(config.schema),
                        table=sql.Identifier(config.table),
                        primary_key=sql.Identifier(config.primary_key),
                    )
                    params = (cursor, config.page_size)
                rows = conn.execute(query, params).fetchall()
                return [dict(row) for row in rows], read_only

    def _upsert_row(
        self,
        context: SourceContext,
        config: PostgresTableConfig,
        row: dict[str, Any],
    ) -> None:
        primary_key = row[config.primary_key]
        content_json = {config.primary_key: primary_key}
        for column in config.content_columns:
            content_json[column] = row.get(column)
        content_text = "\n".join(
            str(row[column])
            for column in config.content_columns
            if row.get(column) not in (None, "")
        )
        mapping = {
            "system": "postgres",
            "external_type": f"{config.schema}.{config.table}",
            "external_id": str(primary_key),
            "sync_status": "synced",
        }
        if config.updated_at_column and row.get(config.updated_at_column) is not None:
            mapping["external_updated_at"] = row[config.updated_at_column]
        self.resource_repo.upsert_resource(
            tenant_id=context.source.tenant_id,
            actor_open_id=context.actor_open_id,
            resource_type=config.resource_type,
            title=str(row.get(config.title_column) or primary_key),
            content_text=content_text,
            content_json=content_json,
            visibility="team",
            owner_open_id=context.actor_open_id,
            mapping=mapping,
            outbox_requests=default_write_requests(),
        )


def _selected_columns(config: PostgresTableConfig) -> sql.SQL:
    columns = [config.primary_key, config.title_column, *config.content_columns]
    if config.updated_at_column:
        columns.append(config.updated_at_column)
    unique_columns = list(dict.fromkeys(columns))
    return sql.SQL(", ").join(sql.Identifier(column) for column in unique_columns)


def _validate_identifier(key: str, value: str) -> None:
    if not IDENTIFIER.fullmatch(value):
        raise SourceConfigError(f"{key} must be a safe PostgreSQL identifier")


def _postgres_dsn(credentials: dict[str, Any]) -> str:
    dsn = str(credentials.get("dsn") or "")
    if not (dsn.startswith("postgresql://") or dsn.startswith("postgres://")):
        raise SourceConfigError("PostgreSQL source requires a postgresql:// DSN")
    return dsn


def _cursor_value(cursor: dict[str, Any]) -> str | None:
    value = cursor.get("last_pk")
    return None if value in (None, "") else str(value)
