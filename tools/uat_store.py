# tools/uat_store.py
import os
import json
import base64
import tempfile
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
    # UAT 加密密钥与 JWT 签名密钥必须解耦:JWT 泄露不应等于全员飞书令牌可解密。
    # 优先用独立的 XHS_UAT_ENCRYPTION_KEY;仅当其缺失时,回退到 XHS_JWT_SECRET 派生
    # (平滑过渡,不硬断),并告警提示运维配置独立密钥。
    secret = os.environ.get("XHS_UAT_ENCRYPTION_KEY", "").strip()
    if not secret:
        secret = os.environ.get("XHS_JWT_SECRET", "default_fallback_secret_for_key_derivation_32bytes")
        logger.warning(
            "XHS_UAT_ENCRYPTION_KEY is not set; falling back to deriving the UAT encryption "
            "key from XHS_JWT_SECRET. Configure a dedicated XHS_UAT_ENCRYPTION_KEY so that a "
            "JWT secret leak cannot also decrypt stored Feishu user tokens."
        )
    # Derive a 32-byte key using SHA-256 and base64 urlsafe encode
    derived = hashlib.sha256(secret.encode()).digest()
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

        # 原子写:同目录临时文件 + fsync + os.replace 原子 rename。直接 O_TRUNC 覆写非原子,
        # 写一半进程被杀会把文件截断,下次 _read_store 的 decrypt 抛异常 → 兜底返回 {} →
        # 全员 UAT 静默全丢(所有用户需重新授权,且无报错)。os.replace 在同一文件系统原子,
        # 任一时刻读到的要么完整旧文件、要么完整新文件。
        # tempfile.mkstemp 默认即 0600,正好满足令牌文件的权限要求(rename 保留该权限)。
        store_dir = os.path.dirname(store_path) or "."
        fd, tmp_name = tempfile.mkstemp(dir=store_dir, prefix=".uat_store.", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fp:
                fp.write(encrypted_data)
                fp.flush()
                os.fsync(fp.fileno())
            os.replace(tmp_name, store_path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
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
        # 安全:OAuth token 端点的响应体(含错误体)可能回带 access_token/refresh_token,
        # 一律不打印 resp.text / data —— 只记状态码与错误类型(守 CLAUDE.md「日志不得打印 token」)。
        if resp.status_code == 400:
            logger.error("Feishu OAuth explicitly rejected refresh token for user %s (status 400)", open_id)
            raise TokenInvalidError("Refresh token is invalid or expired.")

        if resp.status_code != 200:
            logger.error("Feishu refresh token API returned status %s for user %s", resp.status_code, open_id)
            return None

        data = resp.json()
        uat = data.get("access_token")
        new_refresh = data.get("refresh_token")
        expires_in = data.get("expires_in", 7200)
        if not uat or not new_refresh:
            logger.error(
                "Feishu refresh token response missing access_token/refresh_token for user %s", open_id
            )
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

def _refresh_uat_pg_locked(postgres_uri: str, open_id: str) -> str | None:
    """在行锁内刷新 PG 里的 UAT,消除并发刷新竞态。

    P2 竞态:两个并发 get_uat 同时见到临期 → 都去 refresh;第一个成功并轮换了 refresh_token,
    第二个拿已失效的旧 refresh_token → 飞书返 400 → TokenInvalidError → **删掉第一个刚刷好的记录**。
    解法:SELECT ... FOR UPDATE 串行化同一 open_id 的刷新;拿到锁后 **重读** —— 若已被别的 worker
    刷新过(expiry 已远),直接复用,不再重复刷新(也就不会用旧 refresh_token 触发误删)。
    """
    import psycopg
    with psycopg.connect(postgres_uri) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_access_token, refresh_token, expires_at
                FROM lark_uat_tokens WHERE open_id = %s FOR UPDATE;
                """,
                (open_id,),
            )
            row = cur.fetchone()
            if not row:
                return None  # 已被并发删除
            access_token, refresh_token, expires_at = row[0], row[1], row[2]

            # 双检:拿锁期间可能已有 worker 刷新过,此时直接复用,避免用旧 refresh_token 二次刷新。
            if expires_at - time.time() >= 600:
                return access_token

            try:
                refreshed = _refresh_user_token(open_id, refresh_token)
            except TokenInvalidError:
                logger.warning(f"OAuth refresh token invalid for user {open_id}. Deleting database token record.")
                cur.execute("DELETE FROM lark_uat_tokens WHERE open_id = %s;", (open_id,))
                return None

            if not refreshed:
                logger.warning(f"Failed to refresh database token for user {open_id} due to network issues. Preserving record.")
                return None

            cur.execute(
                """
                UPDATE lark_uat_tokens
                SET user_access_token = %s, refresh_token = %s, expires_at = %s, updated_at = CURRENT_TIMESTAMP
                WHERE open_id = %s;
                """,
                (refreshed["user_access_token"], refreshed["refresh_token"], refreshed["expires_at"], open_id),
            )
            logger.info(f"Database token for user {open_id} successfully refreshed in PostgreSQL.")
            return refreshed["user_access_token"]


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
                return _refresh_uat_pg_locked(postgres_uri, open_id)
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
