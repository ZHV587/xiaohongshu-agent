from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg import errors as pg_errors
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from data_foundation.db import connect
from data_foundation.permissions import default_tenant_id
from data_foundation.repositories.user_skill import UserSkillRepository
from data_foundation.user_skill_service import (
    DEFINITION_FIELDS,
    SkillDefinition,
    SkillDefinitionError,
    UserSkillCompiler,
    definition_from_version,
)


logger = logging.getLogger(__name__)


@contextmanager
def _repository() -> Iterator[UserSkillRepository]:
    conn = connect()
    try:
        yield UserSkillRepository(conn)
    finally:
        conn.close()


def _error(status: int, code: str, message: str, *, field: str | None = None) -> JSONResponse:
    payload: dict[str, Any] = {"ok": False, "error": message, "code": code}
    if field:
        payload["fieldErrors"] = {field: message}
    response = JSONResponse(payload, status_code=status)
    response.headers["Cache-Control"] = "no-store"
    return response


def _ok(payload: dict[str, Any], *, status: int = 200) -> JSONResponse:
    response = JSONResponse({"ok": True, **payload}, status_code=status)
    response.headers["Cache-Control"] = "no-store"
    return response


def _require_actor(request: Request):
    from data_foundation.internal_api import require_user

    return require_user(request)


async def _json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if len(raw) > 64 * 1024:
        raise SkillDefinitionError("SKILL_PAYLOAD_TOO_LARGE", "Request body is too large")
    try:
        body = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        raise SkillDefinitionError("SKILL_INVALID_JSON", "Request body must be valid JSON") from exc
    if not isinstance(body, dict):
        raise SkillDefinitionError("SKILL_INVALID_BODY", "Request body must be an object")
    return body


def _definition_body(body: dict[str, Any], *, extra_fields: set[str] | None = None) -> SkillDefinition:
    allowed = set(DEFINITION_FIELDS) | set(extra_fields or set())
    unknown = sorted(set(body) - allowed)
    if unknown:
        # 让编译器对扩权字段给出专门错误码；普通未知字段同样由它统一裁决。
        UserSkillCompiler.validate({key: body[key] for key in body if key not in (extra_fields or set())})
    return UserSkillCompiler.validate({key: body[key] for key in DEFINITION_FIELDS if key in body})


def _definition_payload(definition: SkillDefinition) -> dict[str, Any]:
    return {
        "displayName": definition.display_name,
        "description": definition.description,
        "instructions": definition.instructions,
        "triggerExamples": list(definition.trigger_examples),
        "nonTriggerExamples": list(definition.non_trigger_examples),
        "tags": list(definition.tags),
    }


def _version_payload(version: Any, runtime_name: str) -> dict[str, Any]:
    definition = definition_from_version(version)
    return {
        "version": version.version,
        "contentHash": version.content_hash,
        "createdAt": version.created_at.isoformat(),
        "definition": _definition_payload(definition),
        "skillMd": UserSkillCompiler.compile(runtime_name, definition),
    }


def _skill_payload(skill: Any, *, versions: list[Any] | None = None) -> dict[str, Any]:
    payload = {
        "id": skill.id,
        "runtimeName": skill.runtime_name,
        "status": skill.status,
        "latestVersion": skill.latest_version,
        "publishedVersion": skill.published_version,
        "createdAt": skill.created_at.isoformat(),
        "updatedAt": skill.updated_at.isoformat(),
        "latest": _version_payload(skill.latest_definition, skill.runtime_name),
    }
    if versions is not None:
        payload["versions"] = [_version_payload(version, skill.runtime_name) for version in versions]
    return payload


def _skill_summary_payload(skill: Any) -> dict[str, Any]:
    definition = definition_from_version(skill.latest_definition)
    return {
        "id": skill.id,
        "runtimeName": skill.runtime_name,
        "status": skill.status,
        "latestVersion": skill.latest_version,
        "publishedVersion": skill.published_version,
        "displayName": definition.display_name,
        "description": definition.description,
        "tags": list(definition.tags),
        "updatedAt": skill.updated_at.isoformat(),
    }


def _version_number(value: Any, *, required: bool) -> int | None:
    if value is None and not required:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SkillDefinitionError("SKILL_INVALID_INPUT", "version must be a positive integer", field="version")
    return value


def _handle_exception(exc: Exception) -> JSONResponse:
    if isinstance(exc, SkillDefinitionError):
        if exc.code == "SKILL_PAYLOAD_TOO_LARGE":
            status = 413
        elif exc.code in {"SKILL_INVALID_JSON", "SKILL_INVALID_BODY"}:
            status = 400
        else:
            status = 422
        return _error(status, exc.code, str(exc), field=exc.field)
    if isinstance(exc, KeyError):
        return _error(404, "SKILL_NOT_FOUND", "Skill not found")
    if isinstance(exc, pg_errors.UniqueViolation):
        return _error(409, "SKILL_NAME_CONFLICT", "An active Skill with this name already exists")
    if isinstance(exc, RuntimeError):
        return _error(409, "SKILL_VERSION_CONFLICT", "Skill version changed; reload and retry")
    if isinstance(exc, ValueError):
        return _error(409, "SKILL_CONFLICT", str(exc))
    logger.error("user_skill_api_failed type=%s", type(exc).__name__)
    return _error(500, "SKILL_INTERNAL_ERROR", "Skill operation failed")


