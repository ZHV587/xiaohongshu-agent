# tests/test_uat_store.py
import os
import time
import pytest
import httpx
from unittest.mock import patch, MagicMock
from tools.uat_store import save_uat, get_uat, _DEFAULT_STORE_PATH

@pytest.fixture(autouse=True)
def setup_temp_store(tmp_path):
    temp_file = tmp_path / ".test_uat_store.enc"
    with patch.dict(os.environ, {"XHS_UAT_STORE_PATH": str(temp_file)}):
        yield temp_file
    if temp_file.exists():
        temp_file.unlink()

def test_save_and_retrieve_uat():
    # Save a valid token
    open_id = "usr_123"
    uat = "uat_token_xyz"
    refresh = "refresh_xyz"
    expires_at = time.time() + 3600
    
    save_uat(open_id, uat, refresh, expires_at, ["im:message"], "Test User")
    
    # Retrieve it
    retrieved = get_uat(open_id)
    assert retrieved == uat

def test_encrypted_file_safety():
    open_id = "usr_456"
    uat = "secret_uat_token"
    save_uat(open_id, uat, "refresh_token", time.time() + 3600, [], "User")
    
    # Check that file content is raw ciphertext, not containing plaintext secrets
    store_path = os.environ.get("XHS_UAT_STORE_PATH")
    assert os.path.exists(store_path)
    with open(store_path, "rb") as f:
        ciphertext = f.read()
    assert b"secret_uat_token" not in ciphertext

@patch("tools.uat_store.httpx.post")
def test_uat_auto_refresh_success(mock_post):
    # Setup token expiring in 2 minutes
    open_id = "usr_exp"
    old_uat = "exp_uat"
    new_uat = "newly_refreshed_uat"
    
    # Mock refresh response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": new_uat,
        "refresh_token": "new_refresh",
        "expires_in": 7200
    }
    mock_post.return_value = mock_resp
    
    with patch.dict(os.environ, {"FEISHU_APP_ID": "mock_app", "FEISHU_APP_SECRET": "mock_secret"}):
        save_uat(open_id, old_uat, "refresh_xyz", time.time() + 120, [], "Exp User")
        
        # Accessing it triggers refresh
        token = get_uat(open_id)
        assert token == new_uat
        mock_post.assert_called_once()

@patch("tools.uat_store.httpx.post")
def test_uat_refresh_explicit_failure_deletes(mock_post):
    # 模拟飞书明确返回 400 授权已废除或过期
    mock_resp = MagicMock()
    mock_resp.status_code = 400
    mock_resp.text = "invalid_grant"
    mock_post.return_value = mock_resp
    
    open_id = "usr_invalid"
    old_uat = "exp_uat"
    
    with patch.dict(os.environ, {"FEISHU_APP_ID": "mock_app", "FEISHU_APP_SECRET": "mock_secret"}):
        save_uat(open_id, old_uat, "refresh_xyz", time.time() + 120, [], "Exp User")
        
        token = get_uat(open_id)
        assert token is None
        
        # 验证本地记录已被彻底删除
        from tools.uat_store import _read_store
        store = _read_store()
        assert open_id not in store

@patch("tools.uat_store.httpx.post")
def test_uat_refresh_network_failure_preserves(mock_post):
    # 模拟网络链接超时
    mock_post.side_effect = httpx.ConnectTimeout("Connect timeout")
    
    open_id = "usr_net_err"
    old_uat = "exp_uat"
    
    with patch.dict(os.environ, {"FEISHU_APP_ID": "mock_app", "FEISHU_APP_SECRET": "mock_secret"}):
        save_uat(open_id, old_uat, "refresh_xyz", time.time() + 120, [], "Exp User")
        
        token = get_uat(open_id)
        assert token is None  # 刷新失败但返回 None，保留原始记录以防瞬时网络抖动
        
        # 验证本地记录依然存在，未被强删
        from tools.uat_store import _read_store
        store = _read_store()
        assert open_id in store
        assert store[open_id]["user_access_token"] == old_uat


@pytest.fixture
def mock_psycopg_env():
    import sys
    import tools.uat_store
    tools.uat_store._pg_initialized = False
    
    mock_psycopg = MagicMock()
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value.__enter__.return_value = mock_cur
    mock_psycopg.connect.return_value.__enter__.return_value = mock_conn
    
    with patch.dict(sys.modules, {"psycopg": mock_psycopg}):
        yield mock_psycopg, mock_conn, mock_cur
        
    tools.uat_store._pg_initialized = False


