from __future__ import annotations

import hmac
import json
import logging
import os
import shlex
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from config_center import ConfigCenter, ConfigValidationError, latest_config_snapshot
from data_foundation.db import connect
from data_foundation.permissions import default_tenant_id
from data_foundation.repository import ResourceRepository
from data_foundation.runtime_facts import module_fact, supervisor_runtime_fact, utc_now
from models import build_pool_from_config
from tools.lark_cli import lark_cli
from tools.runtime_identity import identity_config
from tools.uat_store import get_uat, save_uat


logger = logging.getLogger(__name__)

# 影响模型池的配置 key:本次 configs 含其一,才触发"构池验证 + 即时热重载"。
# 其余 key(飞书/bitable 字段名等)与模型池无关,改它们不探测、不 reload。
_MODEL_POOL_KEYS = frozenset({
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_QUALITY_MODELS",
    "LLM_GATEWAY_2_BASE_URL",
    "LLM_GATEWAY_2_API_KEY",
    "LLM_GATEWAY_3_BASE_URL",
    "LLM_GATEWAY_3_API_KEY",
})


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
    if claimed is not None:
        claimed_is_admin = claimed.strip().lower() in {"true", "1", "yes"}
        if claimed_is_admin != is_admin:
            logger.warning("internal_admin_claim_mismatch")
            raise PermissionError("Forbidden")
    return InternalActor(open_id=open_id, is_admin=is_admin)


def require_internal(request: Request) -> JSONResponse | None:
    return _require_internal_key(request)


def require_user(request: Request) -> InternalActor | JSONResponse:
    denied = _require_internal_key(request)
    if denied is not None:
        return denied
    try:
        actor = _actor_from_request(request)
    except PermissionError:
        return _json_error(403, "Forbidden")
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

        center = _config_center()
        merged = {**center.get_plain(), **{k: str(v or "") for k, v in configs.items()}}

        # 是否要"构池验证 + 即时热重载":须同时满足
        # (1) 本次改动涉及模型池 key;
        # (2) 合并后网关配置已完整(至少一个 base_url+key 齐全 且 白名单非空)。
        # 不完整(admin 分步配置中,如先填 key 再填 base_url)则只存不验证、不 reload,
        # 等配齐后再生效 —— 避免"半成品配置"被构池验证拦下导致无法分步保存。
        touches_model_pool = bool(_MODEL_POOL_KEYS & set(configs.keys()))
        gateway_complete = bool(
            merged.get("LLM_BASE_URL", "").strip()
            and merged.get("LLM_API_KEY", "").strip()
            and merged.get("LLM_QUALITY_MODELS", "").strip()
        )
        should_apply = touches_model_pool and gateway_complete

        # 构池验证(force 探测):白名单内无任一模型被网关探测确认可用 → 400、不落库。
        # 配置中心永远只存能构出非空池的完整模型配置。验证即构池,save 后 reload
        # 复用刚填的探测缓存(不再 force),零额外探测、0 延迟生效。
        if should_apply:
            try:
                build_pool_from_config(merged, force_discover=True)
            except Exception as exc:  # noqa: BLE001
                return _json_error(400, f"模型配置无可用模型,未保存:{exc}")

        snapshot = center.save(actor_open_id=actor.open_id, updates=configs)

        reloaded = None
        if should_apply:
            from agent import model_registry  # 延迟 import:同进程单例(N_WORKERS=1)

            reloaded = model_registry.reload_from_config(snapshot)

        payload = {"ok": True, "version": snapshot.version, "changed_keys": snapshot.changed_keys}
        if reloaded is not None:
            payload["model_pool_reloaded"] = reloaded
        return _json_ok(payload)
    except ConfigValidationError as exc:
        return _json_error(400, str(exc))
    except KeyError as exc:
        return _json_error(500, f"Config center missing required environment: {exc.args[0]}")


async def internal_feishu_status(request: Request) -> JSONResponse:
    actor = require_user(request)
    if isinstance(actor, JSONResponse):
        return actor
    if get_uat(actor.open_id):
        return _json_ok({"ok": True, "authorized": True})
    return _json_ok(
        {
            "ok": True,
            "authorized": False,
            "error": "Feishu user authorization is missing or expired.",
        }
    )


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
    fallback = {"ok": True, "name": "小红书爆单手册", "space_id": fallback_space_id}
    if not get_uat(actor.open_id):
        return _json_ok(fallback)

    try:
        command = shlex.join(["wiki", "spaces", "get", "--space-id", fallback_space_id])
        raw = lark_cli(command, config=identity_config(actor.open_id))
        if raw.startswith("Error") or "error" in raw.lower() or raw.startswith("⚠️"):
            return _json_ok(fallback)
        data = json.loads(raw)
        space_name = data.get("data", {}).get("space", {}).get("name") or fallback["name"]
        return _json_ok({"ok": True, "name": space_name, "space_id": fallback_space_id})
    except Exception:
        return _json_ok(fallback)


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def startup_runtime_fact(snapshot, *, observed_at: str) -> dict:
    data = {
        "instance_id": None,
        "started_at": None,
        "stopped_at": None,
    }
    status = "unavailable"
    if snapshot is not None:
        status = snapshot.status
        data = {
            "instance_id": snapshot.instance_id,
            "started_at": snapshot.started_at,
            "stopped_at": snapshot.stopped_at,
        }
    return module_fact(
        status=status,
        source="process",
        observed_at=observed_at,
        stale_after_seconds=30,
        data=data,
    )


