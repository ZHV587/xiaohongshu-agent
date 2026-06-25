import psycopg
import re
from typing import Tuple, Generator, Optional
from psycopg import Connection
from contextlib import contextmanager, AbstractContextManager
from data_foundation import db
from data_foundation.models import RuntimeIdentityConfig

class BaseRepository:
    def __init__(self, conn: Optional[Connection] = None) -> None:
        self.conn = conn

    def unit_of_work(self) -> AbstractContextManager[Connection]:
        if self.conn is None:
            raise RuntimeError("Repository has no connection associated to start unit_of_work")
        from data_foundation.db import transaction
        return transaction(self.conn)

    def _resolve_connection(self, conn: Optional[Connection] = None) -> Tuple[Connection, bool]:
        """Resolve a connection. Returns (connection, should_close)."""
        resolved = conn or self.conn
        if resolved is not None:
            return resolved, False
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
        
        from data_foundation.permissions import readable_resource_where as perm_where
        actual_alias = alias if alias is not None else "r"
        fragment = perm_where(actual_alias)
        
        clean_tenant = actor.tenant_id.replace("'", "''")
        clean_user = actor.open_id.replace("'", "''")
        fragment = fragment.replace("%(tenant_id)s", f"'{clean_tenant}'")
        fragment = fragment.replace("%(actor_open_id)s", f"'{clean_user}'")
        
        if alias is None:
            fragment = fragment.replace("r.", "")
            
        return f"({fragment.strip()})"

