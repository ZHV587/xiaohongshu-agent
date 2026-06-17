# tools/uat_store.py
import os
import json
import base64
import time
import hmac
import hashlib
import logging
import threading
import httpx
from cryptography.fernet import Fernet
from pathlib import Path

logger = logging.getLogger(__name__)

# Lock for multi-threaded access to the local storage file
_store_lock = threading.Lock()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_STORE_PATH = _PROJECT_ROOT / ".uat_store.enc"

def _get_fernet_key() -> bytes:
    jwt_secret = os.environ.get("XHS_JWT_SECRET", "default_fallback_secret_for_key_derivation_32bytes")
    # Derive a 32-byte key using SHA-256 and base64 urlsafe encode
    derived = hashlib.sha256(jwt_secret.encode()).digest()
    return base64.urlsafe_b64encode(derived)

def _read_store() -> dict:
    store_path = os.environ.get("XHS_UAT_STORE_PATH", str(_DEFAULT_STORE_PATH))
    if not os.path.exists(store_path):
        return {}
    try:
        f = Fernet(_get_fernet_key())
        with open(store_path, "rb") as fp:
            encrypted_data = fp.read()
        if not encrypted_data:
            return {}
        decrypted_data = f.decrypt(encrypted_data)
        return json.loads(decrypted_data.decode("utf-8"))
    except Exception as e:
        logger.error(f"Error reading token storage: {e}")
        return {}

def _write_store(data: dict) -> None:
    store_path = os.environ.get("XHS_UAT_STORE_PATH", str(_DEFAULT_STORE_PATH))
    try:
        f = Fernet(_get_fernet_key())
        serialized = json.dumps(data).encode("utf-8")
        encrypted_data = f.encrypt(serialized)
        
        # Enforce 0600 file permissions on Unix-like OS (or simple write on Windows)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        # Check OS compatibility
        if os.name != 'nt':
            fd = os.open(store_path, flags, mode)
            with os.fdopen(fd, 'wb') as fp:
                fp.write(encrypted_data)
        else:
            with open(store_path, "wb") as fp:
                fp.write(encrypted_data)
    except Exception as e:
        logger.error(f"Error writing token storage: {e}")

def save_uat(open_id: str, uat: str, refresh_token: str, expires_at: float, scopes: list, name: str) -> None:
    with _store_lock:
        store = _read_store()
        store[open_id] = {
            "user_access_token": uat,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "scopes": scopes,
            "name": name
        }
        _write_store(store)

def _refresh_user_token(open_id: str, refresh_token: str) -> dict | None:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        logger.error("Missing FEISHU_APP_ID or FEISHU_APP_SECRET during token refresh.")
        return None
        
    url = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
    try:
        resp = httpx.post(url, json={
            "grant_type": "refresh_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "refresh_token": refresh_token
        }, timeout=15)
        if resp.status_code != 200:
            logger.error(f"Feishu refresh token API returned status {resp.status_code}: {resp.text}")
            return None
        data = resp.json()
        uat = data.get("access_token")
        new_refresh = data.get("refresh_token")
        expires_in = data.get("expires_in", 7200)
        if not uat or not new_refresh:
            logger.error(f"Feishu refresh token response invalid: {data}")
            return None
        return {
            "user_access_token": uat,
            "refresh_token": new_refresh,
            "expires_at": time.time() + expires_in
        }
    except Exception as e:
        logger.error(f"Failed to call Feishu refresh token API: {e}")
        return None

def get_uat(open_id: str) -> str | None:
    with _store_lock:
        store = _read_store()
    user_data = store.get(open_id)
    if not user_data:
        return None
        
    # Check if the token expires in less than 10 minutes
    if user_data["expires_at"] - time.time() < 600:
        logger.info(f"Token for user {open_id} expiring soon. Attempting refresh...")
        refreshed = _refresh_user_token(open_id, user_data["refresh_token"])
        if refreshed:
            user_data.update(refreshed)
            with _store_lock:
                store = _read_store()
                store[open_id] = user_data
                _write_store(store)
            logger.info(f"Token for user {open_id} successfully refreshed.")
            return user_data["user_access_token"]
        else:
            logger.warning(f"Failed to refresh token for user {open_id}. Deleting token from store.")
            with _store_lock:
                store = _read_store()
                if open_id in store:
                    del store[open_id]
                    _write_store(store)
            return None
            
    return user_data["user_access_token"]
