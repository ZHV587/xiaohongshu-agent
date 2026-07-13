from __future__ import annotations

from types import SimpleNamespace
import time

import pytest
from deepagents.backends.protocol import BackendProtocol, FileDownloadResponse, LsResult

from data_foundation.user_skill_runtime import RevisionAwareSkillsMiddleware


def _skill_md(name: str, description: str) -> bytes:
    return f'---\nname: "{name}"\ndescription: "{description}"\n---\n\n# Test\n'.encode()


class MutableSkillsBackend(BackendProtocol):
    def __init__(self) -> None:
        self.user_description = "用户流程 v1"
        self.calls = 0

    def ls(self, path: str) -> LsResult:
        self.calls += 1
        if path == "/skills/":
            return LsResult(entries=[{"path": "/skills/system-flow/", "is_dir": True}])
        if path == "/user-skills/":
            return LsResult(entries=[{"path": "/user-skills/usr-owner-flow/", "is_dir": True}])
        return LsResult(entries=[])

    async def als(self, path: str) -> LsResult:
        return self.ls(path)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        responses = []
        for path in paths:
            if "system-flow" in path:
                content = _skill_md("system-flow", "系统流程")
            else:
                content = _skill_md("usr-owner-flow", self.user_description)
            responses.append(FileDownloadResponse(path=path, content=content))
        return responses

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self.download_files(paths)


def _runtime():
    return SimpleNamespace(context=None, stream_writer=None, store=None)


def _middleware(backend: BackendProtocol, revision: list[int], actor: list[str] | None = None):
    actor = actor or ["ou-owner"]
    return RevisionAwareSkillsMiddleware(
        backend=backend,
        system_sources=[("/skills/", "系统")],
        user_sources=[("/user-skills/", "我的")],
        revision_loader=lambda tenant, actor: revision[0],
        actor_resolver=lambda config: actor[0],
        tenant_resolver=lambda: "tenant-a",
    )


def test_revision_change_reloads_metadata_in_the_same_thread():
    backend = MutableSkillsBackend()
    revision = [1]
    middleware = _middleware(backend, revision)
    state = {}

    first = middleware.before_agent(state, _runtime(), {})
    assert first and first["loaded_user_skills_revision"] == 1
    assert {item["description"] for item in first["skills_metadata"]} == {
        "系统流程",
        "用户流程 v1",
    }
    state.update(first)
    calls = backend.calls
    assert middleware.before_agent(state, _runtime(), {}) is None
    assert backend.calls == calls

    backend.user_description = "用户流程 v2"
    revision[0] = 2
    second = middleware.before_agent(state, _runtime(), {})
    assert second and second["loaded_user_skills_revision"] == 2
    descriptions = {item["description"] for item in second["skills_metadata"]}
    assert "用户流程 v2" in descriptions and "用户流程 v1" not in descriptions


def test_same_revision_is_reloaded_when_authenticated_identity_changes():
    backend = MutableSkillsBackend()
    revision = [7]
    actor = ["ou-a"]
    middleware = _middleware(backend, revision, actor)
    first = middleware.before_agent({}, _runtime(), {})
    assert first
    calls = backend.calls
    actor[0] = "ou-b"
    second = middleware.before_agent(first, _runtime(), {})
    assert second is not None
    assert backend.calls > calls
    assert second["loaded_user_skills_scope"] != first["loaded_user_skills_scope"]


@pytest.mark.asyncio
async def test_async_revision_reload_matches_sync_contract():
    backend = MutableSkillsBackend()
    revision = [4]
    middleware = _middleware(backend, revision)
    first = await middleware.abefore_agent({}, _runtime(), {})
    assert first and first["loaded_user_skills_revision"] == 4
    backend.user_description = "异步 v5"
    revision[0] = 5
    second = await middleware.abefore_agent(first, _runtime(), {})
    assert second and any(item["description"] == "异步 v5" for item in second["skills_metadata"])


@pytest.mark.asyncio
async def test_async_revision_timeout_fails_closed_without_waiting_for_loader_completion():
    backend = MutableSkillsBackend()

    def slow_revision(tenant: str, actor: str) -> int:
        time.sleep(0.2)
        return 1

    middleware = RevisionAwareSkillsMiddleware(
        backend=backend,
        system_sources=[("/skills/", "系统")],
        user_sources=[("/user-skills/", "我的")],
        revision_loader=slow_revision,
        actor_resolver=lambda config: "ou-owner",
        tenant_resolver=lambda: "tenant-a",
        io_timeout_seconds=0.01,
    )
    started = time.perf_counter()
    update = await middleware.abefore_agent({}, _runtime(), {})
    assert time.perf_counter() - started < 0.1
    assert update and update["loaded_user_skills_revision"] is None


def test_revision_failure_drops_stale_user_metadata_and_retries_next_turn():
    backend = MutableSkillsBackend()

    def unavailable(tenant: str, actor: str) -> int:
        raise RuntimeError("secret database detail")

    middleware = RevisionAwareSkillsMiddleware(
        backend=backend,
        system_sources=[("/skills/", "系统")],
        user_sources=[("/user-skills/", "我的")],
        revision_loader=unavailable,
        actor_resolver=lambda config: "ou-owner",
        tenant_resolver=lambda: "tenant-a",
    )
    state = {
        "skills_metadata": [
            {"name": "usr-stale", "description": "stale", "path": "/user-skills/usr-stale/SKILL.md"}
        ],
        "loaded_user_skills_revision": 8,
    }
    update = middleware.before_agent(state, _runtime(), {})
    assert update and update["loaded_user_skills_revision"] is None
    assert [item["name"] for item in update["skills_metadata"]] == ["system-flow"]
    assert update["skills_load_errors"] == ["User Skill catalog is temporarily unavailable"]
