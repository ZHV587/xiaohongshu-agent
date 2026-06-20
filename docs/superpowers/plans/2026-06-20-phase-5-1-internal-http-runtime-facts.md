# Phase 5.1 Internal HTTP and Runtime Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Web-to-Python internal operations from per-request `execFile` bridge calls to LangGraph-hosted Starlette internal routes with explicit shared-secret auth, route ACLs, config recovery fallback, and runtime facts.

**Architecture:** `data_foundation/http_app.py` remains the LangGraph `http.app` entry and delegates internal routes to small focused modules. Next.js keeps user/admin cookie auth, forwards internal requests with `XHS_INTERNAL_SECRET`, and uses a config-only degraded fallback when the internal route is unavailable. Config key allowlists are made explicit so Web and Python do not disagree in config-center mode.

**Tech Stack:** Python 3.11, Starlette, pytest, ConfigCenter/Fernet, existing Feishu UAT helpers, Next.js route handlers, TypeScript, pnpm unit tests, LangGraph `http.app`.

---

## Scope

This plan covers Slice A from the Phase 5 spec:

- Starlette internal routes.
- Next internal HTTP client.
- Internal key and route ACL.
- Config read/write parity.
- Config-only break-glass fallback.
- Runtime facts endpoint foundation.
- Web/Python config allowlist convergence.

This plan does not implement:

- The visual administrator status page.
- `agent.py` import side-effect cleanup.
- Retrieval ranking or performance feedback ranking.
- Web chat component splitting.
- Meilisearch, Graphiti, Neo4j/FalkorDB, or Dagster.

## Current Dirty Worktree Warning

Before starting implementation, run:

```bash
git status --short
```

Expected at the time this plan was written:

```text
 M backends.py
 M models.py
 M tests/test_agent_assembly.py
 M tests/test_backends.py
 M tests/test_content_rubric.py
?? tests/test_public_api_contract.py
```

Those files are pre-existing work by another change stream. Do not stage, revert, or rewrite them while implementing this plan unless the user explicitly asks.

## File Structure

Create:

- `data_foundation/internal_api.py`: Starlette request handlers, internal auth helper, config handlers, Feishu handlers, runtime facts handler.
- `tests/data_foundation/test_internal_api.py`: Python route tests for auth, ACL, config behavior, Feishu user routes, and runtime facts.
- `web/tests/internal-client-http.test.ts`: TypeScript unit tests for HTTP forwarding and degraded config fallback behavior.

Modify:

- `data_foundation/http_app.py`: register internal routes from `data_foundation.internal_api`.
- `config_center.py`: expose one canonical editable/deploy-only key contract, including `XHS_INTERNAL_BASE_URL` as deploy-only.
- `tests/test_config_center.py`: cover internal deploy-only keys and runtime apply key behavior in config-center.
- `web/src/lib/server/config-store.ts`: align Web allowlists with Python semantics and expose helper for config-center-supported keys.
- `web/src/lib/server/internal-client.ts`: replace `execFile` production path with HTTP forwarding to `XHS_INTERNAL_BASE_URL`; keep config-only degraded fallback.
- `web/src/app/api/config/route.ts`: handle `degraded: true` and stop treating all apply states as instant reload.
- `web/src/app/api/feishu/status/route.ts`, `web/src/app/api/feishu/chats/route.ts`, `web/src/app/api/feishu/wiki-space/route.ts`, `web/src/app/api/auth/feishu/callback/route.ts`: use the HTTP internal client without changing user-facing behavior.
- `README.md`: update current facts for internal HTTP route and degraded config fallback.

## Task 1: Python Internal Route Auth and Basic Routes

**Files:**
- Create: `data_foundation/internal_api.py`
- Modify: `data_foundation/http_app.py`
- Test: `tests/data_foundation/test_internal_api.py`

- [ ] **Step 1: Write failing tests for internal key and admin ACL**

Add `tests/data_foundation/test_internal_api.py`:

```python
from __future__ import annotations

import pytest
from starlette.testclient import TestClient


def _client(monkeypatch, *, secret: str = "internal-secret", admins: str = "ou_admin"):
    monkeypatch.setenv("XHS_INTERNAL_SECRET", secret)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", admins)
    import data_foundation.http_app as http_app

    return TestClient(http_app.app)


def test_internal_ok_rejects_missing_key(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/internal/ok")

    assert response.status_code == 401
    assert response.json()["error"] == "Unauthorized internal request"


def test_internal_ok_accepts_internal_key(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/internal/ok", headers={"X-XHS-Internal-Key": "internal-secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_admin_route_rejects_non_admin_even_if_header_claims_admin(monkeypatch):
    client = _client(monkeypatch, admins="ou_real_admin")

    response = client.get(
        "/internal/config",
        headers={
            "X-XHS-Internal-Key": "internal-secret",
            "X-XHS-Open-Id": "ou_normal",
            "X-XHS-Is-Admin": "true",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"] == "Forbidden"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py -q
```

