from deepagents.backends import StateBackend, StoreBackend

from backends import build_backend


def test_build_backend_loads_skills_via_composite():
    """三路由 CompositeBackend 应能经 /skills/ 路由读到 topic-content skill。

    用公开的 backend.ls() 契约验证(BackendProtocol),不依赖框架私有
    helper(skills._list_skills)——后者是内部 API,升级 deepagents 易碎。
    """
    backend = build_backend()
    entries = backend.ls("/skills/").entries or []
    paths = [entry["path"] for entry in entries]
    assert any("topic-content" in path for path in paths)


def test_build_backend_skills_path_is_virtual():
    """skill 路径应是虚拟路径(以 / 开头),非 Windows 绝对路径。"""
    backend = build_backend()
    entries = backend.ls("/skills/").entries or []
    assert entries, "应至少加载到一个 skill"
    assert all(entry["path"].startswith("/") for entry in entries)


def test_build_backend_skills_content_readable():
    """经 /skills/ 路由应能读到 SKILL.md 正文(端到端验证路由 + 前缀剥离正确)。"""
    backend = build_backend()
    result = backend.read("/skills/topic-content/SKILL.md")
    assert result.error is None
    assert result.file_data is not None
    assert result.file_data["content"].strip()


def test_build_backend_has_no_business_file_routes():
    """业务资产只能走数据库工具，不注册虚拟文件路由。"""
    backend = build_backend()
    assert set(backend.routes) == {
        "/skills/",
        "/user-skills/",
        "/memories/",
        "/user-memories/",
    }
    assert isinstance(backend.default, StateBackend)


def test_build_backend_routes_agent_memories_to_store():
    """DeepAgents 内部团队和用户记忆继续使用独立 StoreBackend。"""
    backend = build_backend()
    assert isinstance(backend.routes["/memories/"], StoreBackend)
    assert isinstance(backend.routes["/user-memories/"], StoreBackend)
