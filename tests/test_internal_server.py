# tests/test_internal_server.py
import os
import json
import hmac
import hashlib
import time
import pytest
import httpx
from unittest.mock import patch, MagicMock
from tools.internal_server import start_internal_server

@pytest.fixture(scope="module")
def running_server():
    with patch.dict(os.environ, {"XHS_JWT_SECRET": "secret_key", "XHS_INTERNAL_PORT": "9090"}):
        server = start_internal_server()
        yield server
        if server:
            server.shutdown()

def test_status_endpoint(running_server):
    resp = httpx.get("http://127.0.0.1:9090/_internal/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "bot_configured" in data
    assert data["internal_port"] == 9090

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
    
    # 使用纯文本签名格式
    sign_text = "usr_999:uat_xxx:ref_xxx:1800000000"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {"Authorization": f"HMAC {sig}"}
    
    with patch("tools.internal_server.save_uat") as mock_save:
        resp = httpx.post("http://127.0.0.1:9090/_internal/uat", content=body, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_save.assert_called_once_with("usr_999", "uat_xxx", "ref_xxx", 1800000000, [], "Sync User")

def test_authorized_post_missing_refresh_token(running_server):
    body = json.dumps({
        "open_id": "usr_999",
        "uat": "uat_xxx",
        # refresh_token is omitted
        "expires_at": 1800000000,
        "scopes": [],
        "name": "Sync User"
    }).encode("utf-8")
    
    # HMAC expects refresh_token to fall back to empty string
    sign_text = "usr_999:uat_xxx::1800000000"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    headers = {"Authorization": f"HMAC {sig}"}
    
    with patch("tools.internal_server.save_uat") as mock_save:
        resp = httpx.post("http://127.0.0.1:9090/_internal/uat", content=body, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        mock_save.assert_called_once_with("usr_999", "uat_xxx", "", 1800000000, [], "Sync User")

@patch("tools.internal_server.get_uat")
@patch("tools.internal_server.lark_cli")
def test_chats_endpoint_success(mock_lark_cli, mock_get_uat, running_server):
    mock_get_uat.return_value = "mock_user_token"
    
    # 模拟新版飞书群聊列表返回数据
    mock_lark_cli.func.return_value = json.dumps({
        "code": 0,
        "msg": "success",
        "data": {
            "chats": [
                {"chat_id": "oc_chat_1", "name": "露营小组", "chat_mode": "group"},
                {"chat_id": "oc_chat_2", "name": "运营大群", "chat_mode": "group"},
                {"chat_id": "oc_p2p_3", "name": "私聊", "chat_mode": "p2p"}
            ]
        }
    })
    
    open_id = "usr_chats"
    ts = int(time.time())
    
    sign_text = f"{open_id}:{ts}"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    
    headers = {
        "X-Open-ID": open_id,
        "X-Timestamp": str(ts),
        "Authorization": f"HMAC {sig}"
    }
    
    resp = httpx.get("http://127.0.0.1:9090/_internal/chats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert len(data["chats"]) == 2
    assert data["chats"][0]["chat_id"] == "oc_chat_1"
    assert data["chats"][1]["chat_id"] == "oc_chat_2"

@patch("tools.internal_server.get_uat")
@patch("tools.internal_server.lark_cli")
def test_sync_endpoint_success(mock_lark_cli, mock_get_uat, running_server):
    mock_get_uat.return_value = "mock_user_token"
    
    # 1. 模拟新版 Bitable 字段列名列表返回数据
    fields_resp = json.dumps({
        "code": 0,
        "data": {
            "fields": [
                {"id": "fld_title", "name": "文案标题", "type": 1},
                {"id": "fld_body", "name": "笔记正文", "type": 1}
            ]
        }
    })
    
    # 2. 模拟写入多维表格成功返回数据
    update_resp = json.dumps({
        "code": 0,
        "msg": "success"
    })
    
    mock_lark_cli.func.side_effect = [fields_resp, update_resp]
    
    open_id = "usr_sync"
    record_id = "rec_98765"
    title = "露营好物推荐"
    content = "夏天快去露营呀⛺！"
    ts = int(time.time())
    
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    sign_text = f"{open_id}:{record_id}:{content_hash}:{ts}"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    
    body = {
        "open_id": open_id,
        "recordId": record_id,
        "title": title,
        "content": content,
        "timestamp": ts
    }
    
    headers = {"Authorization": f"HMAC {sig}"}
    
    with patch.dict(os.environ, {
        "FEISHU_BITABLE_APP_TOKEN": "bas_mock",
        "FEISHU_BITABLE_TABLE_ID": "tbl_mock"
    }):
        resp = httpx.post("http://127.0.0.1:9090/_internal/sync", json=body, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        
        # 验证是否正确调用了 2 次 CLI
        assert mock_lark_cli.func.call_count == 2
        call_args_list = mock_lark_cli.func.call_args_list
        second_call_cmd = call_args_list[1][0][0] # first arg
        assert "fld_title" in second_call_cmd
        assert "fld_body" in second_call_cmd

@patch("tools.internal_server.get_uat")
@patch("tools.internal_server.lark_cli")
def test_notify_endpoint_success(mock_lark_cli, mock_get_uat, running_server):
    mock_get_uat.return_value = "mock_user_token"
    
    mock_lark_cli.func.return_value = json.dumps({
        "code": 0,
        "msg": "success"
    })
    
    open_id = "usr_notify"
    chat_id = "oc_chat_9876"
    title = "通知标题"
    content = "通知正文内容"
    ts = int(time.time())
    
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    sign_text = f"{open_id}:{chat_id}:{content_hash}:{ts}"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    
    body = {
        "open_id": open_id,
        "chatId": chat_id,
        "title": title,
        "content": content,
        "timestamp": ts
    }
    
    headers = {"Authorization": f"HMAC {sig}"}
    
    resp = httpx.post("http://127.0.0.1:9090/_internal/notify", json=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    mock_lark_cli.func.assert_called_once()

def test_get_config_unauthorized(running_server):
    resp = httpx.get("http://127.0.0.1:9090/_internal/config")
    assert resp.status_code == 401

def test_get_config_success(running_server):
    open_id = "usr_config"
    ts = int(time.time())
    sign_text = f"{open_id}:{ts}"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    
    headers = {
        "X-Open-ID": open_id,
        "X-Timestamp": str(ts),
        "Authorization": f"HMAC {sig}"
    }
    
    with patch.dict(os.environ, {
        "FEISHU_APP_ID": "cli_test_id",
        "FEISHU_APP_SECRET": "test_secret"
    }):
        resp = httpx.get("http://127.0.0.1:9090/_internal/config", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["configs"]["FEISHU_APP_ID"] == "cli_test_id"
        assert data["configs"]["FEISHU_APP_SECRET"] == "test_secret"

def test_post_config_success(running_server):
    configs = {
        "FEISHU_APP_ID": "cli_new_id",
        "FEISHU_APP_SECRET": "new_secret",
        "FEISHU_BITABLE_APP_TOKEN": "new_token",
        "FEISHU_BITABLE_TABLE_ID": "new_table"
    }
    ts = int(time.time())
    configs_str = json.dumps(configs, sort_keys=True, separators=(',', ':'))
    sign_text = f"{configs_str}:{ts}"
    sig = hmac.new(b"secret_key", sign_text.encode("utf-8"), hashlib.sha256).hexdigest()
    
    body = {
        "configs": configs,
        "timestamp": ts
    }
    headers = {"Authorization": f"HMAC {sig}"}
    
    with patch("tools.internal_server._update_env_file") as mock_update_env:
        resp = httpx.post("http://127.0.0.1:9090/_internal/config", json=body, headers=headers)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}
        assert os.environ.get("FEISHU_APP_ID") == "cli_new_id"
        assert os.environ.get("FEISHU_APP_SECRET") == "new_secret"
        mock_update_env.assert_called_once_with(configs)
