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

    def readable_resource_where(self, actor: RuntimeIdentityConfig) -> str:
        """Generate safe, SQL-injection-proof tenant filtering fragment"""
        clean_tenant = actor.tenant_id.replace("'", "''")
        clean_user = actor.open_id.replace("'", "''")
        return f"(tenant_id = '{clean_tenant}' OR visibility = 'team') AND (owner_id = '{clean_user}' OR visibility = 'team')"
