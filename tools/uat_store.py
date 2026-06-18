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
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Lock for multi-threaded access to the local storage file
_store_lock = threading.Lock()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")
_DEFAULT_STORE_PATH = _PROJECT_ROOT / ".uat_store.enc"

_pg_initialized = False
_pg_init_lock = threading.Lock()

def _ensure_pg_table() -> None:
    global _pg_initialized
    if _pg_initialized:
        return
    postgres_uri = os.environ.get("POSTGRES_URI")
    if not postgres_uri:
        return
    with _pg_init_lock:
        if _pg_initialized:
            return
        try:
            import psycopg
            with psycopg.connect(postgres_uri, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS lark_uat_tokens (
                            open_id VARCHAR(255) PRIMARY KEY,
                            user_access_token TEXT NOT NULL,
                            refresh_token TEXT NOT NULL,
                            expires_at DOUBLE PRECISION NOT NULL,
                            scopes TEXT[] NOT NULL,
                            name VARCHAR(255) NOT NULL,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
            _pg_initialized = True
            logger.info("Successfully checked/created PostgreSQL lark_uat_tokens table.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL Lark token table: {e}")

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
    postgres_uri = os.environ.get("POSTGRES_URI")
    if postgres_uri:
        _ensure_pg_table()
        try:
            import psycopg
            with psycopg.connect(postgres_uri) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO lark_uat_tokens (open_id, user_access_token, refresh_token, expires_at, scopes, name)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (open_id) DO UPDATE SET
                            user_access_token = EXCLUDED.user_access_token,
                            refresh_token = EXCLUDED.refresh_token,
                            expires_at = EXCLUDED.expires_at,
                            scopes = EXCLUDED.scopes,
                            name = EXCLUDED.name,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (open_id, uat, refresh_token, expires_at, scopes, name))
            logger.info(f"Saved UAT token for user {open_id} to PostgreSQL database.")
            return
        except Exception as e:
            logger.error(f"Failed to save UAT token to PostgreSQL database: {e}. Falling back to file storage.")

    # File storage fallback
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

class TokenInvalidError(Exception):
    """飞书明确拒绝（如 refresh_token 失效或过期）时抛出的异常"""
    pass

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
        
        # 飞书授权失效（如 refresh_token 过期）一般返回 400
        if resp.status_code == 400:
            logger.error(f"Feishu OAuth explicitly rejected refresh token for user {open_id}: {resp.text}")
            raise TokenInvalidError("Refresh token is invalid or expired.")
            
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
    except TokenInvalidError:
        raise
    except Exception as e:
        logger.error(f"Network error or server error during Feishu refresh token API call: {e}")
        return None

def get_uat(open_id: str) -> str | None:
    postgres_uri = os.environ.get("POSTGRES_URI")
    if postgres_uri:
        _ensure_pg_table()
        try:
            import psycopg
            with psycopg.connect(postgres_uri) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT user_access_token, refresh_token, expires_at, scopes, name
                        FROM lark_uat_tokens
                        WHERE open_id = %s;
                    """, (open_id,))
                    row = cur.fetchone()
            
            if not row:
                return None
            
            user_data = {
                "user_access_token": row[0],
                "refresh_token": row[1],
                "expires_at": row[2],
                "scopes": row[3],
                "name": row[4]
            }

            # Check if the token expires in less than 10 minutes
            if user_data["expires_at"] - time.time() < 600:
                logger.info(f"Database token for user {open_id} expiring soon. Attempting refresh...")
                try:
                    refreshed = _refresh_user_token(open_id, user_data["refresh_token"])
                    if refreshed:
                        user_data.update(refreshed)
                        with psycopg.connect(postgres_uri) as conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    UPDATE lark_uat_tokens
                                    SET user_access_token = %s, refresh_token = %s, expires_at = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE open_id = %s;
                                """, (user_data["user_access_token"], user_data["refresh_token"], user_data["expires_at"], open_id))
                        logger.info(f"Database token for user {open_id} successfully refreshed in PostgreSQL.")
                        return user_data["user_access_token"]
                    else:
                        logger.warning(f"Failed to refresh database token for user {open_id} due to network issues. Preserving record.")
                        return None
                except TokenInvalidError:
                    logger.warning(f"OAuth refresh token invalid for user {open_id}. Deleting database token record.")
                    with psycopg.connect(postgres_uri) as conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM lark_uat_tokens WHERE open_id = %s;", (open_id,))
                    return None
            return user_data["user_access_token"]
        except Exception as e:
            logger.error(f"Failed to load UAT token from PostgreSQL database: {e}. Falling back to file storage.")

    # File storage fallback
    with _store_lock:
        store = _read_store()
    user_data = store.get(open_id)
    if not user_data:
        return None
        
    # Check if the token expires in less than 10 minutes
    if user_data["expires_at"] - time.time() < 600:
        logger.info(f"Token for user {open_id} expiring soon. Attempting refresh...")
        try:
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
                logger.warning(f"Failed to refresh token for user {open_id} due to network/server issues. Preserving record.")
                return None
        except TokenInvalidError:
            logger.warning(f"OAuth refresh token invalid for user {open_id}. Deleting token from store.")
            with _store_lock:
                store = _read_store()
                if open_id in store:
                    del store[open_id]
                    _write_store(store)
            return None
            
    return user_data["user_access_token"]
