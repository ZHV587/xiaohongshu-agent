from __future__ import annotations

from datetime import datetime, timezone
import time

import pytest
from deepagents.backends import CompositeBackend, StateBackend

from data_foundation.models import PublishedUserSkillDocument
from data_foundation.user_skill_backend import PostgresUserSkillsBackend


def _doc(name: str, description: str = "用户要求按自定义流程处理时使用") -> PublishedUserSkillDocument:
    return PublishedUserSkillDocument(
        runtime_name=name,
        version_id=f"version-{name}",
        version=1,
        display_name="我的流程",
        description=description,
        instructions_markdown="先核对目标，再执行并自检。",
        trigger_examples=["按我的流程处理"],
        non_trigger_examples=["只查询天气"],
        tags=["通用"],
        updated_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
    )


def _backend(actor: list[str], calls: list[tuple[str, str]]) -> PostgresUserSkillsBackend:
    documents = {
        "ou-a": [_doc("usr-owner-a")],
        "ou-b": [_doc("usr-owner-b")],
    }

    def load(tenant: str, owner: str):
        calls.append((tenant, owner))
        return documents.get(owner, [])

    return PostgresUserSkillsBackend(
        document_loader=load,
        actor_resolver=lambda: actor[0],
        tenant_resolver=lambda: "tenant-a",
    )


def test_backend_is_user_scoped_and_exposes_only_standard_skill_files():
    actor = ["ou-a"]
    calls: list[tuple[str, str]] = []
    backend = _backend(actor, calls)

    root = backend.ls("/")
    assert [entry["path"] for entry in root.entries or []] == ["/usr-owner-a/"]
    assert backend.ls("/usr-owner-b").error == "file_not_found"

    response = backend.download_files(["/usr-owner-a/SKILL.md"])[0]
    content = (response.content or b"").decode()
    assert "name: \"usr-owner-a\"" in content
    assert "allowed-tools" not in content
    assert calls and all(call == ("tenant-a", "ou-a") for call in calls)

    actor[0] = "ou-b"
    assert [entry["path"] for entry in backend.ls("/").entries or []] == ["/usr-owner-b/"]


def test_backend_preserves_batch_order_and_supports_read_grep_glob():
    backend = _backend(["ou-a"], [])
    paths = ["/missing/SKILL.md", "/usr-owner-a/SKILL.md", "../bad"]
    responses = backend.download_files(paths)
    assert [item.path for item in responses] == paths
    assert responses[0].error == "file_not_found"
    assert responses[1].content
    assert responses[2].error == "invalid_path"

    first_line = backend.read("/usr-owner-a/SKILL.md", offset=0, limit=1)
    assert first_line.file_data and first_line.file_data["content"] == "---\n"
    assert backend.grep("先核对目标", path="/usr-owner-a").matches
    matches = backend.glob("**/SKILL.md").matches or []
    assert [item["path"] for item in matches] == ["/usr-owner-a/SKILL.md"]


@pytest.mark.asyncio
async def test_async_backend_resolves_actor_before_worker_thread_and_matches_sync_results():
    actor = ["ou-a"]
    backend = _backend(actor, [])
    assert await backend.als("/") == backend.ls("/")
    assert await backend.aread("/usr-owner-a/SKILL.md") == backend.read(
        "/usr-owner-a/SKILL.md"
    )
    assert await backend.adownload_files(["/usr-owner-a/SKILL.md"]) == backend.download_files(
        ["/usr-owner-a/SKILL.md"]
    )
    assert await backend.aglob("**/SKILL.md") == backend.glob("**/SKILL.md")
    assert await backend.agrep("核对") == backend.grep("核对")


@pytest.mark.asyncio
async def test_backend_rejects_every_write_path_in_sync_and_async_modes():
    backend = _backend(["ou-a"], [])
    assert backend.write("/usr-owner-a/new.md", "x").error == "permission_denied"
    assert backend.edit("/usr-owner-a/SKILL.md", "a", "b").error == "permission_denied"
    assert backend.upload_files([("/x", b"x")])[0].error == "permission_denied"
    assert (await backend.awrite("/x", "x")).error == "permission_denied"
    assert (await backend.aedit("/x", "a", "b")).error == "permission_denied"
    assert (await backend.aupload_files([("/x", b"x")]))[0].error == "permission_denied"


@pytest.mark.asyncio
async def test_backend_async_reads_have_a_deadline():
    def slow_loader(tenant: str, owner: str):
        time.sleep(0.2)
        return [_doc("usr-slow")]

    backend = PostgresUserSkillsBackend(
        document_loader=slow_loader,
        actor_resolver=lambda: "ou-owner",
        tenant_resolver=lambda: "tenant-a",
        io_timeout_seconds=0.01,
    )
    started = time.perf_counter()
    result = await backend.als("/")
    assert time.perf_counter() - started < 0.1
    assert result.error == "User Skill catalog timed out"


def test_composite_backend_restores_user_skill_route_prefix():
    user_backend = _backend(["ou-a"], [])
    composite = CompositeBackend(default=StateBackend(), routes={"/user-skills/": user_backend})
    root = composite.ls("/user-skills/")
    assert [entry["path"] for entry in root.entries or []] == ["/user-skills/usr-owner-a/"]
    response = composite.download_files(["/user-skills/usr-owner-a/SKILL.md"])[0]
    assert response.error is None and response.content