Expected: FAIL because `/internal/ok` and `/internal/config` are not registered yet.

- [ ] **Step 3: Implement internal auth and `/internal/ok`**

Create `data_foundation/internal_api.py`:

```python
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


@dataclass(frozen=True)
class InternalActor:
    open_id: str
    is_admin: bool


def _admin_open_ids() -> set[str]:
    return {
        item.strip()
        for item in os.environ.get("XHS_ADMIN_OPEN_IDS", "").split(",")
        if item.strip()
    }


def _json_error(status: int, message: str) -> JSONResponse:
    response = JSONResponse({"error": message}, status_code=status)
    response.headers["Cache-Control"] = "no-store"
    return response


def _json_ok(payload: dict) -> JSONResponse:
    response = JSONResponse(payload)
    response.headers["Cache-Control"] = "no-store"
    return response


def _require_internal_key(request: Request) -> JSONResponse | None:
    expected = os.environ.get("XHS_INTERNAL_SECRET", "")
    supplied = request.headers.get("X-XHS-Internal-Key", "")
    if not expected or not hmac.compare_digest(expected, supplied):
        return _json_error(401, "Unauthorized internal request")
    return None


def _actor_from_request(request: Request) -> InternalActor:
    open_id = request.headers.get("X-XHS-Open-Id", "").strip()
    is_admin = bool(open_id and open_id in _admin_open_ids())
    claimed = request.headers.get("X-XHS-Is-Admin")
    if claimed is not None and claimed.strip().lower() in {"true", "1", "yes"} and not is_admin:
        raise PermissionError("Forbidden")
    return InternalActor(open_id=open_id, is_admin=is_admin)


def require_internal(request: Request) -> JSONResponse | None:
    return _require_internal_key(request)


def require_user(request: Request) -> InternalActor | JSONResponse:
    denied = _require_internal_key(request)
    if denied is not None:
        return denied
    actor = _actor_from_request(request)
    if not actor.open_id:
        return _json_error(401, "Missing internal user")
    return actor


def require_admin(request: Request) -> InternalActor | JSONResponse:
    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    if not actor.is_admin:
        return _json_error(403, "Forbidden")
    return actor


async def internal_ok(request: Request) -> JSONResponse:
    denied = require_internal(request)
    if denied is not None:
        return denied
    return _json_ok({"ok": True})


async def internal_config_get(request: Request) -> JSONResponse:
    actor = require_admin(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _json_ok({"ok": True, "configs": {}, "version": ""})


internal_routes = [
    Route("/internal/ok", internal_ok, methods=["GET"]),
    Route("/internal/config", internal_config_get, methods=["GET"]),
]
```

Modify `data_foundation/http_app.py` route registration:

```python
from data_foundation.internal_api import internal_routes

app = Starlette(routes=[Route("/ok", ok), *internal_routes], lifespan=lifespan)
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py -q
```

Expected: PASS for the three new tests.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/internal_api.py data_foundation/http_app.py tests/data_foundation/test_internal_api.py
git commit -m "feat: add authenticated internal routes"
```

## Task 2: Config Center Internal Routes

**Files:**
- Modify: `data_foundation/internal_api.py`
- Modify: `config_center.py`
- Modify: `tests/test_config_center.py`
- Test: `tests/data_foundation/test_internal_api.py`

- [ ] **Step 1: Write failing tests for config get/set**

Append to `tests/data_foundation/test_internal_api.py`:

```python
from cryptography.fernet import Fernet


def _admin_headers(secret: str = "internal-secret", open_id: str = "ou_admin") -> dict[str, str]:
    return {
        "X-XHS-Internal-Key": secret,
        "X-XHS-Open-Id": open_id,
        "X-XHS-Is-Admin": "true",
    }


