import psycopg
import re
from typing import Tuple, Generator, Optional
from psycopg import Connection
from contextlib import contextmanager, AbstractContextManager
from data_foundation import db

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

    def readable_resource_where(self, alias: Optional[str] = None) -> str:
        """返回参数化的租户/ACL 过滤片段(命名占位符,不拼接身份值)。

        安全:tenant_id / actor_open_id 一律走命名占位符 %(tenant_id)s / %(actor_open_id)s
        由 psycopg 绑定,绝不把身份值拼进 SQL 文本——与 permissions.readable_resource_where
        保持单一实现,消除手动转义的注入面。调用方必须用命名参数 dict 传入这两个键
        (tenant_id / actor_open_id);同一查询里多别名复用同名占位符即可(psycopg 按名绑定)。
        """
        if alias is not None and not re.match(r"^[a-zA-Z0-9_]+$", alias):
            raise ValueError("Invalid alias")

        from data_foundation.permissions import readable_resource_where as perm_where

        actual_alias = alias if alias is not None else "r"
        fragment = perm_where(actual_alias)
        if alias is None:
            fragment = fragment.replace("r.", "")
        return f"({fragment.strip()})"

