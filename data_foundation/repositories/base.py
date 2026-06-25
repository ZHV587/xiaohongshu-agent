import psycopg
from data_foundation import db
from data_foundation.models import RuntimeIdentityConfig

class BaseRepository:
    def __init__(self):
        pass

    def get_connection(self, conn=None):
        """If conn is passed, return it; otherwise get a new connection from db.connect()"""
        if conn is not None:
            return conn, False
        return db.connect(), True

    def readable_resource_where(self, actor: RuntimeIdentityConfig, alias: str = None) -> str:
        """Generate safe, SQL-injection-proof tenant filtering fragment"""
        clean_tenant = actor.tenant_id.replace("'", "''")
        clean_user = actor.open_id.replace("'", "''")
        prefix = f"{alias}." if alias else ""
        return f"({prefix}tenant_id = '{clean_tenant}' OR {prefix}visibility = 'team') AND ({prefix}owner_open_id = '{clean_user}' OR {prefix}visibility = 'team')"
