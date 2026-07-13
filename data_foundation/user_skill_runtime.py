from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Annotated, Any, NotRequired

from deepagents.middleware._utils import append_to_system_message
from deepagents.middleware.skills import SkillsMiddleware, SkillsState
from langchain.agents.middleware.types import PrivateStateAttr

from data_foundation.db import connect
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.repositories.user_skill import UserSkillRepository
from data_foundation.user_skill_service import UserSkillCompiler, definition_from_version

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from deepagents.middleware.skills import SkillSource
    from langchain_core.runnables import RunnableConfig
    from langgraph.runtime import Runtime


logger = logging.getLogger(__name__)

_TEST_MODE_DENIED_TOOLS = {
    "task",
    "write_file",
    "edit_file",
    "sync_feishu_resources",
    "save_generated_topic",
    "save_generated_copy",
    "save_user_feedback",
    "save_performance_metric",
    "save_session_snapshot",
    "sync_copy_to_feishu",
    "send_review_notification",
    "sync_topic_to_feishu",
    "sync_diagnosis_to_feishu",
    "adopt_online_notes",
    "lark_cli",
}


class RevisionAwareSkillsState(SkillsState):
    loaded_user_skills_revision: NotRequired[Annotated[int | None, PrivateStateAttr]]
    loaded_user_skills_scope: NotRequired[Annotated[str | None, PrivateStateAttr]]
    selected_user_skill: NotRequired[dict[str, Any] | None]
    resolved_user_skill: NotRequired[Annotated[dict[str, str] | None, PrivateStateAttr]]


def _load_revision(tenant_id: str, owner_open_id: str) -> int:
    with connect(connect_timeout=3, options="-c statement_timeout=5000") as conn:
        return UserSkillRepository(conn).get_catalog_revision(
            tenant_id=tenant_id,
            owner_open_id=owner_open_id,
        )


def _load_selected_document(
    tenant_id: str,
    owner_open_id: str,
    skill_id: str,
    version_id: str,
    mode: str,
):
    with connect(connect_timeout=3, options="-c statement_timeout=5000") as conn:
        return UserSkillRepository(conn).resolve_selected_document(
            tenant_id=tenant_id,
            owner_open_id=owner_open_id,
            skill_id=skill_id,
            version_id=version_id,
            mode=mode,
        )


