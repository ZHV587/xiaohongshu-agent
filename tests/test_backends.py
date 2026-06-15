import os

from backends import build_backend


def test_build_backend_loads_skills_via_composite():
    """三路由 CompositeBackend 应能经 /skills/ 路由读到 topic-content skill。"""
    import deepagents.middleware.skills as sk

    backend = build_backend()
    skills = sk._list_skills(backend, "/skills/")
    names = [s["name"] for s in skills]
    assert "topic-content" in names


def test_build_backend_skills_path_is_virtual():
    """skill 路径应是虚拟路径(以 / 开头),非 Windows 绝对路径。"""
    import deepagents.middleware.skills as sk

    backend = build_backend()
    skills = sk._list_skills(backend, "/skills/")
    assert skills, "应至少加载到一个 skill"
    assert skills[0]["path"].startswith("/skills/")


def test_build_backend_routes_shared_to_store():
    """/shared/ 前缀应路由到 StoreBackend,而非默认 StateBackend。"""
    from deepagents.backends.store import StoreBackend

    backend = build_backend()
    # 白盒测试:直接验证路由决策;_get_backend_and_key 是框架内部 API
    target, _key = backend._get_backend_and_key("/shared/xhs-style.md")
    assert isinstance(target, StoreBackend)


def test_build_backend_routes_drafts_to_default_state():
    """/drafts/ 未单独路由,应落到默认 StateBackend。"""
    from deepagents.backends.state import StateBackend

    backend = build_backend()
    # 白盒测试:直接验证路由决策;_get_backend_and_key 是框架内部 API
    target, _key = backend._get_backend_and_key("/drafts/x.md")
    assert isinstance(target, StateBackend)
