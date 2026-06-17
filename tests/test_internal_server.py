# tests/test_internal_server.py
import os
import json
import hmac
import hashlib
import pytest
import httpx
from unittest.mock import patch
from tools.internal_server import start_internal_server

@pytest.fixture(scope="module")
def running_server():
    with patch.dict(os.environ, {"XHS_JWT_SECRET": "secret_key", "XHS_INTERNAL_PORT": "9090"}):
        server = start_internal_server()
        yield server
        if server:
            server.shutdown()

def test_unauthorized_post(running_server):
    resp = httpx.post("http://127.0.0.1:9090/_internal/uat", content=b"{}")
    assert resp.status_code == 401

def test_signature_mismatch(running_server):
    headers = {"Authorization": "HMAC badsig"}
    body = json.dumps({
        "open_id": "usr_999",
        "uat": "uat_xxx",
        "refresh_token": "ref_xxx",
        "expires_at": 1800000000,
        "scopes": [],
        "name": "Sync User"
    }).encode("utf-8")
    resp = httpx.post("http://127.0.0.1:9090/_internal/uat", content=body, headers=headers)
    assert resp.status_code == 403

def test_authorized_post(running_server):
    body = json.dumps({
        "open_id": "usr_999",
        "uat": "uat_xxx",
        "refresh_token": "ref_xxx",
        "expires_at": 1800000000,
        "scopes": [],
        "name": "Sync User"
    }).encode("utf-8")
    
    # Sign using the plain text format
    sign_text = "usr_999:uat_xxx:ref_xxx:1800000000"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {"Authorization": f"HMAC {sig}"}
    
    with patch("tools.internal_server.save_uat") as mock_save:
        resp = httpx.post("http://127.0.0.1:9090/_internal/uat", content=body, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_save.assert_called_once_with("usr_999", "uat_xxx", "ref_xxx", 1800000000, [], "Sync User")