class RevisionAwareSkillsMiddleware(SkillsMiddleware):
    """在官方 SkillsMiddleware 上增加按用户 revision 的同线程热刷新。"""

    state_schema = RevisionAwareSkillsState

    def __init__(
        self,
        *,
        backend,
        system_sources: Sequence[SkillSource],
        user_sources: Sequence[SkillSource],
        revision_loader: Callable[[str, str], int] = _load_revision,
        selected_loader: Callable[[str, str, str, str, str], Any] = _load_selected_document,
        actor_resolver: Callable[[object], str] = actor_from_config,
        tenant_resolver: Callable[[], str] = default_tenant_id,
        io_timeout_seconds: float = 6.0,
    ) -> None:
        super().__init__(backend=backend, sources=[*system_sources, *user_sources])
        self._revision_loader = revision_loader
        self._selected_loader = selected_loader
        self._actor_resolver = actor_resolver
        self._tenant_resolver = tenant_resolver
        self._io_timeout_seconds = io_timeout_seconds
        self._system_only = SkillsMiddleware(
            backend=backend,
            sources=system_sources,
            system_prompt=None,
        )

    @staticmethod
    def _clean_state(state: RevisionAwareSkillsState) -> RevisionAwareSkillsState:
        clean = dict(state)
        clean.pop("skills_metadata", None)
        clean.pop("skills_load_errors", None)
        return clean  # type: ignore[return-value]

    @staticmethod
    def _normalize_update(
        update: dict | None,
        revision: int | None,
        scope: str | None,
    ) -> dict:
        normalized = dict(update or {})
        normalized.setdefault("skills_metadata", [])
        normalized.setdefault("skills_load_errors", [])
        normalized["loaded_user_skills_revision"] = revision
        normalized["loaded_user_skills_scope"] = scope
        return normalized

    @staticmethod
    def _scope(tenant_id: str, actor_open_id: str) -> str:
        return hashlib.sha256(f"{tenant_id}\0{actor_open_id}".encode()).hexdigest()

    def _system_only_update(
        self,
        state: RevisionAwareSkillsState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> dict:
        try:
            update = self._system_only.before_agent(self._clean_state(state), runtime, config)
        except Exception as exc:  # noqa: BLE001 - fail closed;正文、DSN、SQL都不进入日志
            logger.warning("system_skill_reload_failed type=%s", type(exc).__name__)
            update = {"skills_metadata": []}
        normalized = self._normalize_update(update, None, None)
        normalized["skills_load_errors"] = ["User Skill catalog is temporarily unavailable"]
        return normalized

    @staticmethod
    def _turn_id(config: RunnableConfig) -> str | None:
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        value = configurable.get("turn_id") if isinstance(configurable, dict) else None
        return value if isinstance(value, str) and value else None

    def _selected_ref(
        self,
        state: RevisionAwareSkillsState,
        config: RunnableConfig,
    ) -> dict[str, str] | None:
        raw = state.get("selected_user_skill")
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise PermissionError("Selected User Skill is unavailable")
        allowed = {"skill_id", "version_id", "mode", "invocation_id"}
        if set(raw) != allowed or any(not isinstance(raw.get(key), str) for key in allowed):
            raise PermissionError("Selected User Skill is unavailable")
        if raw["invocation_id"] != self._turn_id(config):
            return None
        if raw["mode"] not in {"execute", "test"}:
            raise PermissionError("Selected User Skill is unavailable")
        return {key: str(raw[key]) for key in allowed}

    def _resolve_selected(
        self,
        state: RevisionAwareSkillsState,
        config: RunnableConfig,
        *,
        actor: str,
        tenant: str,
    ) -> dict[str, str] | None:
        selected = self._selected_ref(state, config)
        if selected is None:
            return None
        try:
            document = self._selected_loader(
                tenant,
                actor,
                selected["skill_id"],
                selected["version_id"],
                selected["mode"],
            )
        except Exception as exc:  # noqa: BLE001 - 对外统一不可用，避免泄露他人资源存在性
            logger.warning("selected_user_skill_rejected type=%s", type(exc).__name__)
            raise PermissionError("Selected User Skill is unavailable") from None
        return {
            "skill_id": document.skill_id,
            "version_id": document.definition.id,
            "runtime_name": document.runtime_name,
            "mode": selected["mode"],
            "invocation_id": selected["invocation_id"],
        }

    async def _aresolve_selected(
        self,
        state: RevisionAwareSkillsState,
        config: RunnableConfig,
        *,
        actor: str,
        tenant: str,
    ) -> dict[str, str] | None:
        selected = self._selected_ref(state, config)
        if selected is None:
            return None
        try:
            document = await asyncio.wait_for(
                asyncio.to_thread(
                    self._selected_loader,
                    tenant,
                    actor,
                    selected["skill_id"],
                    selected["version_id"],
                    selected["mode"],
                ),
                timeout=self._io_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("selected_user_skill_rejected type=%s", type(exc).__name__)
            raise PermissionError("Selected User Skill is unavailable") from None
        return {
            "skill_id": document.skill_id,
            "version_id": document.definition.id,
            "runtime_name": document.runtime_name,
            "mode": selected["mode"],
            "invocation_id": selected["invocation_id"],
        }

    async def _async_system_only_update(
        self,
        state: RevisionAwareSkillsState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> dict:
        try:
            update = await self._system_only.abefore_agent(self._clean_state(state), runtime, config)
        except Exception as exc:  # noqa: BLE001
            logger.warning("system_skill_reload_failed type=%s", type(exc).__name__)
            update = {"skills_metadata": []}
        normalized = self._normalize_update(update, None, None)
        normalized["skills_load_errors"] = ["User Skill catalog is temporarily unavailable"]
        return normalized

    def before_agent(
        self,
        state: RevisionAwareSkillsState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> dict | None:
        skills_update: dict | None
        try:
            actor = self._actor_resolver(config)
            tenant = self._tenant_resolver()
            revision = self._revision_loader(tenant, actor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("user_skill_revision_load_failed type=%s", type(exc).__name__)
            skills_update = self._system_only_update(state, runtime, config)
            try:
                actor = self._actor_resolver(config)
                tenant = self._tenant_resolver()
            except Exception:
                skills_update["resolved_user_skill"] = None
                return skills_update
            skills_update["resolved_user_skill"] = self._resolve_selected(
                state, config, actor=actor, tenant=tenant
            )
            return skills_update

        scope = self._scope(tenant, actor)
        if (
            "skills_metadata" in state
            and state.get("loaded_user_skills_revision") == revision
            and state.get("loaded_user_skills_scope") == scope
        ):
            skills_update = None
        else:
            try:
                update = super().before_agent(self._clean_state(state), runtime, config)
            except Exception as exc:  # noqa: BLE001
                logger.warning("user_skill_catalog_reload_failed type=%s", type(exc).__name__)
                skills_update = self._system_only_update(state, runtime, config)
            else:
                skills_update = self._normalize_update(update, revision, scope)
                if skills_update["skills_load_errors"]:
                    skills_update["loaded_user_skills_revision"] = None
                    skills_update["loaded_user_skills_scope"] = None
        resolved = self._resolve_selected(state, config, actor=actor, tenant=tenant)
        result = dict(skills_update or {})
        result["resolved_user_skill"] = resolved
        return result

    async def abefore_agent(
        self,
        state: RevisionAwareSkillsState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> dict | None:
        skills_update: dict | None
        try:
            actor = self._actor_resolver(config)
            tenant = self._tenant_resolver()
            revision = await asyncio.wait_for(
                asyncio.to_thread(self._revision_loader, tenant, actor),
                timeout=self._io_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("user_skill_revision_load_failed type=%s", type(exc).__name__)
            skills_update = await self._async_system_only_update(state, runtime, config)
            try:
                actor = self._actor_resolver(config)
                tenant = self._tenant_resolver()
            except Exception:
                skills_update["resolved_user_skill"] = None
                return skills_update
            skills_update["resolved_user_skill"] = await self._aresolve_selected(
                state, config, actor=actor, tenant=tenant
            )
            return skills_update

        scope = self._scope(tenant, actor)
        if (
            "skills_metadata" in state
            and state.get("loaded_user_skills_revision") == revision
            and state.get("loaded_user_skills_scope") == scope
        ):
            skills_update = None
        else:
            try:
                update = await super().abefore_agent(self._clean_state(state), runtime, config)
            except Exception as exc:  # noqa: BLE001
                logger.warning("user_skill_catalog_reload_failed type=%s", type(exc).__name__)
                skills_update = await self._async_system_only_update(state, runtime, config)
            else:
                skills_update = self._normalize_update(update, revision, scope)
                if skills_update["skills_load_errors"]:
                    skills_update["loaded_user_skills_revision"] = None
                    skills_update["loaded_user_skills_scope"] = None
        resolved = await self._aresolve_selected(state, config, actor=actor, tenant=tenant)
        result = dict(skills_update or {})
        result["resolved_user_skill"] = resolved
        return result

    def _selected_document_for_request(self, request):
        resolved = request.state.get("resolved_user_skill")
        if not isinstance(resolved, dict):
            return None
        actor = self._actor_resolver(request.runtime)
        tenant = self._tenant_resolver()
        try:
            return self._selected_loader(
                tenant,
                actor,
                resolved["skill_id"],
                resolved["version_id"],
                resolved["mode"],
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("selected_user_skill_reload_failed type=%s", type(exc).__name__)
            raise PermissionError("Selected User Skill is unavailable") from None

    def _request_with_selected_document(self, request, document):
        state = dict(request.state)
        state["skills_metadata"] = [
            item
            for item in state.get("skills_metadata", [])
            if not str(item.get("path", "")).startswith("/user-skills/")
        ]
        tools = request.tools
        resolved = request.state.get("resolved_user_skill")
        if isinstance(resolved, dict) and resolved.get("mode") == "test":
            tools = [
                tool
                for tool in request.tools
                if (
                    tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
                )
                not in _TEST_MODE_DENIED_TOOLS
            ]
        modified = super().modify_request(request.override(state=state, tools=tools))
        definition = definition_from_version(document.definition)
        skill_md = UserSkillCompiler.compile(document.runtime_name, definition)
        instruction = (
            "<explicit_user_skill>\n"
            "当前请求由用户显式选择了下方自定义 Skill，必须按该工作流执行，"
            "不要再选择其他用户 Skill。该 Skill 不增加任何工具、权限或文件访问能力；"
            "所有工具调用仍受当前 Agent 的工具清单、鉴权、审批和安全规则约束。\n\n"
            f"{skill_md}"
            "</explicit_user_skill>"
        )
        return modified.override(
            system_message=append_to_system_message(modified.system_message, instruction)
        )

    def wrap_model_call(self, request, handler):
        document = self._selected_document_for_request(request)
        if document is None:
            return super().wrap_model_call(request, handler)
        return handler(self._request_with_selected_document(request, document))

    async def awrap_model_call(self, request, handler):
        resolved = request.state.get("resolved_user_skill")
        if not isinstance(resolved, dict):
            return await super().awrap_model_call(request, handler)
        actor = self._actor_resolver(request.runtime)
        tenant = self._tenant_resolver()
        try:
            document = await asyncio.wait_for(
                asyncio.to_thread(
                    self._selected_loader,
                    tenant,
                    actor,
                    resolved["skill_id"],
                    resolved["version_id"],
                    resolved["mode"],
                ),
                timeout=self._io_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("selected_user_skill_reload_failed type=%s", type(exc).__name__)
            raise PermissionError("Selected User Skill is unavailable") from None
        return await handler(self._request_with_selected_document(request, document))

    def after_agent(self, state, runtime, config):
        return {"selected_user_skill": None, "resolved_user_skill": None}

    async def aafter_agent(self, state, runtime, config):
        return {"selected_user_skill": None, "resolved_user_skill": None}


__all__ = ["RevisionAwareSkillsMiddleware", "RevisionAwareSkillsState"]
