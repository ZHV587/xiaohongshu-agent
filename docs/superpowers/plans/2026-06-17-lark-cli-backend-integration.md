# Lark CLI Backend Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the complete backend integration of `lark-cli` with user OAuth workflow: securely encrypted local token storage, automated access token refreshing, a secure local HMAC-signed callback route, dynamic user/bot session environment injection, and interactive write confirmation (HITL).

**Architecture:** 
1. Next.js auth callback receives user access token & refresh token, signs a normalized plain-text token payload with HMAC-SHA256, and posts it to a python-based localhost HTTP server.
2. Python internal HTTP server verifies the HMAC signature using the same normalized structure and writes the tokens to a locally encrypted storage (`.uat_store.enc`) protected by `cryptography.fernet`.
3. The `lark_cli` tool intercepts user commands, queries the encrypted storage via the caller's thread identity, automatically refreshes expired user tokens, and executes the CLI securely via `shell=False` with dynamic environment variables.
4. Interaction confirmation (exit code 10) prompts the LLM to request user confirmation, repeating with `yes=True` upon approval.

**Tech Stack:** Python 3.11, Next.js (Node.js), LangGraph SDK, `cryptography` library.

---

## Proposed Changes

### Task 1: Install `cryptography` Library

**Files:**
- Modify: [pyproject.toml](file:///e:/小红书智能体/pyproject.toml)

- [x] **Step 1: Add cryptography to dependencies**

Modify [pyproject.toml](file:///e:/小红书智能体/pyproject.toml) to append `"cryptography>=42.0.0,<43.0.0"` in `dependencies`.
```toml
dependencies = [
    "deepagents>=0.6.8,<1.0.0",
    "langchain>=1.3.9,<2.0.0",
    "langchain-anthropic>=1.4.6,<2.0.0",
    "langgraph-cli[inmem]>=0.2.0,<1.0.0",
    "langgraph-sdk>=0.1.0,<1.0.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.1",
    "rich>=15.0.0",
    "cryptography>=42.0.0,<43.0.0",
]
```

- [x] **Step 2: Install the dependency**

Run: `uv pip install -e .` or `pip install -e .`
Expected: Dependencies are successfully resolved and installed.

- [x] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add cryptography dependency for secure token storage"
```

---

### Task 2: Define Full Lark Scopes List

**Files:**
- Create: [tools/lark_scopes.py](file:///e:/小红书智能体/tools/lark_scopes.py)

- [x] **Step 1: Create lark_scopes.py**

Create a clean definition of required scopes that matches both Python skills and Next.js authorize endpoints.
```python
# tools/lark_scopes.py

# A curated set of scopes needed for im, base, drive, task, and calendar domains.
LARK_SCOPES = [
    "im:message",
    "im:message.send_as_user",
    "im:chat",
    "im:chat.members:read",
    "base:form:update",
    "drive:drive",
    "drive:file:download",
    "drive:file:upload",
    "task:task:read",
    "task:task:write",
    "calendar:calendar:read",
    "calendar:calendar.event:create",
]
```

- [x] **Step 2: Commit**

```bash
git add tools/lark_scopes.py
git commit -m "feat: define Lark OAuth scopes constants"
```

---

### Task 3: Implement UAT Encrypted Storage Layer

**Files:**
- Create: [tools/uat_store.py](file:///e:/小红书智能体/tools/uat_store.py)
- Create: [tests/test_uat_store.py](file:///e:/小红书智能体/tests/test_uat_store.py)

- [x] **Step 1: Implement UAT encrypted storage logic**

Write `tools/uat_store.py` to encrypt/decrypt using `cryptography.fernet.Fernet` derived from `XHS_JWT_SECRET`. Include automated refresh using Feishu OAuth `/authen/v2/oauth/token` API.
```python
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
```

- [x] **Step 2: Create UAT store unit tests**

Write `tests/test_uat_store.py` verifying file locking, encryption, serialization, and mocks of the refresh token API.
```python
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
```

- [x] **Step 3: Run UAT storage tests**

Run: `pytest tests/test_uat_store.py -v`
Expected: Tests pass successfully.

- [x] **Step 4: Commit**

```bash
git add tools/uat_store.py tests/test_uat_store.py
git commit -m "feat: implement encrypted UAT storage and test suites"
```

---

### Task 4: Implement Python Internal HTTP Server for OAuth Callbacks

**Files:**
- Create: [tools/internal_server.py](file:///e:/小红书智能体/tools/internal_server.py)
- Modify: [agent.py](file:///e:/小红书智能体/agent.py)
- Create: [tests/test_internal_server.py](file:///e:/小红书智能体/tests/test_internal_server.py)

- [x] **Step 1: Write the internal HTTP server**

Create `tools/internal_server.py`. It runs a lightweight `http.server.HTTPServer` on port `8081` in a background daemon thread, listening only on `127.0.0.1`. It parses JSON bodies and requires an HMAC-SHA256 signature calculated with `XHS_JWT_SECRET` in the `Authorization` header (`HMAC <hex_signature>`). The signature payload is built using a strict plain-text format: `"{open_id}:{uat}:{refresh_token}:{int(expires_at)}"` to avoid differences in JSON key ordering or space padding between TS and Python.
```python
# tools/internal_server.py
import os
import json
import hmac
import hashlib
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from tools.uat_store import save_uat

logger = logging.getLogger(__name__)

class InternalUATHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path != "/_internal/uat":
            self.send_response(404)
            self.end_headers()
            return

        # 1) HMAC authentication check
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("HMAC "):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized: Missing HMAC signature.")
            return
            
        client_sig = auth_header[5:].strip()
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        jwt_secret = os.environ.get("XHS_JWT_SECRET", "")
        if not jwt_secret:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal server misconfiguration: missing secret.")
            return

        try:
            payload = json.loads(body.decode("utf-8"))
            open_id = payload["open_id"]
            uat = payload["uat"]
            refresh_token = payload["refresh_token"]
            expires_at = int(payload["expires_at"])
            scopes = payload.get("scopes", [])
            name = payload.get("name", "")
            
            # Construct signature base exactly matches TypeScript's structure
            sign_text = f"{open_id}:{uat}:{refresh_token}:{expires_at}"
            expected_sig = hmac.new(
                jwt_secret.encode("utf-8"),
                sign_text.encode("utf-8"),
                hashlib.sha256
            ).hexdigest()
        except Exception as e:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Bad Request: Failed to parse body or construct signature: {e}".encode("utf-8"))
            return

        if not hmac.compare_digest(expected_sig, client_sig):
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b"Forbidden: Signature validation failed.")
            return

        # 2) Save UAT
        try:
            save_uat(open_id, uat, refresh_token, expires_at, scopes, name)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
        except Exception as e:
            logger.error(f"Error saving UAT: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

def start_internal_server():
    port = int(os.environ.get("XHS_INTERNAL_PORT", 8081))
    try:
        server = HTTPServer(("127.0.0.1", port), InternalUATHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info(f"Started local internal UAT synchronization HTTP server on 127.0.0.1:{port}")
        return server
    except OSError as e:
        logger.error(f"Failed to start internal UAT HTTP server on port {port}: {e}. Next.js OAuth callbacks will not sync UAT tokens.")
        return None
```

- [x] **Step 2: Start server during agent startup**

Modify [agent.py](file:///e:/小红书智能体/agent.py) to launch this HTTP server on import (same way CLI background update triggers).
```python
# In agent.py, import and start internal server:
from tools.internal_server import start_internal_server
# ...
auto_update_lark_skills()
auto_update_lark_cli()
start_internal_server()
```

- [x] **Step 3: Write tests for internal HTTP server**

Create `tests/test_internal_server.py` to assert correct HMAC check and JSON parsing.
```python
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
    resp = httpx.post("http://127.0.0.1:9090/_internal/uat", content=b"{}", headers=headers)
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
```

- [x] **Step 4: Run internal server tests**

Run: `pytest tests/test_internal_server.py -v`
Expected: Tests pass.

- [x] **Step 5: Commit**

```bash
git add tools/internal_server.py agent.py tests/test_internal_server.py
git commit -m "feat: add internal HMAC-authenticated UAT sync server"
```

---

### Task 5: Web OAuth Frontend Callback & Login Scopes Upgrade

**Files:**
- Modify: [web/src/app/api/auth/feishu/login/route.ts](file:///e:/小红书智能体/web/src/app/api/auth/feishu/login/route.ts)
- Modify: [web/src/app/api/auth/feishu/callback/route.ts](file:///e:/小红书智能体/web/src/app/api/auth/feishu/callback/route.ts)

- [x] **Step 1: Inject scopes into Authorize URL**

Modify `web/src/app/api/auth/feishu/login/route.ts` to add the scopes.
```typescript
  const authorizeUrl = new URL(FEISHU_AUTHORIZE_URL);
  authorizeUrl.searchParams.set("client_id", cfg.appId);
  authorizeUrl.searchParams.set("redirect_uri", cfg.redirectUri);
  authorizeUrl.searchParams.set("response_type", "code");
  authorizeUrl.searchParams.set("state", state);
  
  // Defined scopes
  const scopes = [
    "im:message",
    "im:message.send_as_user",
    "im:chat",
    "im:chat.members:read",
    "base:form:update",
    "drive:drive",
    "drive:file:download",
    "drive:file:upload",
    "task:task:read",
    "task:task:write",
    "calendar:calendar:read",
    "calendar:calendar.event:create",
  ];
  authorizeUrl.searchParams.set("scope", scopes.join(" "));
```

- [x] **Step 2: Sign and forward UAT on authorization callback**

Modify `web/src/app/api/auth/feishu/callback/route.ts` to capture the UAT, token scopes, refresh token, and expires_in, sign it using the plain text format, and forward it to Python's internal server.
```typescript
  // In callback/route.ts, capture full tokenData object
  let userToken: string;
  let refreshToken: string;
  let expiresIn: number;
  
  try {
    const tokenResp = await fetch(FEISHU_TOKEN_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify({
        grant_type: "authorization_code",
        client_id: cfg.appId,
        client_secret: cfg.appSecret,
        code,
        redirect_uri: cfg.redirectUri,
      }),
    });
    const tokenData = await tokenResp.json();
    userToken = tokenData.access_token ?? tokenData?.data?.access_token;
    refreshToken = tokenData.refresh_token ?? tokenData?.data?.refresh_token;
    expiresIn = tokenData.expires_in ?? tokenData?.data?.expires_in ?? 7200;
    
    if (!userToken || !refreshToken) {
      return fail(
        req,
        `换取 token 失败：${tokenData.error_description ?? tokenData.msg ?? "未知错误"}`
      );
    }
  } catch {
    return fail(req, "换取 token 请求异常");
  }

  // Fetch user info
  let openId: string;
  let name: string | undefined;
  try {
    const infoResp = await fetch(FEISHU_USER_INFO_URL, {
      headers: { Authorization: `Bearer ${userToken}` },
    });
    const infoData = await infoResp.json();
    const data = infoData.data ?? infoData;
    openId = data.open_id ?? data.union_id;
    name = data.name;
    if (!openId) {
      return fail(req, `获取用户信息失败：${infoData.msg ?? "无 open_id"}`);
    }
  } catch {
    return fail(req, "获取用户信息请求异常");
  }

  // ── Sync to Python UAT storage using HMAC signature ──────────
  try {
    const expiresAt = Math.floor(Date.now() / 1000 + expiresIn);
    const bodyObj = {
      open_id: openId,
      uat: userToken,
      refresh_token: refreshToken,
      expires_at: expiresAt,
      scopes: tokenData.scope ? tokenData.scope.split(" ") : [],
      name: name || openId
    };
    
    const bodyStr = JSON.stringify(bodyObj);
    const signText = `${openId}:${userToken}:${refreshToken}:${expiresAt}`;
    
    const crypto = await import("node:crypto");
    const signature = crypto
      .createHmac("sha256", cfg.jwtSecret)
      .update(signText)
      .digest("hex");

    const internalPort = process.env.XHS_INTERNAL_PORT || "8081";
    const syncResp = await fetch(`http://127.0.0.1:${internalPort}/_internal/uat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `HMAC ${signature}`
      },
      body: bodyStr
    });
    
    if (!syncResp.ok) {
      const errMsg = await syncResp.text();
      console.error(`UAT sync to python internal server failed: ${errMsg}`);
    }
  } catch (e) {
    console.error("Exception during UAT sync post to Python:", e);
  }
```

- [x] **Step 3: Commit**

```bash
git add web/src/app/api/auth/feishu/login/route.ts web/src/app/api/auth/feishu/callback/route.ts
git commit -m "feat: upgrade login scopes and post UAT on auth callback"
```

---

### Task 6: Refactor Lark CLI Subprocess execution & Security Hardening

**Files:**
- Modify: [tools/lark_cli.py](file:///e:/小红书智能体/tools/lark_cli.py)
- Modify: [tests/test_lark_cli.py](file:///e:/小红书智能体/tests/test_lark_cli.py)

- [x] **Step 1: Harden subprocess call & token injection**

Modify `tools/lark_cli.py` to:
- Take arguments: `command: str, yes: bool = False, config: RunnableConfig = None`.
- Read context identity via `config` (if server-driven), fetch token using `get_uat(identity)`.
- Fallback to Bot identity if `--as bot` in arguments or running in CLI mode (no identity).
- Deny commands containing `auth` or `config`.
- Set `shell=False` for security. Dynamically map binary file extensions on Windows (`lark-cli.cmd`).
- Inject token to `LARKSUITE_CLI_USER_ACCESS_TOKEN` / App ID secrets into a clean env.
- Parse stderr/stdout for `exit 10` (write warning) and format human-friendly response prompting for `yes=True`.

```python
# tools/lark_cli.py (Modified segment)
import os
import shlex
import subprocess
import logging
import platform
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from tools.uat_store import get_uat

logger = logging.getLogger(__name__)

# BLACKLIST of subcommands to prevent security tampering
_BLACKLIST_COMMANDS = {"auth", "config"}

@tool
def lark_cli(command: str, yes: bool = False, config: RunnableConfig = None) -> str:
    """运行飞书官方命令行工具 (Lark Suite CLI) 的具体指令。
    
    你可以通过它操作飞书日历、即时通讯(发送消息)、云文档、多维表格等业务。
    注意：
    1. 传入参数 command 中不要包含 'lark-cli' 的前缀，只写具体服务 and 子命令。
    2. 对于写操作（例如发送消息、创建会议），需要用户二次确认。如果返回“需要确认”提示，
       你必须用自然语言向用户表述风险，在用户确认同意后，传入 `yes=True` 重新运行该指令。
       
    示例：
    - 发送消息: im +messages-send --chat-id "oc_xxx" --text "文案草稿已写好"
    """
    args = shlex.split(command.strip())
    if not args:
        return "Error: Command cannot be empty."
        
    if args[0] == "lark-cli":
        args = args[1:]
        
    if not args:
        return "Error: Command cannot be empty."

    # 1) Security block blacklist
    sub_cmd = args[0].lower()
    if sub_cmd in _BLACKLIST_COMMANDS:
        return f"Error: Command service '{sub_cmd}' is disallowed for security reasons."

    # 2) Identity resolution
    # Get user identity from runtime config
    server_info = getattr(config, "server_info", None) if config else None
    user = getattr(server_info, "user", None) if server_info else None
    open_id = getattr(user, "identity", None) if user else None
    
    force_bot = False
    clean_args = []
    for arg in args:
        if arg == "--as" and "--as" in args:
            # Look ahead for 'bot'
            idx = args.index("--as")
            if idx + 1 < len(args) and args[idx + 1].lower() == "bot":
                force_bot = True
                # Skip in actual command execution
                continue
        if arg == "bot" and args[args.index(arg) - 1] == "--as":
            continue
        clean_args.append(arg)

    # Resolve token injection
    run_env = {
        "PATH": os.environ.get("PATH", ""),
        "LARKSUITE_CLI_CONTENT_SAFETY_MODE": "warn"
    }
    
    if open_id and not force_bot:
        token = get_uat(open_id)
        if not token:
            return "Please authorize Feishu access first. Please log in again using the UI panel to grant permissions."
        run_env["LARKSUITE_CLI_USER_ACCESS_TOKEN"] = token
        run_env["LARKSUITE_CLI_DEFAULT_AS"] = "user"
    else:
        # CLI fallback or forced bot
        app_id = os.environ.get("FEISHU_APP_ID")
        app_secret = os.environ.get("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            return "Error: Bot credentials (FEISHU_APP_ID/SECRET) not configured."
        run_env["LARKSUITE_CLI_APP_ID"] = app_id
        run_env["LARKSUITE_CLI_APP_SECRET"] = app_secret
        run_env["LARKSUITE_CLI_DEFAULT_AS"] = "app"

    # Append --yes parameter if approved by human
    if yes:
        clean_args.append("--yes")

    # Add output format options if metadata command is not run
    meta_cmds = {"--help", "schema", "--version", "-h"}
    has_meta = any(c in clean_args for c in meta_cmds)
    if not has_meta and "--format" not in clean_args:
        clean_args.extend(["--format", "json"])

    # 3) Execute process
    executable = "lark-cli"
    if platform.system() == "Windows":
        executable = "lark-cli.cmd"

    cmd = [executable] + clean_args
    try:
        result = subprocess.run(
            cmd,
            env=run_env,
            capture_output=True,
            text=True,
            timeout=45,
            shell=False
        )
        
        # 4) Handle exit codes
        if result.returncode == 10:
            # Safety confirmation required
            return (
                "⚠️ [Human-in-the-Loop Required]\n"
                "The requested command requires safety confirmation to execute. Details:\n"
                f"{result.stderr or result.stdout}\n"
                "Please explain the details and risks to the user. Once approved, call the lark_cli tool again with yes=True."
            )
        elif result.returncode == 3:
            # Insufficient scopes / permissions
            return f"Feishu authorization scope insufficient (Exit Code 3). Error message:\n{result.stderr or result.stdout}\nPlease log in to Feishu and grant permissions."
        elif result.returncode != 0:
            return f"Lark CLI command execution failed (Exit Code {result.returncode}):\n{result.stderr or result.stdout}"

        output = result.stdout
        if not output.strip():
            return "Command executed successfully."
        return output[:10000] # Safe crop
        
    except subprocess.TimeoutExpired:
        return "Error: Command execution timed out after 45 seconds."
    except Exception as e:
        return f"Error executing Lark CLI command: {str(e)}"
```

- [x] **Step 2: Update unit tests for CLI**

Update `tests/test_lark_cli.py` to match the new dynamic environment logic, `shell=False` execution, and `exit 10` intercept mocks.
```python
# In tests/test_lark_cli.py
# Modify assertions to support shell=False, executable resolving, blacklists, and context open_id

import subprocess
import pytest
from unittest.mock import patch, MagicMock
from tools.lark_cli import lark_cli

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_blacklist(mock_run):
    res = lark_cli.func("auth status")
    assert "disallowed" in res
    mock_run.assert_not_called()

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_exit_10_confirmation(mock_run):
    mock_resp = MagicMock()
    mock_resp.returncode = 10
    mock_resp.stderr = "Write warning: sending message"
    mock_run.return_value = mock_resp
    
    res = lark_cli.func("im +messages-send --chat-id 1", yes=False)
    assert "Human-in-the-Loop Required" in res
```

- [x] **Step 3: Run full Lark CLI tests**

Run: `pytest tests/test_lark_cli.py -v`
Expected: Tests pass.

- [x] **Step 4: Commit**

```bash
git add tools/lark_cli.py tests/test_lark_cli.py
git commit -m "refactor: harden lark-cli execution and inject token dynamically"
```

---

## Verification Plan

### Automated Tests
Run all unit tests in the repository:
- `pytest -v`

### Manual Verification
1. Run Next.js (`npm run dev`) and LangGraph local server.
2. Open Mockup or main application browser page.
3. Authenticate with Feishu.
4. Verify `.uat_store.enc` file is generated locally, and check that ciphertext does not leak keys.
5. In CLI or browser workspace, request the agent to send a message to Feishu chat:
   - Verify that the agent generates a HITL warning (Exit Code 10) requiring consent.
   - Reply with "确认" / "Confirm".
   - Verify that the message is successfully sent to the Feishu channel.
