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
    return _json_ok({"ok": True, "configs": {}, "version": ""})


internal_routes = [
    Route("/internal/ok", internal_ok, methods=["GET"]),
    Route("/internal/config", internal_config_get, methods=["GET"]),
]
