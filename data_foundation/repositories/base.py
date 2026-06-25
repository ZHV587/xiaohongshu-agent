import psycopg
import re
from typing import Tuple, Generator, Optional
from psycopg import Connection
from contextlib import contextmanager
from data_foundation import db
from data_foundation.models import RuntimeIdentityConfig

class BaseRepository:
    def __init__(self) -> None:
        pass

    def _resolve_connection(self, conn: Optional[Connection] = None) -> Tuple[Connection, bool]:
        """Resolve a connection. Returns (connection, should_close)."""
        if conn is not None:
            return conn, False
        return db.connect(), True

    @contextmanager
    def connection_context(self, conn: Optional[Connection] = None) -> Generator[Connection, None, None]:
        """Context manager to resolve and clean up a database connection."""
        connection, should_close = self._resolve_connection(conn)
        try:
            yield connection
        finally:
            if should_close:
                connection.close()

    def readable_resource_where(self, actor: RuntimeIdentityConfig, alias: Optional[str] = None) -> str:
        """Generate safe, SQL-injection-proof tenant filtering fragment"""
        if alias is not None:
            if not re.match(r"^[a-zA-Z0-9_]+$", alias):
                raise ValueError("Invalid alias")
        
        clean_tenant = actor.tenant_id.replace("'", "''")
        clean_user = actor.open_id.replace("'", "''")
        prefix = f"{alias}." if alias else ""
        return f"({prefix}tenant_id = '{clean_tenant}' AND ({prefix}owner_open_id = '{clean_user}' OR {prefix}visibility = 'team'))"
