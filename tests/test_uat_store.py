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
