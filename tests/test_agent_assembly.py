def test_agent_importable_and_compiled(monkeypatch):
    # 组装阶段会初始化 Anthropic 模型,需要 key 存在(不真实调用)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    import importlib
    import agent as agent_module
    importlib.reload(agent_module)
    # create_deep_agent 返回一个 CompiledStateGraph,应有 invoke 方法
    assert hasattr(agent_module.agent, "invoke")
    assert hasattr(agent_module.agent, "astream")
