"""框架公开扩展面契约冒烟测试。

钉死本项目对 deepagents / langchain 的所有扩展都走【官方公开导出入口】,
而非内部实现子模块。一旦升级 deepagents/langchain 后某个符号从公开 __all__
里消失或改名,这里立刻变红 —— 把"升级 break"暴露在 CI,而不是等生产启动
时 ImportError 才发现。

判定标准:符号必须能从其【包级/顶层】入口导入,且(若有 __all__)在 __all__
中显式列出。深层实现路径(如 deepagents.backends.composite)不算公开契约。
"""


def test_deepagents_backends_public_exports():
    """backends.py 依赖的四个后端必须由 deepagents.backends 包级 __all__ 导出。"""
    import deepagents.backends as backends_pkg

    expected = {"CompositeBackend", "FilesystemBackend", "StateBackend", "StoreBackend"}
    exported = set(getattr(backends_pkg, "__all__", []))
    missing = expected - exported
    assert not missing, (
        f"deepagents.backends 不再公开导出 {sorted(missing)} —— "
        "backends.py 的包级导入会断,需检查 deepagents 升级变更"
    )
    # 能取到属性(__all__ 列了但实际拿不到也算断约)
    for name in expected:
        assert getattr(backends_pkg, name, None) is not None, f"{name} 在 __all__ 但无法取得"


def test_deepagents_toplevel_public_exports():
    """agent.py 从 deepagents 顶层导入的符号必须在顶层 __all__。"""
    import deepagents

    expected = {
        "FilesystemPermission",
        "HarnessProfileConfig",
        "create_deep_agent",
        "register_harness_profile",
    }
    exported = set(getattr(deepagents, "__all__", []))
    missing = expected - exported
    assert not missing, (
        f"deepagents 顶层不再公开导出 {sorted(missing)} —— agent.py 导入会断"
    )


def test_langchain_middleware_public_exports():
    """models.py / middlewares.py 依赖的中间件符号必须在
    langchain.agents.middleware 顶层 __all__(不走 .types 等内部子模块)。"""
    import langchain.agents.middleware as mw

    expected = {
        "AgentMiddleware",
        "ModelRequest",
        "ModelRetryMiddleware",
    }
    exported = set(getattr(mw, "__all__", []))
    missing = expected - exported
    assert not missing, (
        f"langchain.agents.middleware 顶层不再公开导出 {sorted(missing)} —— "
        "models.py 的顶层导入会断"
    )
    for name in expected:
        assert getattr(mw, name, None) is not None, f"{name} 在 __all__ 但无法取得"
