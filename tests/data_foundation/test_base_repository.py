import pytest
from unittest.mock import MagicMock, patch
from data_foundation.repositories.base import BaseRepository
from data_foundation.models import RuntimeIdentityConfig
from data_foundation import db

def test_apply_permission_filter_sql():
    actor = RuntimeIdentityConfig(tenant_id="tenant_123", open_id="user_abc")
    repo = BaseRepository()
    sql_fragment = repo.readable_resource_where(actor)
    # The filter must force the tenant boundary strictly
    assert sql_fragment == "(tenant_id = 'tenant_123' AND (owner_open_id = 'user_abc' OR visibility = 'team'))"

def test_apply_permission_filter_sql_with_alias():
    actor = RuntimeIdentityConfig(tenant_id="tenant_123", open_id="user_abc")
    repo = BaseRepository()
    
    # Test with table alias "r"
    sql_fragment_alias = repo.readable_resource_where(actor, alias="r")
    assert sql_fragment_alias == "(r.tenant_id = 'tenant_123' AND (r.owner_open_id = 'user_abc' OR r.visibility = 'team'))"

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

def test_alias_sql_injection_guard():
    actor = RuntimeIdentityConfig(tenant_id="tenant_123", open_id="user_abc")
    repo = BaseRepository()
    
    # Valid aliases should pass
    repo.readable_resource_where(actor, alias="r")
    repo.readable_resource_where(actor, alias="res_1")
    repo.readable_resource_where(actor, alias=None)
    
    # Invalid aliases should raise ValueError
    with pytest.raises(ValueError, match="Invalid alias"):
        repo.readable_resource_where(actor, alias="r; DROP TABLE resources;")
        
    with pytest.raises(ValueError, match="Invalid alias"):
        repo.readable_resource_where(actor, alias="r-1")

def test_connection_context_provided():
    repo = BaseRepository()
    mock_conn = MagicMock()
    
    with repo.connection_context(mock_conn) as conn:
        assert conn is mock_conn
        
    # Since connection was provided, we must NOT close it
    mock_conn.close.assert_not_called()

def test_connection_context_not_provided(monkeypatch):
    repo = BaseRepository()
    mock_new_conn = MagicMock()
    
    # Mock db.connect
    monkeypatch.setattr(db, "connect", lambda: mock_new_conn)
    
    with repo.connection_context() as conn:
        assert conn is mock_new_conn
        
    # Since connection was opened by the repository, it must be closed automatically
    mock_new_conn.close.assert_called_once()

def test_connection_context_closes_on_error(monkeypatch):
    repo = BaseRepository()
    mock_new_conn = MagicMock()
    monkeypatch.setattr(db, "connect", lambda: mock_new_conn)
    
    with pytest.raises(RuntimeError):
        with repo.connection_context() as conn:
            assert conn is mock_new_conn
            raise RuntimeError("test error")
            
    # Should still close the connection on error
    mock_new_conn.close.assert_called_once()
