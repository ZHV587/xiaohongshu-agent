from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Annotated, NotRequired

from deepagents.middleware.skills import SkillsMiddleware, SkillsState
from langchain.agents.middleware.types import PrivateStateAttr

from data_foundation.db import connect
from data_foundation.permissions import actor_from_config, default_tenant_id
from data_foundation.repositories.user_skill import UserSkillRepository

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from deepagents.middleware.skills import SkillSource
    from langchain_core.runnables import RunnableConfig
    from langgraph.runtime import Runtime


logger = logging.getLogger(__name__)


class RevisionAwareSkillsState(SkillsState):
    loaded_user_skills_revision: NotRequired[Annotated[int | None, PrivateStateAttr]]
    loaded_user_skills_scope: NotRequired[Annotated[str | None, PrivateStateAttr]]


def _load_revision(tenant_id: str, owner_open_id: str) -> int:
    with connect(connect_timeout=3, options="-c statement_timeout=5000") as conn:
        return UserSkillRepository(conn).get_catalog_revision(
            tenant_id=tenant_id,
            owner_open_id=owner_open_id,
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
        actor_resolver: Callable[[object], str] = actor_from_config,
        tenant_resolver: Callable[[], str] = default_tenant_id,
        io_timeout_seconds: float = 6.0,
    ) -> None:
        super().__init__(backend=backend, sources=[*system_sources, *user_sources])
        self._revision_loader = revision_loader
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
        try:
            actor = self._actor_resolver(config)
            tenant = self._tenant_resolver()
            revision = self._revision_loader(tenant, actor)
        except Exception as exc:  # noqa: BLE001
            logger.warning("user_skill_revision_load_failed type=%s", type(exc).__name__)
            return self._system_only_update(state, runtime, config)

        scope = self._scope(tenant, actor)
        if (
            "skills_metadata" in state
            and state.get("loaded_user_skills_revision") == revision
            and state.get("loaded_user_skills_scope") == scope
        ):
            return None
        try:
            update = super().before_agent(self._clean_state(state), runtime, config)
        except Exception as exc:  # noqa: BLE001
            logger.warning("user_skill_catalog_reload_failed type=%s", type(exc).__name__)
            return self._system_only_update(state, runtime, config)
        normalized = self._normalize_update(update, revision, scope)
        if normalized["skills_load_errors"]:
            normalized["loaded_user_skills_revision"] = None
            normalized["loaded_user_skills_scope"] = None
        return normalized

    async def abefore_agent(
        self,
        state: RevisionAwareSkillsState,
        runtime: Runtime,
        config: RunnableConfig,
    ) -> dict | None:
        try:
            actor = self._actor_resolver(config)
            tenant = self._tenant_resolver()
            revision = await asyncio.wait_for(
                asyncio.to_thread(self._revision_loader, tenant, actor),
                timeout=self._io_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("user_skill_revision_load_failed type=%s", type(exc).__name__)
            return await self._async_system_only_update(state, runtime, config)

        scope = self._scope(tenant, actor)
        if (
            "skills_metadata" in state
            and state.get("loaded_user_skills_revision") == revision
            and state.get("loaded_user_skills_scope") == scope
        ):
            return None
        try:
            update = await super().abefore_agent(self._clean_state(state), runtime, config)
        except Exception as exc:  # noqa: BLE001
            logger.warning("user_skill_catalog_reload_failed type=%s", type(exc).__name__)
            return await self._async_system_only_update(state, runtime, config)
        normalized = self._normalize_update(update, revision, scope)
        if normalized["skills_load_errors"]:
            normalized["loaded_user_skills_revision"] = None
            normalized["loaded_user_skills_scope"] = None
        return normalized


__all__ = ["RevisionAwareSkillsMiddleware", "RevisionAwareSkillsState"]
