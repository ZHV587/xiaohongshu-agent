# Phase 2 Config Center And Model Hot Reload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move runtime business configuration out of `.env` into an audited encrypted config center, then make proven model-router paths use new model pools without restarting the LangGraph/DeepAgents process.

**Architecture:** Keep DeepAgents and LangGraph untouched. Add a Python config-center module and a process-local `ModelRegistry`; `ModelRouterMiddleware.wrap_model_call` / `awrap_model_call` continue to use native LangChain middleware and `request.override(model=candidate.model)`. Phase 2 only promises hot reload for paths proven by tests; static startup paths such as rubric remain restart-required until converted.

**Tech Stack:** Python 3.12, pytest, cryptography Fernet, httpx, DeepAgents, LangChain AgentMiddleware, Next.js App Router, TypeScript.

---

## File Map

- Create `config_center.py`: encrypted JSON config store, version history, audit entries, redacted reads, env bootstrap import.
- Create `tests/test_config_center.py`: config center persistence, encryption, allowlist, redaction, audit, rollback tests.
- Create `model_registry.py`: process-local registry that loads config snapshots, builds model pools, exposes status, supports reload.
- Modify `models.py`: separate pool-building from env reads, add config-driven pool builder, make router middleware read from registry each call.
- Modify `agent.py`: construct registry once, route main model through native middleware; keep rubric restart-required unless converted in Task 5.
- Modify `subagents.py`: use the shared registry-backed router middleware, not a separate env-built pool.
- Create `tests/test_model_registry.py`: registry reload, version-scoped health, sync/async router hot-switch tests.
- Modify `web/src/app/api/config/route.ts`: read/write config through backend config command instead of direct `.env` writes when phase-2 mode is enabled.
- Modify `tools/cli_runner.py`: add `config-get`, `config-set`, `config-status` actions for out-of-process config store access only; do not claim these reload in-process registry.
- Modify `web/src/app/api/backend/status/route.ts`: include config-center version, active registry version, active model IDs, reload coverage status.
- Modify `README.md` and `.env.example`: document phase-2 config storage, encryption key, and exact hot-reload limits.

## Task 1: Encrypted Config Center

**Files:**
- Create: `config_center.py`
- Test: `tests/test_config_center.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing config-center tests**

Create `tests/test_config_center.py`:

```python
import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from config_center import (
    ConfigCenter,
    ConfigValidationError,
    bootstrap_snapshot_from_env,
)


def test_config_center_encrypts_secret_values(tmp_path):
    key = Fernet.generate_key().decode()
    path = tmp_path / "config-center.enc"
    center = ConfigCenter(path=path, encryption_key=key)

    saved = center.save(
        actor_open_id="ou_admin",
        updates={
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://gateway.example/v1",
            "LLM_API_KEY": "sk-secret",
            "LLM_QUALITY_MODELS": "gpt-4o,claude-sonnet-4-6",
        },
    )

    raw = path.read_bytes()
    assert b"sk-secret" not in raw
    assert saved.version
    assert center.get_plain()["LLM_API_KEY"] == "sk-secret"
    assert center.get_redacted()["LLM_API_KEY"] == "********"


def test_config_center_rejects_deploy_only_keys(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ConfigValidationError, match="XHS_JWT_SECRET"):
        center.save(actor_open_id="ou_admin", updates={"XHS_JWT_SECRET": "do-not-edit"})


def test_config_center_records_audit_history(tmp_path):
    center = ConfigCenter(path=tmp_path / "config.enc", encryption_key=Fernet.generate_key().decode())
    first = center.save(actor_open_id="ou_admin", updates={"LLM_PROVIDER": "openai"})
    second = center.save(actor_open_id="ou_admin", updates={"LLM_QUALITY_MODELS": "gpt-4o"})

    history = center.history()
    assert [item.version for item in history] == [first.version, second.version]
    assert history[0].actor_open_id == "ou_admin"
    assert history[1].changed_keys == ["LLM_QUALITY_MODELS"]