def test_internal_config_round_trip_returns_plain_admin_values(monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    config_path = tmp_path / "config-center.enc"
    monkeypatch.setenv("XHS_CONFIG_ENCRYPTION_KEY", key)
    monkeypatch.setenv("XHS_CONFIG_CENTER_PATH", str(config_path))
    client = _client(monkeypatch)

    save_response = client.post(
        "/internal/config",
        headers=_admin_headers(),
        json={"configs": {"LLM_API_KEY": "sk-secret", "LLM_PROVIDER": "openai"}},
    )
    assert save_response.status_code == 200
    save_payload = save_response.json()
    assert save_payload["ok"] is True
    assert save_payload["changed_keys"] == ["LLM_API_KEY", "LLM_PROVIDER"]
    assert save_payload["version"]

    read_response = client.get("/internal/config", headers=_admin_headers())
    assert read_response.status_code == 200
    read_payload = read_response.json()
    assert read_payload["ok"] is True
    assert read_payload["configs"]["LLM_API_KEY"] == "sk-secret"
    assert read_payload["configs"]["LLM_PROVIDER"] == "openai"
    assert read_payload["version"] == save_payload["version"]


def test_internal_config_rejects_deploy_only_internal_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("XHS_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("XHS_CONFIG_CENTER_PATH", str(tmp_path / "config-center.enc"))
    client = _client(monkeypatch)

    response = client.post(
        "/internal/config",
        headers=_admin_headers(),
        json={"configs": {"XHS_INTERNAL_BASE_URL": "http://127.0.0.1:2024"}},
    )

    assert response.status_code == 400
    assert "not editable" in response.json()["error"]
```

Append to `tests/test_config_center.py`:

```python
def test_config_center_rejects_internal_base_url(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ConfigValidationError, match="XHS_INTERNAL_BASE_URL"):
        center.save(actor_open_id="ou_admin", updates={"XHS_INTERNAL_BASE_URL": "http://127.0.0.1:2024"})
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py tests/test_config_center.py -q
```

Expected: FAIL because POST `/internal/config` is not implemented and `XHS_INTERNAL_BASE_URL` is not deploy-only yet.

- [ ] **Step 3: Add deploy-only key and config handlers**

Modify `config_center.py`:

```python
DEPLOY_ONLY_KEYS = {
    "XHS_ADMIN_OPEN_IDS",
    "XHS_JWT_SECRET",
    "XHS_INTERNAL_SECRET",
    "XHS_INTERNAL_BASE_URL",
    "XHS_CONFIG_ENCRYPTION_KEY",
    "XHS_CONFIG_CENTER_PATH",
    "PATH",
    "NODE_OPTIONS",
}
```

Modify `data_foundation/internal_api.py` imports:

```python
from config_center import ConfigCenter, ConfigValidationError
```

Add helpers and replace `internal_config_get`; add `internal_config_post`:

```python
def _config_center() -> ConfigCenter:
    return ConfigCenter(
        path=os.environ["XHS_CONFIG_CENTER_PATH"],
        encryption_key=os.environ["XHS_CONFIG_ENCRYPTION_KEY"],
    )


def _config_version(center: ConfigCenter) -> str:
    history = center.history()
    return history[-1].version if history else ""


async def internal_config_get(request: Request) -> JSONResponse:
    actor = require_admin(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        center = _config_center()
        return _json_ok({"ok": True, "configs": center.get_plain(), "version": _config_version(center)})
    except KeyError as exc:
        return _json_error(500, f"Config center missing required environment: {exc.args[0]}")


async def internal_config_post(request: Request) -> JSONResponse:
    actor = require_admin(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        body = await request.json()
        configs = body.get("configs")
        if not isinstance(configs, dict):
            return _json_error(400, "Bad Request: Missing configs object")
        snapshot = _config_center().save(actor_open_id=actor.open_id, updates=configs)
        return _json_ok({"ok": True, "version": snapshot.version, "changed_keys": snapshot.changed_keys})
    except ConfigValidationError as exc:
        return _json_error(400, str(exc))
    except KeyError as exc:
        return _json_error(500, f"Config center missing required environment: {exc.args[0]}")
```

Update `internal_routes`:

```python
internal_routes = [
    Route("/internal/ok", internal_ok, methods=["GET"]),
    Route("/internal/config", internal_config_get, methods=["GET"]),
    Route("/internal/config", internal_config_post, methods=["POST"]),
]
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py tests/test_config_center.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config_center.py data_foundation/internal_api.py tests/data_foundation/test_internal_api.py tests/test_config_center.py
git commit -m "feat: serve config center over internal http"
```

## Task 3: Feishu Internal Routes

**Files:**
- Modify: `data_foundation/internal_api.py`
- Test: `tests/data_foundation/test_internal_api.py`

- [ ] **Step 1: Write failing tests for user-scoped Feishu routes**

Append to `tests/data_foundation/test_internal_api.py`:

```python
def test_internal_uat_status_uses_current_open_id(monkeypatch):
    client = _client(monkeypatch)

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(internal_api, "get_uat", lambda open_id: "token" if open_id == "ou_user" else None)

    response = client.get(
        "/internal/feishu/status",
        headers={
            "X-XHS-Internal-Key": "internal-secret",
            "X-XHS-Open-Id": "ou_user",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "authorized": True}


def test_internal_uat_save_requires_user_identity(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/internal/feishu/uat",
        headers={"X-XHS-Internal-Key": "internal-secret"},
        json={"uat": "token", "refresh_token": "", "expires_at": 123, "scopes": [], "name": "User"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "Missing internal user"


def test_internal_chats_filters_group_chats(monkeypatch):
    client = _client(monkeypatch)

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(internal_api, "get_uat", lambda open_id: "token")
    monkeypatch.setattr(internal_api, "identity_config", lambda open_id: {"user": open_id})
    monkeypatch.setattr(
        internal_api,
        "lark_cli",
        lambda command, config=None: '{"data":{"chats":[{"chat_mode":"group","chat_id":"oc_1","name":"群"},{"chat_mode":"p2p","chat_id":"ou_1","name":"人"}]}}',
    )

    response = client.get(
        "/internal/feishu/chats",
        headers={"X-XHS-Internal-Key": "internal-secret", "X-XHS-Open-Id": "ou_user"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "chats": [{"chat_id": "oc_1", "name": "群"}]}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py -q
```

Expected: FAIL because Feishu routes are not implemented.

- [ ] **Step 3: Implement Feishu handlers by moving bridge logic into internal API**

Modify `data_foundation/internal_api.py` imports:

```python
import json
import shlex

from tools.lark_cli import lark_cli
from tools.runtime_identity import identity_config
from tools.uat_store import get_uat, save_uat
```

Add handlers:

```python
async def internal_feishu_status(request: Request) -> JSONResponse:
    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    if get_uat(actor.open_id):
        return _json_ok({"ok": True, "authorized": True})
    return _json_ok({"ok": True, "authorized": False, "error": "Feishu user authorization is missing or expired."})


async def internal_feishu_uat_post(request: Request) -> JSONResponse:
    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    body = await request.json()
    save_uat(
        open_id=actor.open_id,
        uat=str(body.get("uat") or ""),
        refresh_token=str(body.get("refresh_token") or ""),
        expires_at=float(body.get("expires_at") or 0),
        scopes=list(body.get("scopes") or []),
        name=str(body.get("name") or actor.open_id),
    )
    return _json_ok({"ok": True})


async def internal_feishu_chats(request: Request) -> JSONResponse:
    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    if not get_uat(actor.open_id):
        return _json_error(401, "Unauthorized: Feishu token invalid or expired.")
    try:
        raw = lark_cli("im +chat-list", config=identity_config(actor.open_id))
        if raw.startswith("Error"):
            return _json_error(500, raw)
        data = json.loads(raw)
        chats = data.get("data", {}).get("chats") or []
        groups = [
            {"chat_id": item.get("chat_id"), "name": item.get("name", "未命名群聊")}
            for item in chats
            if item.get("chat_mode") == "group"
        ]
        return _json_ok({"ok": True, "chats": groups})
    except Exception as exc:
        return _json_error(500, str(exc))


async def internal_feishu_wiki_space(request: Request) -> JSONResponse:
    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    fallback_space_id = os.environ.get("FEISHU_WIKI_SPACE_ID", "7648177996175543260")
    if not get_uat(actor.open_id):
        return _json_ok({"ok": True, "name": "小红书爆单手册", "space_id": fallback_space_id})
    try:
        command = shlex.join(["wiki", "spaces", "get", "--space-id", fallback_space_id])
        raw = lark_cli(command, config=identity_config(actor.open_id))
        if raw.startswith("Error") or "error" in raw.lower() or raw.startswith("⚠️"):
            return _json_ok({"ok": True, "name": "小红书爆单手册", "space_id": fallback_space_id})
        data = json.loads(raw)
        name = data.get("data", {}).get("space", {}).get("name") or "小红书爆单手册"
        return _json_ok({"ok": True, "name": name, "space_id": fallback_space_id})
    except Exception:
        return _json_ok({"ok": True, "name": "小红书爆单手册", "space_id": fallback_space_id})
```

Update `internal_routes`:

```python
Route("/internal/feishu/status", internal_feishu_status, methods=["GET"]),
Route("/internal/feishu/uat", internal_feishu_uat_post, methods=["POST"]),
Route("/internal/feishu/chats", internal_feishu_chats, methods=["GET"]),
Route("/internal/feishu/wiki-space", internal_feishu_wiki_space, methods=["GET"]),
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/internal_api.py tests/data_foundation/test_internal_api.py
git commit -m "feat: move feishu bridge actions to internal http"
```

## Task 4: Runtime Facts Endpoint

**Files:**
- Modify: `data_foundation/internal_api.py`
- Test: `tests/data_foundation/test_internal_api.py`

- [ ] **Step 1: Write failing tests for admin-only runtime facts**

Append to `tests/data_foundation/test_internal_api.py`:

```python
def test_internal_health_facts_is_admin_only(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    response = client.get(
        "/internal/health/facts",
        headers={"X-XHS-Internal-Key": "internal-secret", "X-XHS-Open-Id": "ou_user"},
    )

    assert response.status_code == 403


def test_internal_health_facts_returns_safe_shape(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(
        internal_api,
        "runtime_facts_payload",
        lambda: {
            "ok": True,
            "scheduler": {"enabled": False},
            "outbox": {"pending": 0, "blocked": 0, "dead": 0},
            "embedding": {"active": None, "building": None},
            "sync": {"running": False},
            "errors": [],
        },
    )

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json()["scheduler"] == {"enabled": False}
    assert "credentials" not in response.text
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py -q
```

Expected: FAIL because `/internal/health/facts` is not implemented.

- [ ] **Step 3: Implement safe runtime facts skeleton**

Add to `data_foundation/internal_api.py`:

```python
def runtime_facts_payload() -> dict:
    return {
        "ok": True,
        "scheduler": {
            "enabled": os.environ.get("XHS_SYNC_ENABLED", "false").strip().lower() == "true",
        },
        "outbox": {
            "pending": 0,
            "retry": 0,
            "processing": 0,
            "blocked": 0,
            "dead": 0,
        },
        "embedding": {
            "active": None,
            "building": None,
        },
        "sync": {
            "running": False,
        },
        "errors": [],
    }


async def internal_health_facts(request: Request) -> JSONResponse:
    actor = require_admin(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _json_ok(runtime_facts_payload())
```

Add route:

```python
Route("/internal/health/facts", internal_health_facts, methods=["GET"]),
```

This skeleton intentionally returns safe facts only. Slice C will expand the payload from telemetry repositories.

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add data_foundation/internal_api.py tests/data_foundation/test_internal_api.py
git commit -m "feat: expose internal runtime facts skeleton"
```

## Task 5: Web Config Allowlist Convergence

**Files:**
- Modify: `web/src/lib/server/config-store.ts`
- Modify: `web/tests/config-store-allowlist.test.ts`
- Test: `tests/test_config_center.py`

- [ ] **Step 1: Write failing Web allowlist tests**

Append to `web/tests/config-store-allowlist.test.ts`:

```ts
assert.equal(deployOnlyKeys.has("XHS_INTERNAL_SECRET"), true);
assert.equal(deployOnlyKeys.has("XHS_INTERNAL_BASE_URL"), true);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_INTERNAL_SECRET: "secret" }),
  /not editable/,
);

assert.throws(
  () => assertAllowedConfigKeys({ XHS_INTERNAL_BASE_URL: "http://127.0.0.1:2024" }),
  /not editable/,
);
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
cd web
corepack pnpm test:unit
```

Expected: FAIL because `XHS_INTERNAL_BASE_URL` is not deploy-only yet.

- [ ] **Step 3: Implement Web deploy-only key**

Modify `web/src/lib/server/config-store.ts`:

```ts
export const deployOnlyKeys = new Set([
  "XHS_ADMIN_OPEN_IDS",
  "XHS_JWT_SECRET",
  "XHS_INTERNAL_SECRET",
  "XHS_INTERNAL_BASE_URL",
  "XHS_CONFIG_ENCRYPTION_KEY",
  "XHS_CONFIG_CENTER_PATH",
  "PATH",
  "NODE_OPTIONS",
]);
```

- [ ] **Step 4: Run Web unit tests**

Run:

```bash
cd web
corepack pnpm test:unit
```

Expected: PASS.

- [ ] **Step 5: Run Python config tests**

Run:

```bash
uv run pytest tests/test_config_center.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/server/config-store.ts web/tests/config-store-allowlist.test.ts tests/test_config_center.py
git commit -m "fix: align internal deploy-only config keys"
```

## Task 6: Next Internal HTTP Client

**Files:**
- Modify: `web/src/lib/server/internal-client.ts`
- Test: `web/tests/internal-client-http.test.ts`

- [ ] **Step 1: Write failing tests for HTTP forwarding**

Create `web/tests/internal-client-http.test.ts`:

```ts
import assert from "node:assert/strict";
import test from "node:test";

import { forwardToInternalServer } from "../src/lib/server/internal-client";

test("forwards internal request over HTTP with internal headers", async () => {
  const originalBaseUrl = process.env.XHS_INTERNAL_BASE_URL;
  const originalSecret = process.env.XHS_INTERNAL_SECRET;
  const originalFetch = globalThis.fetch;
  const calls: Array<{ url: string; init: RequestInit }> = [];

  process.env.XHS_INTERNAL_BASE_URL = "http://127.0.0.1:2024";
  process.env.XHS_INTERNAL_SECRET = "internal-secret";
  globalThis.fetch = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init || {} });
    return new Response(JSON.stringify({ ok: true, configs: { LLM_API_KEY: "sk" }, version: "v1" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  try {
    const response = await forwardToInternalServer("/_internal/config-status", "GET", "ou_admin", undefined, {
      isAdmin: true,
    });
    const payload = await response.json();

    assert.equal(response.status, 200);
    assert.equal(payload.configs.LLM_API_KEY, "sk");
    assert.equal(calls[0].url, "http://127.0.0.1:2024/internal/config");
    assert.equal((calls[0].init.headers as Record<string, string>)["X-XHS-Internal-Key"], "internal-secret");
    assert.equal((calls[0].init.headers as Record<string, string>)["X-XHS-Open-Id"], "ou_admin");
    assert.equal((calls[0].init.headers as Record<string, string>)["X-XHS-Is-Admin"], "true");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalBaseUrl === undefined) delete process.env.XHS_INTERNAL_BASE_URL;
    else process.env.XHS_INTERNAL_BASE_URL = originalBaseUrl;
    if (originalSecret === undefined) delete process.env.XHS_INTERNAL_SECRET;
    else process.env.XHS_INTERNAL_SECRET = originalSecret;
  }
});
```

- [ ] **Step 2: Confirm unit runner includes the test**

Open `web/scripts/run-unit-tests.mjs` and confirm it already includes this collection logic:

```js
...(await readdir(join(webRoot, "tests")))
  .filter((name) => name.endsWith(".test.ts"))
  .sort()
  .map((name) => join(webRoot, "tests", name)),
```

No edit to `web/scripts/run-unit-tests.mjs` is expected for this task.

- [ ] **Step 3: Run test to verify failure**

Run:

```bash
cd web
corepack pnpm test:unit
```

Expected: FAIL because `forwardToInternalServer` still uses `execFile`.

- [ ] **Step 4: Implement HTTP forwarding**

Modify `web/src/lib/server/internal-client.ts` to map legacy internal names to HTTP routes:

```ts
const internalPathMap: Record<string, { path: string; method: "GET" | "POST"; admin: boolean }> = {
  "/_internal/chats": { path: "/internal/feishu/chats", method: "GET", admin: false },
  "/_internal/uat": { path: "/internal/feishu/uat", method: "POST", admin: false },
  "/_internal/uat-status": { path: "/internal/feishu/status", method: "GET", admin: false },
  "/_internal/wiki-space": { path: "/internal/feishu/wiki-space", method: "GET", admin: false },
  "/_internal/config-status": { path: "/internal/config", method: "GET", admin: true },
  "/_internal/config-set": { path: "/internal/config", method: "POST", admin: true },
};
```

Replace `execFile` production path with:

```ts
export async function forwardToInternalServer(
  pathName: string,
  method: "GET" | "POST",
  openId: string,
  extraBody?: any,
  extraHeaders?: any,
): Promise<Response> {
  const route = internalPathMap[pathName];
  if (!route) {
    return new Response(JSON.stringify({ error: `Unknown internal path: ${pathName}` }), { status: 404 });
  }
  const baseUrl = process.env.XHS_INTERNAL_BASE_URL;
  const secret = process.env.XHS_INTERNAL_SECRET;
  if (!baseUrl || !secret) {
    return new Response(JSON.stringify({ error: "Internal HTTP is not configured" }), { status: 503 });
  }

  const headers: Record<string, string> = {
    "X-XHS-Internal-Key": secret,
    "X-XHS-Open-Id": openId,
    "X-XHS-Is-Admin": String(Boolean(extraHeaders?.isAdmin)),
  };
  if (route.method === "POST") headers["Content-Type"] = "application/json";

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10_000);
  try {
    return await fetch(new URL(route.path, baseUrl).toString(), {
      method: route.method,
      headers,
      body: route.method === "POST" ? JSON.stringify(extraBody || {}) : undefined,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message || "Internal HTTP request failed" }), {
      status: 503,
    });
  } finally {
    clearTimeout(timeout);
  }
}
```

Keep the old `execFile` code out of the main function. The config-only fallback will be added in Task 7.

- [ ] **Step 5: Run Web unit tests**

Run:

```bash
cd web
corepack pnpm test:unit
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/server/internal-client.ts web/tests/internal-client-http.test.ts
git commit -m "feat: forward internal requests over http"
```

## Task 7: Config-Only Degraded Fallback

**Files:**
- Modify: `web/src/lib/server/internal-client.ts`
- Modify: `web/src/app/api/config/route.ts`
- Test: `web/tests/internal-client-http.test.ts`

- [ ] **Step 1: Write failing tests for config fallback**

Append to `web/tests/internal-client-http.test.ts`:

```ts
test("returns degraded config fallback only for config status when internal http is unavailable", async () => {
  const originalBaseUrl = process.env.XHS_INTERNAL_BASE_URL;
  const originalSecret = process.env.XHS_INTERNAL_SECRET;

  delete process.env.XHS_INTERNAL_BASE_URL;
  process.env.XHS_INTERNAL_SECRET = "internal-secret";

  try {
    const configResponse = await forwardToInternalServer("/_internal/config-status", "GET", "ou_admin", undefined, {
      isAdmin: true,
      allowConfigFallback: true,
    });
    const configPayload = await configResponse.json();
    assert.equal(configResponse.status, 503);
    assert.equal(configPayload.degraded, true);

    const chatsResponse = await forwardToInternalServer("/_internal/chats", "GET", "ou_user", undefined, {
      allowConfigFallback: true,
    });
    const chatsPayload = await chatsResponse.json();
    assert.equal(chatsResponse.status, 503);
    assert.equal(chatsPayload.degraded, undefined);
  } finally {
    if (originalBaseUrl === undefined) delete process.env.XHS_INTERNAL_BASE_URL;
    else process.env.XHS_INTERNAL_BASE_URL = originalBaseUrl;
    if (originalSecret === undefined) delete process.env.XHS_INTERNAL_SECRET;
    else process.env.XHS_INTERNAL_SECRET = originalSecret;
  }
});
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
cd web
corepack pnpm test:unit
```

Expected: FAIL because degraded fallback is not implemented.

- [ ] **Step 3: Implement config-only degraded response**

In `web/src/lib/server/internal-client.ts`, when `XHS_INTERNAL_BASE_URL` is missing or fetch fails and `extraHeaders?.allowConfigFallback === true` and the path is `/_internal/config-status` or `/_internal/config-set`, return:

```ts
return new Response(
  JSON.stringify({
    ok: false,
    degraded: true,
    error: "Internal HTTP unavailable; config fallback is required",
  }),
  { status: 503, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } },
);
```

This task does not reimplement Fernet in TypeScript. The actual local Python fallback can remain unavailable until a later maintenance task if the process cannot access Python. The important behavior here is explicit degraded signaling and no silent alternate config store.

Modify `web/src/app/api/config/route.ts` calls:

```ts
const resp = await forwardToInternalServer("/_internal/config-status", "GET", "system", undefined, {
  isAdmin: true,
  allowConfigFallback: true,
});
```

and:

```ts
const resp = await forwardToInternalServer("/_internal/config-set", "POST", user.openId, { configs }, {
  isAdmin: true,
  allowConfigFallback: true,
});
```

If the response contains `degraded: true`, return it to the client with the same status and `Cache-Control: no-store`.

- [ ] **Step 4: Run Web unit tests**

Run:

```bash
cd web
corepack pnpm test:unit
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/server/internal-client.ts web/src/app/api/config/route.ts web/tests/internal-client-http.test.ts
git commit -m "fix: make config fallback explicitly degraded"
```

## Task 8: Switch Feishu and Config API Call Sites

**Files:**
- Modify: `web/src/app/api/config/route.ts`
- Modify: `web/src/app/api/feishu/status/route.ts`
- Modify: `web/src/app/api/feishu/chats/route.ts`
- Modify: `web/src/app/api/feishu/wiki-space/route.ts`
- Modify: `web/src/app/api/auth/feishu/callback/route.ts`
- Test: existing Web unit tests and TypeScript

- [ ] **Step 1: Update config route admin forwarding**

Ensure both config GET and POST pass `{ isAdmin: true, allowConfigFallback: true }`.

For GET:

```ts
const resp = await forwardToInternalServer("/_internal/config-status", "GET", user.openId, undefined, {
  isAdmin: true,
  allowConfigFallback: true,
});
```

Use `const user = await requireAdmin();` instead of discarding the admin user in GET.

- [ ] **Step 2: Update Feishu routes to pass non-admin context**

For `/api/feishu/status`, `/api/feishu/chats`, `/api/feishu/wiki-space`, and OAuth callback UAT sync, call:

```ts
await forwardToInternalServer("/_internal/uat-status", "GET", user.openId, undefined, {
  isAdmin: user.isAdmin,
});
```

For routes that manually verify JWT and only have `payload.sub`, pass:

```ts
{ isAdmin: false }
```

Do not require admin for Feishu user routes.

- [ ] **Step 3: Run TypeScript**

Run:

```bash
cd web
corepack pnpm exec tsc --noEmit
```

Expected: PASS.

- [ ] **Step 4: Run Web unit tests**

Run:

```bash
cd web
corepack pnpm test:unit
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add web/src/app/api/config/route.ts web/src/app/api/feishu/status/route.ts web/src/app/api/feishu/chats/route.ts web/src/app/api/feishu/wiki-space/route.ts web/src/app/api/auth/feishu/callback/route.ts
git commit -m "refactor: route web internals through internal http"
```

## Task 9: Documentation and Old Bridge Boundary

**Files:**
- Modify: `README.md`
- Test: `git diff --check`

- [ ] **Step 1: Update README current facts**

Add under the configuration center / data foundation sections:

```markdown
- Web 内部请求通过 LangGraph `http.app` 的 `/internal/*` routes 访问 Python 能力；Next 负责用户/管理员 cookie 鉴权，并用 `XHS_INTERNAL_SECRET` 调用内部 route。
- `tools/web_bridge_runner.py` 不再是 Web 生产请求主路径；仅允许作为配置恢复或维护工具使用，且 degraded fallback 必须明确返回降级状态。
- `XHS_INTERNAL_BASE_URL` 与 `XHS_INTERNAL_SECRET` 是 deploy-only 配置，不进入管理员配置中心历史版本或状态 API。
```

- [ ] **Step 2: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document internal http runtime boundary"
```

## Task 10: Full Local Verification

**Files:** no intentional edits.

- [ ] **Step 1: Run focused Python tests**

Run:

```bash
uv run pytest tests/data_foundation/test_internal_api.py tests/data_foundation/test_http_app.py tests/test_config_center.py tests/test_web_bridge_runner.py -q
```

Expected: PASS.

- [ ] **Step 2: Run all Python tests**

Run:

```bash
uv run pytest -q
```

Expected: PASS. If pre-existing unrelated dirty changes fail tests, isolate with `git diff --name-only` and report separately before editing files outside this plan.

- [ ] **Step 3: Run Web quality gates**

Run:

```bash
cd web
corepack pnpm test:unit
corepack pnpm exec tsc --noEmit
corepack pnpm lint
corepack pnpm build
```

Expected: all commands exit 0. Existing lint warnings are acceptable if the command exits 0.

- [ ] **Step 4: Run diff check**

Run:

```bash
git diff --check
```

Expected: no output.

- [ ] **Step 5: Commit any verification-only documentation fixes**

If verification required doc-only corrections:

```bash
git add README.md docs/superpowers/plans/2026-06-20-phase-5-1-internal-http-runtime-facts.md
git commit -m "docs: clarify internal http verification"
```

If no files changed, skip this step.

## Task 11: Server Validation and Deployment

**Files:** no source edits.

- [ ] **Step 1: Push current branch**

Run:

```bash
git push origin master
```

Expected: push succeeds.

- [ ] **Step 2: Pull and test on server**

On the server, run:

```bash
cd /home/ubuntu/xiaohongshu-agent
git pull --ff-only origin master
set -a
. ./.env
set +a
TEST_XHS_DATABASE_URL="$XHS_DATABASE_URL" .venv/bin/python -m pytest tests/data_foundation/test_internal_api.py tests/data_foundation/test_http_app.py tests/test_config_center.py -q
cd web
corepack pnpm test:unit
corepack pnpm exec tsc --noEmit
corepack pnpm build
```

Expected: all commands exit 0.

- [ ] **Step 3: Restart production processes**

Run:

```bash
pm2 restart xhs-backend --update-env
pm2 restart xhs-frontend --update-env
pm2 save
pm2 status
```

Expected: `xhs-backend` and `xhs-frontend` are `online`.

- [ ] **Step 4: Smoke check internal route**

Run a server-local smoke request without printing secrets:

```bash
python - <<'PY'
import os
import httpx

base = os.environ.get("XHS_INTERNAL_BASE_URL", "http://127.0.0.1:2024")
secret = os.environ["XHS_INTERNAL_SECRET"]
resp = httpx.get(
    base.rstrip("/") + "/internal/ok",
    headers={"X-XHS-Internal-Key": secret},
    timeout=5,
)
print(resp.status_code)
print(resp.json())
PY
```

Expected:

```text
200
{'ok': True}
```

## Self-Review Checklist

- [ ] Every Phase 5.1 spec requirement maps to a task:
  - internal routes: Tasks 1-4
  - internal key and ACL: Tasks 1, 3, 4, 6, 8
  - config read/write: Task 2
  - Feishu user routes: Task 3
  - runtime facts foundation: Task 4
  - Web/Python allowlist convergence: Task 5
  - config degraded fallback: Task 7
  - Web call sites: Task 8
  - docs: Task 9
  - local/server validation: Tasks 10-11
- [ ] No plan step asks an implementer to invent behavior without code or command guidance.
- [ ] No task stages the existing unrelated dirty files listed at the top.
- [ ] No route trusts `X-XHS-Is-Admin` without Python recomputing admin membership.
- [ ] No fallback silently writes a second config store.
- [ ] No ordinary Feishu user route is made admin-only.
