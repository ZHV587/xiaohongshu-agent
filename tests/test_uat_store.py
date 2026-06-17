# tests/test_uat_store.py
import os
import time
import pytest
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
