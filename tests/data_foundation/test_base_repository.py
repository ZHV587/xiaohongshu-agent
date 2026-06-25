import pytest
from data_foundation.repositories.base import BaseRepository
from data_foundation.models import RuntimeIdentityConfig

def test_apply_permission_filter_sql():
    actor = RuntimeIdentityConfig(tenant_id="tenant_123", open_id="user_abc")
    repo = BaseRepository()
    sql_fragment = repo.readable_resource_where(actor)
    assert "tenant_id = 'tenant_123'" in sql_fragment
    assert "owner_id = 'user_abc'" in sql_fragment