def test_save_uat_postgres(mock_psycopg_env):
    mock_psycopg, mock_conn, mock_cur = mock_psycopg_env
    
    open_id = "pg_usr_123"
    uat = "pg_token"
    refresh = "pg_refresh"
    expires_at = time.time() + 3600
    
    with patch.dict(os.environ, {"POSTGRES_URI": "postgresql://mock_url"}):
        save_uat(open_id, uat, refresh, expires_at, ["scopes"], "PG User")
        
        # Verify psycopg connect was called (both for ensure_pg_table and for insert)
        mock_psycopg.connect.assert_any_call("postgresql://mock_url", autocommit=True)
        mock_psycopg.connect.assert_any_call("postgresql://mock_url")
        
        # Verify table check and insert execute
        execute_calls = mock_cur.execute.call_args_list
        assert len(execute_calls) >= 2
        # First execute should contain CREATE TABLE IF NOT EXISTS
        assert "CREATE TABLE IF NOT EXISTS" in execute_calls[0][0][0]
        # Second execute should contain INSERT INTO lark_uat_tokens
        assert "INSERT INTO lark_uat_tokens" in execute_calls[1][0][0]
        assert execute_calls[1][0][1] == (open_id, uat, refresh, expires_at, ["scopes"], "PG User")


def test_get_uat_postgres_fresh(mock_psycopg_env):
    mock_psycopg, mock_conn, mock_cur = mock_psycopg_env
    
    open_id = "pg_usr_456"
    uat = "pg_token_fresh"
    refresh = "pg_refresh_fresh"
    expires_at = time.time() + 3600  # fresh, > 10 min
    
    # Mock row returned by fetchone
    mock_cur.fetchone.return_value = (uat, refresh, expires_at, ["scopes"], "PG User Fresh")
    
    with patch.dict(os.environ, {"POSTGRES_URI": "postgresql://mock_url"}):
        retrieved = get_uat(open_id)
        assert retrieved == uat
        
        # Verify select execute
        execute_calls = mock_cur.execute.call_args_list
        assert len(execute_calls) >= 2
        assert "SELECT user_access_token" in execute_calls[1][0][0]
        assert execute_calls[1][0][1] == (open_id,)


@patch("tools.uat_store._refresh_user_token")
def test_get_uat_postgres_expired_refresh_success(mock_refresh, mock_psycopg_env):
    mock_psycopg, mock_conn, mock_cur = mock_psycopg_env
    
    open_id = "pg_usr_exp"
    uat = "pg_token_exp"
    refresh = "pg_refresh_exp"
    expires_at = time.time() + 100  # expiring in 100 seconds (< 600)
    
    new_uat = "pg_token_new"
    new_refresh = "pg_refresh_new"
    new_expires_at = time.time() + 7200
    
    # Mock database responses
    mock_cur.fetchone.return_value = (uat, refresh, expires_at, ["scopes"], "PG User Exp")
    mock_refresh.return_value = {
        "user_access_token": new_uat,
        "refresh_token": new_refresh,
        "expires_at": new_expires_at
    }
    
    with patch.dict(os.environ, {"POSTGRES_URI": "postgresql://mock_url"}):
        retrieved = get_uat(open_id)
        assert retrieved == new_uat
        
        # Verify select, then update
        execute_calls = mock_cur.execute.call_args_list
        assert any("UPDATE lark_uat_tokens" in call[0][0] for call in execute_calls)
        
        # Find the update call and check parameters
        update_call = [call for call in execute_calls if "UPDATE lark_uat_tokens" in call[0][0]][0]
        assert update_call[0][1] == (new_uat, new_refresh, new_expires_at, open_id)


@patch("tools.uat_store._refresh_user_token")
def test_get_uat_postgres_expired_refresh_invalid_delete(mock_refresh, mock_psycopg_env):
    from tools.uat_store import TokenInvalidError
    mock_psycopg, mock_conn, mock_cur = mock_psycopg_env
    
    open_id = "pg_usr_invalid"
    uat = "pg_token_invalid"
    refresh = "pg_refresh_invalid"
    expires_at = time.time() + 100
    
    # Mock database responses
    mock_cur.fetchone.return_value = (uat, refresh, expires_at, ["scopes"], "PG User Invalid")
    mock_refresh.side_effect = TokenInvalidError("Invalid refresh token")
    
    with patch.dict(os.environ, {"POSTGRES_URI": "postgresql://mock_url"}):
        retrieved = get_uat(open_id)
        assert retrieved is None
        
        # Verify select, then delete
        execute_calls = mock_cur.execute.call_args_list
        assert any("DELETE FROM lark_uat_tokens" in call[0][0] for call in execute_calls)
        
        delete_call = [call for call in execute_calls if "DELETE FROM lark_uat_tokens" in call[0][0]][0]
        assert delete_call[0][1] == (open_id,)