def test_bootstrap_snapshot_from_env_imports_allowed_keys(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-bootstrap")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "gpt-4o")
    monkeypatch.setenv("XHS_JWT_SECRET", "not-imported")

    snapshot = bootstrap_snapshot_from_env(actor_open_id="system-bootstrap")

    assert snapshot.values["LLM_API_KEY"] == "sk-bootstrap"
    assert "XHS_JWT_SECRET" not in snapshot.values
```

- [ ] **Step 2: Run red tests**

Run:

```powershell
uv run pytest tests/test_config_center.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'config_center'`.

- [ ] **Step 3: Implement `config_center.py`**

Create `config_center.py`:

```python
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

EDITABLE_KEYS = {
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_QUALITY_MODELS",
    "LLM_GATEWAY_2_BASE_URL",
    "LLM_GATEWAY_2_API_KEY",
    "LLM_GATEWAY_3_BASE_URL",
    "LLM_GATEWAY_3_API_KEY",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "FEISHU_BITABLE_APP_TOKEN",
    "FEISHU_BITABLE_TABLE_ID",
    "XHS_BITABLE_FIELD_TITLE",
    "XHS_BITABLE_FIELD_BODY",
    "XHS_BITABLE_FIELD_TAGS",
    "XHS_BITABLE_FIELD_AUTHOR",
    "XHS_BITABLE_FIELD_STATUS",
}

SECRET_KEYS = {
    "LLM_API_KEY",
    "LLM_GATEWAY_2_API_KEY",
    "LLM_GATEWAY_3_API_KEY",
    "FEISHU_APP_SECRET",
}

DEPLOY_ONLY_KEYS = {
    "XHS_ADMIN_OPEN_IDS",
    "XHS_JWT_SECRET",
    "XHS_INTERNAL_SECRET",
    "XHS_CONFIG_ENCRYPTION_KEY",
    "XHS_CONFIG_CENTER_PATH",
    "PATH",
    "NODE_OPTIONS",
}


class ConfigValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ConfigSnapshot:
    version: str
    values: dict[str, str]
    actor_open_id: str
    changed_keys: list[str]
    created_at: float


def _make_version(values: dict[str, str], created_at: float) -> str:
    digest = sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"{int(created_at)}-{digest}"


def _validate_updates(updates: dict[str, Any]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in updates.items():
        if key in DEPLOY_ONLY_KEYS or key not in EDITABLE_KEYS:
            raise ConfigValidationError(f"Config key is not editable: {key}")
        sanitized[key] = str(value or "")
    return sanitized


class ConfigCenter:
    def __init__(self, path: Path | str, encryption_key: str) -> None:
        self.path = Path(path)
        self.fernet = Fernet(encryption_key.encode("utf-8"))

    def _read_document(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"current": {}, "history": []}
        decrypted = self.fernet.decrypt(self.path.read_bytes())
        return json.loads(decrypted.decode("utf-8"))

    def _write_document(self, document: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
        self.path.write_bytes(self.fernet.encrypt(payload))

    def save(self, actor_open_id: str, updates: dict[str, Any]) -> ConfigSnapshot:
        sanitized = _validate_updates(updates)
        document = self._read_document()
        current = {str(k): str(v) for k, v in document.get("current", {}).items()}
        next_values = {**current, **sanitized}
        created_at = time.time()
        snapshot = ConfigSnapshot(
            version=_make_version(next_values, created_at),
            values=next_values,
            actor_open_id=actor_open_id,
            changed_keys=sorted(sanitized),
            created_at=created_at,
        )
        history = list(document.get("history", []))
        history.append({
            "version": snapshot.version,
            "values": snapshot.values,
            "actor_open_id": snapshot.actor_open_id,
            "changed_keys": snapshot.changed_keys,
            "created_at": snapshot.created_at,
        })
        self._write_document({"current": next_values, "history": history})
        return snapshot

    def get_plain(self) -> dict[str, str]:
        return {str(k): str(v) for k, v in self._read_document().get("current", {}).items()}

    def get_redacted(self) -> dict[str, str]:
        plain = self.get_plain()
        return {key: ("********" if key in SECRET_KEYS and value else value) for key, value in plain.items()}

    def history(self) -> list[ConfigSnapshot]:
        items = self._read_document().get("history", [])
        return [
            ConfigSnapshot(
                version=item["version"],
                values={str(k): str(v) for k, v in item["values"].items()},
                actor_open_id=item["actor_open_id"],
                changed_keys=list(item["changed_keys"]),
                created_at=float(item["created_at"]),
            )
            for item in items
        ]


def bootstrap_snapshot_from_env(actor_open_id: str) -> ConfigSnapshot:
    values = {key: os.environ[key] for key in EDITABLE_KEYS if os.environ.get(key)}
    created_at = time.time()
    return ConfigSnapshot(
        version=_make_version(values, created_at),
        values=values,
        actor_open_id=actor_open_id,
        changed_keys=sorted(values),
        created_at=created_at,
    )


def default_config_center() -> ConfigCenter:
    key = os.environ["XHS_CONFIG_ENCRYPTION_KEY"]
    path = os.environ.get("XHS_CONFIG_CENTER_PATH", ".xhs-config/config-center.enc")
    return ConfigCenter(path=path, encryption_key=key)
```

- [ ] **Step 4: Add phase-2 env examples**

Append to `.env.example`:

```env
# Phase 2 config center. Generate with:
# python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
XHS_CONFIG_ENCRYPTION_KEY=
XHS_CONFIG_CENTER_PATH=.xhs-config/config-center.enc
```

- [ ] **Step 5: Run green tests**

Run:

```powershell
uv run pytest tests/test_config_center.py -q
```

Expected: `4 passed`.

- [ ] **Step 6: Commit**

```bash
git add config_center.py tests/test_config_center.py .env.example
git commit -m "feat: add encrypted config center"
```

## Task 2: Process-Local Model Registry

**Files:**
- Create: `model_registry.py`
- Modify: `models.py`
- Test: `tests/test_model_registry.py`

- [ ] **Step 1: Write failing registry tests**

Create `tests/test_model_registry.py`:

```python
import pytest

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from model_registry import ModelRegistry
from models import ModelCandidate, ModelRouterMiddleware


def _candidate(version: str, model_id: str) -> ModelCandidate:
    return ModelCandidate(
        gateway_name=f"gateway-{version}",
        model_id=model_id,
        model=FakeListChatModel(responses=[f"{version}:{model_id}"]),
    )


def test_registry_reload_replaces_active_pool():
    registry = ModelRegistry()
    registry.replace(version="v1", pool=[_candidate("v1", "gpt-4o")])
    assert registry.status()["version"] == "v1"
    assert registry.status()["active_models"] == ["gpt-4o"]

    registry.replace(version="v2", pool=[_candidate("v2", "claude-sonnet-4-6")])
    assert registry.status()["version"] == "v2"
    assert registry.get_pool()[0].model_id == "claude-sonnet-4-6"


def test_router_reads_registry_on_each_sync_call():
    registry = ModelRegistry()
    registry.replace(version="v1", pool=[_candidate("v1", "gpt-4o")])
    middleware = ModelRouterMiddleware(registry)
    seen = []

    class Request:
        def override(self, model):
            seen.append(model)
            return self

    def handler(request):
        return "ok"

    assert middleware.wrap_model_call(Request(), handler) == "ok"
    registry.replace(version="v2", pool=[_candidate("v2", "claude-sonnet-4-6")])
    assert middleware.wrap_model_call(Request(), handler) == "ok"

    assert seen[0] is not seen[1]


@pytest.mark.asyncio
async def test_router_reads_registry_on_each_async_call():
    registry = ModelRegistry()
    registry.replace(version="v1", pool=[_candidate("v1", "gpt-4o")])
    middleware = ModelRouterMiddleware(registry)
    seen = []

    class Request:
        def override(self, model):
            seen.append(model)
            return self

    async def handler(request):
        return "ok"

    assert await middleware.awrap_model_call(Request(), handler) == "ok"
    registry.replace(version="v2", pool=[_candidate("v2", "claude-sonnet-4-6")])
    assert await middleware.awrap_model_call(Request(), handler) == "ok"

    assert seen[0] is not seen[1]
```

- [ ] **Step 2: Run red tests**

Run:

```powershell
uv run pytest tests/test_model_registry.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'model_registry'`.

- [ ] **Step 3: Implement `model_registry.py`**

Create `model_registry.py`:

```python
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from models import ModelCandidate


@dataclass(frozen=True)
class RegistrySnapshot:
    version: str
    pool: list[ModelCandidate]
    loaded_at: float
    last_error: str | None = None


class ModelRegistry:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot = RegistrySnapshot(version="", pool=[], loaded_at=0.0)

    def replace(self, version: str, pool: list[ModelCandidate]) -> None:
        if not pool:
            raise ValueError("ModelRegistry requires at least one model candidate")
        with self._lock:
            self._snapshot = RegistrySnapshot(version=version, pool=list(pool), loaded_at=time.time())

    def record_error(self, message: str) -> None:
        with self._lock:
            current = self._snapshot
            self._snapshot = RegistrySnapshot(
                version=current.version,
                pool=current.pool,
                loaded_at=current.loaded_at,
                last_error=message,
            )

    def get_pool(self) -> list[ModelCandidate]:
        with self._lock:
            return list(self._snapshot.pool)

    def status(self) -> dict[str, object]:
        with self._lock:
            return {
                "version": self._snapshot.version,
                "loaded_at": self._snapshot.loaded_at,
                "active_models": [candidate.model_id for candidate in self._snapshot.pool],
                "last_error": self._snapshot.last_error,
                "hot_reload_coverage": {
                    "main_agent": True,
                    "server_async": True,
                    "subagents": True,
                    "rubric": False,
                },
            }
```

- [ ] **Step 4: Update `models.py` router to accept registry**

In `models.py`, change `ModelRouterMiddleware.__init__` and `_ordered_candidates`:

```python
from typing import Protocol


class ModelPoolProvider(Protocol):
    def get_pool(self) -> list[ModelCandidate]:
        raise NotImplementedError
```

Replace the constructor:

```python
    def __init__(self, pool: list[ModelCandidate] | ModelPoolProvider) -> None:
        super().__init__()
        self._pool_provider = pool if hasattr(pool, "get_pool") else None
        self._pool = pool if not hasattr(pool, "get_pool") else []
        self._health: dict[tuple[str, str], float] = {}
        self._rr = 0
```

Add:

```python
    def _current_pool(self) -> list[ModelCandidate]:
        if self._pool_provider is not None:
            return self._pool_provider.get_pool()
        return list(self._pool)
```

Change `_mark_unhealthy`:

```python
    def _mark_unhealthy(self, candidate: ModelCandidate) -> None:
        self._health[(candidate.gateway_name, candidate.model_id)] = time.monotonic() + _COOLDOWN_SECONDS
```

Change `_is_cooling`:

```python
    def _is_cooling(self, candidate: ModelCandidate) -> bool:
        until = self._health.get((candidate.gateway_name, candidate.model_id))
        return until is not None and time.monotonic() < until
```

Change `_ordered_candidates` to read the current pool:

```python
    def _ordered_candidates(self) -> list[ModelCandidate]:
        pool = self._current_pool()
        if not pool:
            raise ValueError("ModelRouterMiddleware 需要非空候选池")
        n = len(pool)
        rotated = [pool[(self._rr + i) % n] for i in range(n)]
        self._rr = (self._rr + 1) % n
        healthy = [c for c in rotated if not self._is_cooling(c)]
        cooling = [c for c in rotated if self._is_cooling(c)]
        return healthy + cooling
```

Keep `build_router_middleware(pool)` compatible:

```python
def build_router_middleware(pool: list[ModelCandidate] | ModelPoolProvider) -> ModelRouterMiddleware:
    return ModelRouterMiddleware(pool)
```

- [ ] **Step 5: Run green tests**

Run:

```powershell
uv run pytest tests/test_model_registry.py tests/test_models.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add model_registry.py models.py tests/test_model_registry.py
git commit -m "feat: add reloadable model registry"
```

## Task 3: Config-Driven Pool Loading

**Files:**
- Modify: `models.py`
- Modify: `model_registry.py`
- Test: `tests/test_model_registry.py`

- [ ] **Step 1: Write failing config-driven reload test**

Append to `tests/test_model_registry.py`:

```python
def test_registry_reload_from_config_snapshot(monkeypatch):
    import models as models_mod
    from config_center import ConfigSnapshot

    def fake_discover(base_url, api_key):
        assert base_url == "https://gateway.example/v1"
        assert api_key == "sk-secret"
        return ["gpt-4o"]

    monkeypatch.setattr(models_mod, "discover_models", fake_discover)
    monkeypatch.setattr(
        models_mod,
        "_build_chat_model",
        lambda model_id, base_url, api_key: FakeListChatModel(responses=[model_id]),
    )

    registry = ModelRegistry()
    snapshot = ConfigSnapshot(
        version="v-center",
        values={
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://gateway.example/v1",
            "LLM_API_KEY": "sk-secret",
            "LLM_QUALITY_MODELS": "gpt-4o",
        },
        actor_open_id="ou_admin",
        changed_keys=["LLM_QUALITY_MODELS"],
        created_at=1.0,
    )

    registry.reload_from_config(snapshot)

    assert registry.status()["version"] == "v-center"
    assert registry.status()["active_models"] == ["gpt-4o"]
```

- [ ] **Step 2: Run red test**

Run:

```powershell
uv run pytest tests/test_model_registry.py::test_registry_reload_from_config_snapshot -q
```

Expected: FAIL with `AttributeError: 'ModelRegistry' object has no attribute 'reload_from_config'`.

- [ ] **Step 3: Add config-driven pool builder to `models.py`**

Append to `models.py`:

```python
def build_pool_from_config(values: dict[str, str]) -> list[ModelCandidate]:
    gateways: list[tuple[str, str, str]] = []
    base = values.get("LLM_BASE_URL", "").strip()
    key = values.get("LLM_API_KEY", "").strip()
    if base and key:
        gateways.append(("gateway_1", base, key))
    for n in (2, 3):
        b = values.get(f"LLM_GATEWAY_{n}_BASE_URL", "").strip()
        k = values.get(f"LLM_GATEWAY_{n}_API_KEY", "").strip()
        if b and k:
            gateways.append((f"gateway_{n}", b, k))

    whitelist = [m.strip() for m in values.get("LLM_QUALITY_MODELS", "").split(",") if m.strip()]
    whitelist_set = set(whitelist)
    pool: list[ModelCandidate] = []

    old_provider = os.environ.get("LLM_PROVIDER")
    if values.get("LLM_PROVIDER"):
        os.environ["LLM_PROVIDER"] = values["LLM_PROVIDER"]
    try:
        for gw_name, base_url, api_key in gateways:
            available = discover_models(base_url, api_key)
            if not available:
                continue
            for model_id in available:
                if model_id in whitelist_set:
                    pool.append(ModelCandidate(
                        gateway_name=gw_name,
                        model_id=model_id,
                        model=_build_chat_model(model_id, base_url, api_key),
                    ))
        if not pool and gateways and whitelist:
            gw_name, base_url, api_key = gateways[0]
            fallback_id = whitelist[0]
            pool.append(ModelCandidate(
                gateway_name=gw_name,
                model_id=fallback_id,
                model=_build_chat_model(fallback_id, base_url, api_key),
            ))
    finally:
        if old_provider is None:
            os.environ.pop("LLM_PROVIDER", None)
        else:
            os.environ["LLM_PROVIDER"] = old_provider

    if not pool:
        raise RuntimeError("无法从配置中心构造模型池")
    return pool
```

- [ ] **Step 4: Add `reload_from_config` to registry**

In `model_registry.py`, import:

```python
from config_center import ConfigSnapshot
from models import build_pool_from_config
```

Add method:

```python
    def reload_from_config(self, snapshot: ConfigSnapshot) -> None:
        try:
            pool = build_pool_from_config(snapshot.values)
            self.replace(version=snapshot.version, pool=pool)
        except Exception as exc:
            self.record_error(str(exc))
            raise
```

- [ ] **Step 5: Run green tests**

Run:

```powershell
uv run pytest tests/test_model_registry.py tests/test_models.py tests/test_config_center.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add models.py model_registry.py tests/test_model_registry.py
git commit -m "feat: load model registry from config center"
```

## Task 4: Wire Agent And Subagents To Shared Registry

**Files:**
- Modify: `agent.py`
- Modify: `subagents.py`
- Modify: `tests/test_agent_assembly.py`

- [ ] **Step 1: Write failing assembly assertion**

Append to `tests/test_agent_assembly.py`:

```python
def test_agent_exposes_shared_model_registry(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://test-gw/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "gpt-4o")
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")
    monkeypatch.setenv("DISCOVER_MODELS", "false")

    import importlib
    import agent as agent_mod
    agent_mod = importlib.reload(agent_mod)

    assert agent_mod.model_registry.status()["active_models"]
    assert agent_mod.model_registry.status()["hot_reload_coverage"]["main_agent"] is True
    assert agent_mod.model_registry.status()["hot_reload_coverage"]["subagents"] is True
    assert agent_mod.model_registry.status()["hot_reload_coverage"]["rubric"] is False
```

- [ ] **Step 2: Run red test**

Run:

```powershell
uv run pytest tests/test_agent_assembly.py::test_agent_exposes_shared_model_registry -q
```

Expected: FAIL with `AttributeError: module 'agent' has no attribute 'model_registry'`.

- [ ] **Step 3: Wire `agent.py`**

In `agent.py`, import:

```python
from model_registry import ModelRegistry
```

After `pool = build_pool()`, add:

```python
model_registry = ModelRegistry()
model_registry.replace(version=os.environ.get("XHS_CONFIG_VERSION", "env-bootstrap"), pool=list(pool))
```

Change middleware:

```python
middleware=[build_retry_middleware(), rubric_middleware, build_router_middleware(model_registry)],
```

Do not change `rubric_middleware` yet. It remains startup-bound and explicitly excluded from no-restart coverage.

- [ ] **Step 4: Wire `subagents.py` without building an independent pool**

Replace any module-level independent pool in `subagents.py` with a small factory:

```python
from models import build_router_middleware


def build_baokuan_analyst(registry):
    return {
        "name": "baokuan-analyst",
        "description": baokuan_analyst["description"],
        "prompt": baokuan_analyst["prompt"],
        "tools": baokuan_analyst["tools"],
        "middleware": [build_router_middleware(registry)],
    }
```

In `agent.py`, import and use:

```python
from subagents import build_baokuan_analyst
```

Replace:

```python
subagents=[baokuan_analyst],
```

with:

```python
subagents=[build_baokuan_analyst(model_registry)],
```

- [ ] **Step 5: Run green tests**

Run:

```powershell
uv run pytest tests/test_agent_assembly.py tests/test_model_registry.py tests/test_models.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add agent.py subagents.py tests/test_agent_assembly.py
git commit -m "feat: wire agents to shared model registry"
```

## Task 5: Backend Config Status Command

**Files:**
- Modify: `tools/cli_runner.py`
- Modify: `web/src/app/api/backend/status/route.ts`
- Test: `tests/test_cli_runner.py`

- [ ] **Step 1: Write failing status test**

Append to `tests/test_cli_runner.py`:

```python
def test_config_status_reads_redacted_center(tmp_path, capsys):
    from cryptography.fernet import Fernet
    from config_center import ConfigCenter

    key = Fernet.generate_key().decode()
    path = tmp_path / "config.enc"
    center = ConfigCenter(path=path, encryption_key=key)
    center.save(actor_open_id="ou_admin", updates={
        "LLM_PROVIDER": "openai",
        "LLM_API_KEY": "sk-secret",
        "LLM_QUALITY_MODELS": "gpt-4o",
    })

    args = argparse.Namespace(config_path=str(path), encryption_key=key)
    cli_runner.handle_config_status(args)

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["configs"]["LLM_API_KEY"] == "********"
    assert payload["configs"]["LLM_QUALITY_MODELS"] == "gpt-4o"
```

- [ ] **Step 2: Run red test**

Run:

```powershell
uv run pytest tests/test_cli_runner.py::test_config_status_reads_redacted_center -q
```

Expected: FAIL with `AttributeError: module 'tools.cli_runner' has no attribute 'handle_config_status'`.

- [ ] **Step 3: Add config status command**

In `tools/cli_runner.py`, import:

```python
from config_center import ConfigCenter
```

Add handler:

```python
def handle_config_status(args):
    center = ConfigCenter(path=args.config_path, encryption_key=args.encryption_key)
    print(json.dumps({"ok": True, "configs": center.get_redacted()}, ensure_ascii=False))
```

Update parser choices:

```python
parser.add_argument("--action", choices=["save-uat", "uat-status", "chats", "sync", "notify", "config-status"], required=True)
parser.add_argument("--config-path")
parser.add_argument("--encryption-key")
```

Wire:

```python
    elif args.action == "config-status":
        handle_config_status(args)
```

- [ ] **Step 4: Update backend status route**

In `web/src/app/api/backend/status/route.ts`, keep admin auth and add phase-2 fields:

```ts
const configCenterEnabled = Boolean(process.env.XHS_CONFIG_ENCRYPTION_KEY && process.env.XHS_CONFIG_CENTER_PATH);
```

Return:

```ts
config_center_enabled: configCenterEnabled,
hot_reload_supported_paths: {
  main_agent: true,
  server_async: true,
  subagents: true,
  rubric: false,
},
hot_reload_message:
  "Only ModelRouterMiddleware paths are hot-reload eligible. Rubric remains restart-required in phase 2.",
```

- [ ] **Step 5: Run checks**

Run:

```powershell
uv run pytest tests/test_cli_runner.py tests/test_config_center.py -q
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tools/cli_runner.py tests/test_cli_runner.py web/src/app/api/backend/status/route.ts
git commit -m "feat: expose config center status"
```

## Task 6: Next Config API Uses Config Center In Phase 2 Mode

**Files:**
- Modify: `web/src/app/api/config/route.ts`
- Modify: `web/src/lib/server/config-store.ts`

- [ ] **Step 1: Add phase-2 mode helpers**

In `web/src/lib/server/config-store.ts`, add:

```ts
export function isConfigCenterEnabled(): boolean {
  return Boolean(process.env.XHS_CONFIG_ENCRYPTION_KEY && process.env.XHS_CONFIG_CENTER_PATH);
}

export function configCenterRunnerArgs(action: "config-status") {
  if (!process.env.XHS_CONFIG_ENCRYPTION_KEY || !process.env.XHS_CONFIG_CENTER_PATH) {
    throw new Error("Config center is not enabled");
  }
  return [
    "--action",
    action,
    "--config-path",
    process.env.XHS_CONFIG_CENTER_PATH,
    "--encryption-key",
    process.env.XHS_CONFIG_ENCRYPTION_KEY,
  ];
}
```

- [ ] **Step 2: Update `GET /api/config`**

In `web/src/app/api/config/route.ts`, import:

```ts
import { isConfigCenterEnabled } from "@/lib/server/config-store";
import { forwardToInternalServer } from "@/lib/server/internal-client";
```

Inside `GET`, after `await requireAdmin();`:

```ts
if (isConfigCenterEnabled()) {
  const resp = await forwardToInternalServer("/_internal/config-status", "GET", "system");
  const data = await resp.json();
  return jsonNoStore({ ok: true, configs: data.configs, source: "config-center" });
}
```

Keep the existing `.env` response as fallback for phase 1 mode.

- [ ] **Step 3: Update `internal-client.ts` config-status bridge**

In `web/src/lib/server/internal-client.ts`, add branch:

```ts
  } else if (pathName === "/_internal/config-status") {
    action = "config-status";
    runnerArgs.push(
      "--action",
      "config-status",
      "--config-path",
      String(process.env.XHS_CONFIG_CENTER_PATH || ""),
      "--encryption-key",
      String(process.env.XHS_CONFIG_ENCRYPTION_KEY || ""),
    );
```

This reads the config store but does not reload the LangGraph process.

- [ ] **Step 4: Run checks**

Run:

```powershell
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
```

Expected: TypeScript passes; ESLint has 0 errors.

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/server/config-store.ts web/src/lib/server/internal-client.ts web/src/app/api/config/route.ts
git commit -m "feat: read config api from config center"
```

## Task 7: Document Hot Reload Limits And Final Quality Gate

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-19-multi-user-hardening-and-config-evolution-design.md`

- [ ] **Step 1: Add README section**

Append to `README.md`:

```md
## 第二阶段配置中心与热切边界

- 配置中心由 `XHS_CONFIG_CENTER_PATH` 指向的加密文件提供，`XHS_CONFIG_ENCRYPTION_KEY` 是启动级密钥，不能通过 UI 修改。
- 已纳入无重启热切的路径：主 agent 的 `ModelRouterMiddleware` sync/async 调用、子 agent 的 `ModelRouterMiddleware` 调用。
- 未纳入无重启热切的路径：启动时静态构造的 rubric 评分模型。该路径仍需要受控重启，直到改为 registry-backed model factory。
- `tools/cli_runner.py` 可读取配置中心状态，但不能 reload 常驻 LangGraph 进程内存。
- 不 fork DeepAgents，不 monkey-patch DeepAgents，不访问 compiled graph 私有字段。
```

- [ ] **Step 2: Update spec status note**

In `docs/superpowers/specs/2026-06-19-multi-user-hardening-and-config-evolution-design.md`, under `### 4.3 无重启 ModelRegistry 热切换`, add:

```md
实施备注:

- 第二阶段首版只把 `ModelRouterMiddleware` 覆盖的 sync/async 主 agent 与子 agent 路径纳入热切。
- `RubricMiddleware` 当前接收启动时静态模型实例，首版明确标记为 restart-required。
- `cli_runner.py` 是子进程桥接工具，不能作为进程内 registry reload 通道。
```

- [ ] **Step 3: Run complete checks**

Run:

```powershell
uv run pytest
cd E:\小红书智能体\web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
.\node_modules\.bin\eslint.CMD .
```

Expected:

- Backend: all tests pass.
- Frontend: TypeScript passes.
- ESLint: 0 errors; existing warnings are acceptable.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/specs/2026-06-19-multi-user-hardening-and-config-evolution-design.md
git commit -m "docs: document phase two hot reload limits"
```

## Self-Review

- Spec coverage: This plan covers config center, encrypted secrets, audit history, registry hot reload, native middleware boundaries, config status, Next config reads, and explicit hot-reload limits. It does not implement role table, reveal/rotation UI, shared dataset mode, or draft update workflow; those remain separate second-stage follow-up slices because each is independently testable and not required to prove model hot reload.
- Red-flag scan: no blocked drafting instructions remain. The rubric path is not deferred vaguely; it is explicitly marked restart-required and documented.
- Type consistency: `ConfigSnapshot.version`, `ConfigSnapshot.values`, `ModelRegistry.replace`, `ModelRegistry.reload_from_config`, `ModelRouterMiddleware`, and `forwardToInternalServer("/_internal/config-status")` names are consistent across tasks.
