from __future__ import annotations

from types import SimpleNamespace
import time
from datetime import datetime, timezone

import pytest
from deepagents.backends.protocol import BackendProtocol, FileDownloadResponse, LsResult
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage

from data_foundation.models import SelectedUserSkillDocument, UserSkillVersion
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


def _selected_document(
    *,
    status: str = "published",
    published_version: int | None = 1,
) -> SelectedUserSkillDocument:
    version = UserSkillVersion(
        id="22222222-2222-4222-8222-222222222222",
        tenant_id="tenant-a",
        owner_open_id="ou-owner",
        skill_id="11111111-1111-4111-8111-111111111111",
        version=1,
        display_name="我的精确流程",
        description="用户显式选择时使用",
        instructions_markdown="必须先列证据，再输出结论。",
        trigger_examples=[],
        non_trigger_examples=[],
        tags=["通用"],
        content_hash="hash",
        created_by_open_id="ou-owner",
        created_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
    )
    return SelectedUserSkillDocument(
        skill_id=version.skill_id,
        runtime_name="usr-owner-flow",
        status=status,
        published_version=published_version,
        definition=version,
    )


def _middleware(
    backend: BackendProtocol,
    revision: list[int],
    actor: list[str] | None = None,
    selected_loader=None,
):
    actor = actor or ["ou-owner"]
    return RevisionAwareSkillsMiddleware(
        backend=backend,
        system_sources=[("/skills/", "系统")],
        user_sources=[("/user-skills/", "我的")],
        revision_loader=lambda tenant, actor: revision[0],
        selected_loader=selected_loader or (lambda *args: _selected_document()),
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
    assert middleware.before_agent(state, _runtime(), {}) == {"resolved_user_skill": None}
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


def test_explicit_selection_is_bound_to_turn_and_resolved_server_side():
    calls = []

    def load(*args):
        calls.append(args)
        return _selected_document()

    middleware = _middleware(MutableSkillsBackend(), [1], selected_loader=load)
    selected = {
        "skill_id": "11111111-1111-4111-8111-111111111111",
        "version_id": "22222222-2222-4222-8222-222222222222",
        "mode": "execute",
        "invocation_id": "turn-1",
    }
    update = middleware.before_agent(
        {"selected_user_skill": selected},
        _runtime(),
        {"configurable": {"turn_id": "turn-1"}},
    )
    assert update and update["resolved_user_skill"]["runtime_name"] == "usr-owner-flow"
    assert calls[0][0:2] == ("tenant-a", "ou-owner")

    stale = middleware.before_agent(
        {**update, "selected_user_skill": selected},
        _runtime(),
        {"configurable": {"turn_id": "turn-2"}},
    )
    assert stale == {"resolved_user_skill": None}
    assert len(calls) == 1


def test_selected_skill_rejection_is_generic_and_does_not_disclose_resource_state():
    def reject(*args):
        raise KeyError("belongs to another user")

    middleware = _middleware(MutableSkillsBackend(), [1], selected_loader=reject)
    state = {
        "selected_user_skill": {
            "skill_id": "11111111-1111-4111-8111-111111111111",
            "version_id": "22222222-2222-4222-8222-222222222222",
            "mode": "execute",
            "invocation_id": "turn-1",
        }
    }
    with pytest.raises(PermissionError, match="Selected User Skill is unavailable") as caught:
        middleware.before_agent(
            state,
            _runtime(),
            {"configurable": {"turn_id": "turn-1"}},
        )
    assert "another user" not in str(caught.value)


def test_explicit_skill_prompt_hides_other_user_skills_and_never_changes_tools():
    middleware = _middleware(MutableSkillsBackend(), [1])
    request = ModelRequest(
        model=object(),
        messages=[],
        system_message=SystemMessage(content="平台规则"),
        tools=[{"name": "safe_tool"}],
        state={
            "resolved_user_skill": {
                "skill_id": "11111111-1111-4111-8111-111111111111",
                "version_id": "22222222-2222-4222-8222-222222222222",
                "runtime_name": "usr-owner-flow",
                "mode": "execute",
                "invocation_id": "turn-1",
            },
            "skills_metadata": [
                {"name": "system-flow", "description": "系统", "path": "/skills/system-flow/SKILL.md", "metadata": {}, "license": None, "compatibility": None, "allowed_tools": []},
                {"name": "usr-other", "description": "其他", "path": "/user-skills/usr-other/SKILL.md", "metadata": {}, "license": None, "compatibility": None, "allowed_tools": []},
            ],
        },
        runtime=_runtime(),
    )
    captured = {}

    def handler(modified):
        captured["request"] = modified
        return "ok"

    assert middleware.wrap_model_call(request, handler) == "ok"
    modified = captured["request"]
    prompt = str(modified.system_message.content)
    assert "<explicit_user_skill>" in prompt
    assert "必须先列证据" in prompt
    assert "usr-other" not in prompt
    assert modified.tools == request.tools


def test_draft_test_mode_removes_write_and_subagent_tools():
    middleware = _middleware(MutableSkillsBackend(), [1])
    request = ModelRequest(
        model=object(),
        messages=[],
        system_message=SystemMessage(content="平台规则"),
        tools=[
            {"name": "get_resource"},
            {"name": "save_generated_copy"},
            {"name": "save_writing_teardown"},
            {"name": "lark_cli"},
            {"name": "task"},
        ],
        state={
            "resolved_user_skill": {
                "skill_id": "11111111-1111-4111-8111-111111111111",
                "version_id": "22222222-2222-4222-8222-222222222222",
                "runtime_name": "usr-owner-flow",
                "mode": "test",
                "invocation_id": "turn-1",
            },
            "skills_metadata": [],
        },
        runtime=_runtime(),
    )
    captured = {}

    def handler(modified):
        captured["request"] = modified
        return "ok"

    middleware.wrap_model_call(request, handler)
    assert [tool["name"] for tool in captured["request"].tools] == ["get_resource"]


def test_after_agent_clears_one_turn_selection():
    middleware = _middleware(MutableSkillsBackend(), [1])
    assert middleware.after_agent({}, _runtime(), {}) == {
        "selected_user_skill": None,
        "resolved_user_skill": None,
    }
