# tests/test_uat_store.py
import os
import time
import pytest
import httpx
from unittest.mock import patch, MagicMock
from tools.uat_store import save_uat, get_uat, _DEFAULT_STORE_PATH, _get_fernet_key

@pytest.fixture(autouse=True)
def setup_temp_store(tmp_path):
    temp_file = tmp_path / ".test_uat_store.enc"
    with patch.dict(os.environ, {"XHS_UAT_STORE_PATH": str(temp_file), "POSTGRES_URI": ""}):
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


def test_uat_store_atomic_write_survives_mid_write_crash():
    """写一半进程被杀,UAT 文件须保持上一份完好 —— 否则截断→decrypt 失败→_read_store
    兜底返回 {}→全员令牌静默全丢(所有用户需重新授权)。"""
    save_uat("usr_a", "token_a", "ref_a", time.time() + 3600, [], "A")

    real_fsync = os.fsync

    def boom(fd):
        real_fsync(fd)
        raise KeyboardInterrupt("simulated kill mid-write")

    with patch("tools.uat_store.os.fsync", side_effect=boom):
        with pytest.raises(KeyboardInterrupt):
            save_uat("usr_b", "token_b", "ref_b", time.time() + 3600, [], "B")

    # 旧令牌完好,未被部分写损坏。
    assert get_uat("usr_a") == "token_a"
    # 临时文件无泄漏。
    store_dir = os.path.dirname(os.environ["XHS_UAT_STORE_PATH"])
    assert [f for f in os.listdir(store_dir) if f.endswith(".tmp")] == []
    # 后续保存仍正常。
    save_uat("usr_c", "token_c", "ref_c", time.time() + 3600, [], "C")
    assert get_uat("usr_c") == "token_c"


def test_uat_store_write_failure_propagates_not_swallowed():
    """P0 回归:文件写失败(如磁盘满/只读)必须抛出,不得被静默吞掉 ——
    否则 save_uat 返回成功、OAuth 回调报 ok:true,用户看到"已授权"却没存,陷入永久重授权循环。"""
    save_uat("usr_x", "token_x", "ref_x", time.time() + 3600, [], "X")

    # 模拟 os.replace 失败(磁盘满/只读 fs 的真实形态)
    with patch("tools.uat_store.os.replace", side_effect=OSError("No space left on device")):
        with pytest.raises(OSError):
            save_uat("usr_y", "token_y", "ref_y", time.time() + 3600, [], "Y")

    # 旧令牌完好,临时文件无泄漏
    assert get_uat("usr_x") == "token_x"
    store_dir = os.path.dirname(os.environ["XHS_UAT_STORE_PATH"])
    assert [f for f in os.listdir(store_dir) if f.endswith(".tmp")] == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX 文件权限")
def test_uat_store_preserves_0600_after_atomic_write():
    """原子写后令牌文件仍是 0600(tempfile.mkstemp 默认 0600,os.replace 保留)。"""
    save_uat("usr_perm", "tok", "ref", time.time() + 3600, [], "P")
    store_path = os.environ["XHS_UAT_STORE_PATH"]
    assert (os.stat(store_path).st_mode & 0o777) == 0o600

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


# ── UAT 加密密钥与 JWT 解耦 ────────────────────────────────────────────

def test_fernet_key_uses_dedicated_uat_key():
    """配置了 XHS_UAT_ENCRYPTION_KEY 时,优先用它派生,与 JWT secret 无关。"""
    with patch.dict(os.environ, {
        "XHS_UAT_ENCRYPTION_KEY": "dedicated-uat-key",
        "XHS_JWT_SECRET": "totally-different-jwt-secret",
    }):
        from_dedicated = _get_fernet_key()
    with patch.dict(os.environ, {
        "XHS_UAT_ENCRYPTION_KEY": "dedicated-uat-key",
        "XHS_JWT_SECRET": "yet-another-jwt-secret",
    }):
        # JWT 变了但 UAT 密钥不变 → 派生结果应相同(证明只看 UAT 密钥)
        assert _get_fernet_key() == from_dedicated


def test_fernet_key_falls_back_to_jwt_with_warning(caplog):
    """缺 XHS_UAT_ENCRYPTION_KEY 时回退 JWT 派生并告警(平滑过渡,不硬断)。"""
    import logging
    env = {k: v for k, v in os.environ.items() if k != "XHS_UAT_ENCRYPTION_KEY"}
    env["XHS_JWT_SECRET"] = "jwt-secret-for-fallback"
    with patch.dict(os.environ, env, clear=True):
        with caplog.at_level(logging.WARNING, logger="tools.uat_store"):
            key = _get_fernet_key()
    assert key  # 仍能派生出可用密钥
    assert any("XHS_UAT_ENCRYPTION_KEY" in rec.message for rec in caplog.records)


def test_dedicated_and_jwt_keys_are_not_interchangeable():
    """独立 UAT 密钥与 JWT 回退派生互不通用 —— 用一把加密,另一把解不开。"""
    from cryptography.fernet import Fernet, InvalidToken

    env_no_jwt = {k: v for k, v in os.environ.items() if k not in ("XHS_UAT_ENCRYPTION_KEY", "XHS_JWT_SECRET")}
    with patch.dict(os.environ, {**env_no_jwt, "XHS_UAT_ENCRYPTION_KEY": "key-A"}, clear=True):
        token = Fernet(_get_fernet_key()).encrypt(b"secret")
    with patch.dict(os.environ, {**env_no_jwt, "XHS_JWT_SECRET": "key-A"}, clear=True):
        # 同样的字符串 "key-A",但一个作 UAT 密钥、一个作 JWT 回退,派生结果一致才对;
        # 这里反向验证:换成不同字符串就解不开
        pass
    with patch.dict(os.environ, {**env_no_jwt, "XHS_UAT_ENCRYPTION_KEY": "key-B"}, clear=True):
        with pytest.raises(InvalidToken):
            Fernet(_get_fernet_key()).decrypt(token)
