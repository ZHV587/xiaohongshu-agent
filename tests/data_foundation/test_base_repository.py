import pytest
from unittest.mock import MagicMock
from data_foundation.repositories.base import BaseRepository
from data_foundation.models import RuntimeIdentityConfig
from data_foundation import db

def test_apply_permission_filter_sql():
    actor = RuntimeIdentityConfig(tenant_id="tenant_123", open_id="user_abc")
    repo = BaseRepository()
    sql_fragment = repo.readable_resource_where(actor)
    assert "tenant_id = 'tenant_123'" in sql_fragment
    assert "owner_open_id = 'user_abc'" in sql_fragment

def test_apply_permission_filter_sql_with_alias():
    actor = RuntimeIdentityConfig(tenant_id="tenant_123", open_id="user_abc")
    repo = BaseRepository()
    
    # Test with table alias "r"
    sql_fragment_alias = repo.readable_resource_where(actor, alias="r")
    assert "r.tenant_id = 'tenant_123'" in sql_fragment_alias
    assert "r.owner_open_id = 'user_abc'" in sql_fragment_alias
    assert "r.visibility = 'team'" in sql_fragment_alias

def test_sql_injection_escaping():
    actor = RuntimeIdentityConfig(tenant_id="tenant' OR '1'='1", open_id="user' OR '1'='1")
    repo = BaseRepository()
    sql_fragment = repo.readable_resource_where(actor)
    # The clean values should escape single quotes with two single quotes
    assert "tenant'' OR ''1''=''1" in sql_fragment
    assert "user'' OR ''1''=''1" in sql_fragment
    # Ensure raw single quotes are not present in the values themselves
    assert "tenant' OR" not in sql_fragment
    assert "user' OR" not in sql_fragment

def test_get_connection_provided():
    repo = BaseRepository()
    mock_conn = MagicMock()
    conn, is_owner = repo.get_connection(mock_conn)
    assert conn is mock_conn
    assert is_owner is False

def test_get_connection_not_provided(monkeypatch):
    repo = BaseRepository()
    mock_new_conn = MagicMock()
    
    # Mock db.connect to return our fake connection
    monkeypatch.setattr(db, "connect", lambda: mock_new_conn)
    
    conn, is_owner = repo.get_connection()
    assert conn is mock_new_conn
    assert is_owner is True