async def validate_skill(request: Request) -> JSONResponse:
    actor = _require_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        definition = _definition_body(await _json_body(request))
        return _ok(
            {
                "definition": _definition_payload(definition),
                "skillMd": UserSkillCompiler.compile("usr-preview", definition),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _handle_exception(exc)


async def list_skills(request: Request) -> JSONResponse:
    actor = _require_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        with _repository() as repo:
            skills = repo.list_skills(
                tenant_id=default_tenant_id(), owner_open_id=actor.open_id,
                include_archived=request.query_params.get("includeArchived") == "true",
            )
            revision = repo.get_catalog_revision(
                tenant_id=default_tenant_id(), owner_open_id=actor.open_id
            )
        return _ok({"skills": [_skill_summary_payload(skill) for skill in skills], "revision": revision})
    except Exception as exc:  # noqa: BLE001
        return _handle_exception(exc)


async def create_skill(request: Request) -> JSONResponse:
    actor = _require_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        definition = _definition_body(await _json_body(request))
        with _repository() as repo:
            skill = repo.create_skill(
                tenant_id=default_tenant_id(), owner_open_id=actor.open_id,
                actor_open_id=actor.open_id, **definition.storage_kwargs(),
            )
        return _ok({"skill": _skill_payload(skill)}, status=201)
    except Exception as exc:  # noqa: BLE001
        return _handle_exception(exc)


async def skill_detail(request: Request) -> JSONResponse:
    actor = _require_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        skill_id = request.query_params.get("skillId", "")
        with _repository() as repo:
            skill = repo.get_skill(
                tenant_id=default_tenant_id(), owner_open_id=actor.open_id, skill_id=skill_id
            )
            versions = repo.list_versions(
                tenant_id=default_tenant_id(), owner_open_id=actor.open_id, skill_id=skill_id
            )
        return _ok({"skill": _skill_payload(skill, versions=versions)})
    except Exception as exc:  # noqa: BLE001
        return _handle_exception(exc)


async def append_version(request: Request) -> JSONResponse:
    actor = _require_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        body = await _json_body(request)
        definition = _definition_body(body, extra_fields={"skillId", "expectedLatestVersion"})
        expected = body.get("expectedLatestVersion")
        if isinstance(expected, bool) or not isinstance(expected, int) or expected < 1:
            raise SkillDefinitionError(
                "SKILL_INVALID_INPUT", "expectedLatestVersion must be a positive integer",
                field="expectedLatestVersion",
            )
        with _repository() as repo:
            skill = repo.append_version(
                tenant_id=default_tenant_id(), owner_open_id=actor.open_id,
                actor_open_id=actor.open_id, skill_id=str(body.get("skillId") or ""),
                expected_latest_version=expected, **definition.storage_kwargs(),
            )
        return _ok({"skill": _skill_payload(skill)})
    except Exception as exc:  # noqa: BLE001
        return _handle_exception(exc)


async def _publication_action(request: Request, action: str) -> JSONResponse:
    actor = _require_actor(request)
    if isinstance(actor, JSONResponse):
        return actor
    try:
        body = await _json_body(request)
        allowed = {"skillId", "version"} if action in {"publish", "rollback"} else {"skillId"}
        unknown = sorted(set(body) - allowed)
        if unknown:
            raise SkillDefinitionError(
                "SKILL_UNKNOWN_FIELD", f"Field is not allowed: {unknown[0]}", field=unknown[0]
            )
        skill_id = str(body.get("skillId") or "")
        with _repository() as repo:
            common = {
                "tenant_id": default_tenant_id(), "owner_open_id": actor.open_id,
                "actor_open_id": actor.open_id, "skill_id": skill_id,
            }
            if action == "publish":
                skill = repo.publish_version(
                    **common, version=_version_number(body.get("version"), required=False)
                )
            elif action == "rollback":
                skill = repo.rollback_version(
                    **common, version=_version_number(body.get("version"), required=True)
                )
            elif action == "enable":
                current = repo.get_skill(
                    tenant_id=default_tenant_id(), owner_open_id=actor.open_id, skill_id=skill_id
                )
                if current.status != "disabled" or current.published_version is None:
                    raise ValueError("Only disabled Skills can be enabled")
                skill = repo.publish_version(**common, version=current.published_version)
            elif action == "disable":
                skill = repo.disable_skill(**common)
            else:
                skill = repo.archive_skill(**common)
            revision = repo.get_catalog_revision(
                tenant_id=default_tenant_id(), owner_open_id=actor.open_id
            )
        return _ok({"skill": _skill_payload(skill), "revision": revision})
    except Exception as exc:  # noqa: BLE001
        return _handle_exception(exc)


async def publish_skill(request: Request) -> JSONResponse:
    return await _publication_action(request, "publish")


async def rollback_skill(request: Request) -> JSONResponse:
    return await _publication_action(request, "rollback")


async def enable_skill(request: Request) -> JSONResponse:
    return await _publication_action(request, "enable")


async def disable_skill(request: Request) -> JSONResponse:
    return await _publication_action(request, "disable")


async def archive_skill(request: Request) -> JSONResponse:
    return await _publication_action(request, "archive")


user_skill_routes = [
    Route("/internal/user-skills/validate", validate_skill, methods=["POST"]),
    Route("/internal/user-skills", list_skills, methods=["GET"]),
    Route("/internal/user-skills/create", create_skill, methods=["POST"]),
    Route("/internal/user-skills/detail", skill_detail, methods=["GET"]),
    Route("/internal/user-skills/version", append_version, methods=["POST"]),
    Route("/internal/user-skills/publish", publish_skill, methods=["POST"]),
    Route("/internal/user-skills/rollback", rollback_skill, methods=["POST"]),
    Route("/internal/user-skills/enable", enable_skill, methods=["POST"]),
    Route("/internal/user-skills/disable", disable_skill, methods=["POST"]),
    Route("/internal/user-skills/archive", archive_skill, methods=["POST"]),
]