def _runtime_state(request: Request, name: str):
    value = getattr(request.state, name, None)
    if value is not None:
        return value
    return getattr(request.app.state, name, None)


def scheduler_runtime_fact(supervisor, *, observed_at: str) -> dict:
    if supervisor is None:
        return module_fact(
            status="unavailable",
            source="instance",
            observed_at=observed_at,
            stale_after_seconds=30,
            data={
                "instance_id": None,
                "accepting_work": False,
                "last_cycle_started_at": None,
                "last_cycle_finished_at": None,
                "last_cycle_status": "unavailable",
            },
            error={
                "code": "RUNTIME_FACTS_SUPERVISOR_UNAVAILABLE",
                "summary": "Supervisor runtime facts unavailable",
            },
        )
    return supervisor_runtime_fact(supervisor, observed_at=observed_at)


def database_runtime_fact(observed_at: str) -> dict:
    conn = connect()
    try:
        data = ResourceRepository(conn).runtime_fact_aggregates(default_tenant_id())
    finally:
        conn.close()
    return module_fact(
        status="healthy",
        source="database",
        observed_at=observed_at,
        stale_after_seconds=30,
        data=_json_safe(data),
    )


def unavailable_database_runtime_fact(*, observed_at: str) -> dict:
    return module_fact(
        status="unavailable",
        source="database",
        observed_at=observed_at,
        stale_after_seconds=30,
        data={},
        error={
            "code": "RUNTIME_FACTS_DATABASE_UNAVAILABLE",
            "summary": "Database runtime facts unavailable",
        },
    )


def runtime_facts_payload(request: Request) -> dict:
    observed_at = utc_now()
    try:
        database = database_runtime_fact(observed_at)
    except Exception:
        logger.warning("database_runtime_facts_failed")
        database = unavailable_database_runtime_fact(observed_at=observed_at)

    modules = {
        "startup": startup_runtime_fact(
            _runtime_state(request, "runtime_snapshot"),
            observed_at=observed_at,
        ),
        "scheduler": scheduler_runtime_fact(
            _runtime_state(request, "supervisor"),
            observed_at=observed_at,
        ),
        "database": database,
    }
    return {"ok": True, "observed_at": observed_at, "modules": modules}


async def internal_health_facts(request: Request) -> JSONResponse:
    actor = require_admin(request)
    if isinstance(actor, JSONResponse):
        return actor
    return _json_ok(runtime_facts_payload(request))


def data_foundation_status_payload() -> dict:
    conn = connect()
    try:
        return ResourceRepository(conn).data_foundation_status(default_tenant_id())
    finally:
        conn.close()


async def internal_data_foundation_status(request: Request) -> JSONResponse:
    actor = require_admin(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        return _json_ok({"ok": True, "status": data_foundation_status_payload()})
    except Exception:
        logger.warning("internal_data_foundation_status_failed")
        return _json_error(503, "Data foundation status unavailable")


def _config_center() -> ConfigCenter:
    return ConfigCenter(
        path=os.environ["XHS_CONFIG_CENTER_PATH"],
        encryption_key=os.environ["XHS_CONFIG_ENCRYPTION_KEY"],
    )


def _config_version(center: ConfigCenter) -> str:
    history = center.history()
    return history[-1].version if history else ""


internal_routes = [
    Route("/internal/ok", internal_ok, methods=["GET"]),
    Route("/internal/config", internal_config_get, methods=["GET"]),
    Route("/internal/config", internal_config_post, methods=["POST"]),
    Route("/internal/feishu/status", internal_feishu_status, methods=["GET"]),
    Route("/internal/feishu/uat", internal_feishu_uat_post, methods=["POST"]),
    Route("/internal/feishu/chats", internal_feishu_chats, methods=["GET"]),
    Route("/internal/feishu/wiki-space", internal_feishu_wiki_space, methods=["GET"]),
    Route("/internal/data-foundation/status", internal_data_foundation_status, methods=["GET"]),
    Route("/internal/health/facts", internal_health_facts, methods=["GET"]),
]
