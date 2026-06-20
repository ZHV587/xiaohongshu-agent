from __future__ import annotations

import hmac
import json
import os
import shlex
from dataclasses import dataclass

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from config_center import ConfigCenter, ConfigValidationError
from tools.lark_cli import lark_cli
from tools.runtime_identity import identity_config
from tools.uat_store import get_uat, save_uat


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
        snapshot = _config_center().save(actor_open_id=actor.open_id, updates=configs)
        return _json_ok({"ok": True, "version": snapshot.version, "changed_keys": snapshot.changed_keys})
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
]
