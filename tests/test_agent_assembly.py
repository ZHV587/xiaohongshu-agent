"""agent 组装回归测试。

除验证 agent 可装配外,钉死两个收敛期修过的 Critical 安全回归:
- 安全点A:register_harness_profile 的 key 必须 "openai"。铁律一钉死
  provider=openai,key 若误写 "anthropic" 则 profile 失配 →
  excluded_tools={execute,write_todos} 失效 → execute(shell)暴露。
- 安全点B:RubricMiddleware 必须收 BaseChatModel 实例(非裸 id 字符串)。
  收字符串会按名推断 provider(claude-*→anthropic)拿真实 ANTHROPIC_API_KEY
  绕网关泄漏。

所有用例先把禁探测 + 设池 env 写好再 reload agent,避免装配阶段真实
打网关 / 真实初始化外部模型。
"""


def _set_assembly_env(monkeypatch):
    """禁真实探测 + 喂模型池所需 env,使 agent 可离线装配。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DISCOVER_MODELS", "false")
    monkeypatch.setenv("LLM_BASE_URL", "https://test-gw/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "claude-sonnet-4-6")
    monkeypatch.setenv("XHS_SYNC_ENABLED", "false")


def test_agent_importable_and_compiled(monkeypatch):
    # 组装阶段会构造模型池,需要禁探测 + 池 env(不真实调用)
    _set_assembly_env(monkeypatch)
    import importlib
    import agent as agent_module
    importlib.reload(agent_module)
    # create_deep_agent 返回一个 CompiledStateGraph,应有 invoke 方法
    assert hasattr(agent_module.agent, "invoke")
    assert hasattr(agent_module.agent, "astream")


def test_harness_profile_excludes_execute(monkeypatch):
    """安全点A:profile 必须注册在 key="openai" 下,且排除 execute(shell 执行)。

    机制:agent.py 装配时调 register_harness_profile("openai", ...)。
    deepagents 用 model 的 provider(铁律一钉死 openai)拼 "openai:<model>"
    去 _get_harness_profile 查 profile,profile 的 excluded_tools 驱动
    _ToolExclusionMiddleware 在模型调用时把工具从 request.tools 抹掉。
    若 key 误写 "anthropic",查 "openai:claude-sonnet-4-6" 命中不到本次注册,
    excluded_tools 退回空集 → execute 暴露。

    注:write_todos 已重新启用(长任务规划需要),故不在排除集;真正的危险
    工具是 execute(shell 命令执行),它必须始终被排除。

    注意:_HARNESS_PROFILES 是进程级全局,跨 reload 累积(additive merge)。
    为让本用例只观测「本次 agent 装配注册了什么」、不被同会话其它用例污染,
    reload 前先清掉相关 key,这样若 key 写错本次就查不到 → 断言变红。
    """
    import importlib

    from deepagents.profiles.harness import harness_profiles as hp

    # 清掉可能由同会话其它用例 / 历史 reload 残留的注册,确保只观测本次装配
    for key in ("openai", "openai:claude-sonnet-4-6"):
        hp._HARNESS_PROFILES.pop(key, None)

    _set_assembly_env(monkeypatch)
    import agent as agent_module
    importlib.reload(agent_module)  # 触发 register_harness_profile("openai", ...)

    profile = hp._get_harness_profile("openai:claude-sonnet-4-6")
    # key 必须是 "openai":查 openai:<model> 才能命中本次注册;
    # 若误写 "anthropic",这里拿到 None,下面断言全红。
    assert profile is not None, (
        "查不到 openai:claude-sonnet-4-6 的 harness profile —— "
        "register_harness_profile 的 key 可能不是 'openai'"
    )
    assert "execute" in profile.excluded_tools
    assert "write_todos" not in profile.excluded_tools  # write_todos 已启用(长任务规划)



def test_rubric_uses_model_instance_not_string(monkeypatch):
    """安全点B:RubricMiddleware 必须收 BaseChatModel 实例,不能收裸 id 字符串。

    机制:agent.py 用 `from deepagents import RubricMiddleware`,装配时
    RubricMiddleware(model=build_primary_model(pool), ...)。若改回传字符串
    (如 model="claude-sonnet-4-6"),deepagents 会按名推断 provider 自建
    Anthropic 模型,拿真实 ANTHROPIC_API_KEY 绕网关直连泄漏。

    拦截点:patch deepagents.RubricMiddleware(agent.py 的 import 源),
    在 reload 前替换为假中间件,reload 重新执行 import 行时拿到假类,
    捕获 __init__ 收到的 model 参数。假类须是 AgentMiddleware 子类,
    否则 create_deep_agent 组装会报错(无 wrap_tool_call 等属性)。
    """
    import importlib

    import deepagents
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.language_models import BaseChatModel

    captured = {}
    real_rubric = deepagents.RubricMiddleware

    class _CapturingRubric(AgentMiddleware):
        def __init__(self, *, model=None, **kwargs):
            super().__init__()
            captured["model"] = model
            captured["system_prompt"] = kwargs.get("system_prompt", "")

    _set_assembly_env(monkeypatch)
    deepagents.RubricMiddleware = _CapturingRubric
    try:
        import agent as agent_module
        importlib.reload(agent_module)
    finally:
        deepagents.RubricMiddleware = real_rubric
        # 复原后再 reload,避免把假中间件残留给同会话后续用例
        importlib.reload(agent_module)

    assert "model" in captured, "RubricMiddleware 未被装配调用,patch 未拦到"
    model = captured["model"]
    # 必须是实例,不能是裸字符串 —— 否则会按名推断 provider 绕网关
    assert isinstance(model, BaseChatModel)
    assert not isinstance(model, str)

    rubric_prompt = captured["system_prompt"]
    assert "resource_id" in rubric_prompt
    assert "updated_at" in rubric_prompt
    assert "无依据" in rubric_prompt or "没有依据" in rubric_prompt
    assert "当前数据不足" in rubric_prompt


def test_agent_exposes_shared_model_registry(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_mod

    agent_mod = importlib.reload(agent_mod)

    status = agent_mod.model_registry.status()
    assert status["active_models"]
    assert status["hot_reload_coverage"]["main_agent"] is True
    assert status["hot_reload_coverage"]["subagents"] is True
    assert status["hot_reload_coverage"]["rubric"] is False


def test_agent_registers_data_foundation_tools(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_module

    agent_module = importlib.reload(agent_module)
    tool_names = {getattr(tool, "name", "") for tool in agent_module.phase3_tools}

    assert {
        "search_resources",
        "semantic_search_resources",
        "graph_expand",
        "get_resource",
        "get_data_foundation_status",
        "sync_feishu_resources",
    } <= tool_names


def test_agent_registers_feishu_action_tools(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_module

    agent_module = importlib.reload(agent_module)
    tool_names = {getattr(tool, "name", "") for tool in agent_module.feishu_action_tools}

    assert {"sync_copy_to_feishu", "send_review_notification"} <= tool_names


def test_agent_write_tools_have_interrupts_and_checkpointer(monkeypatch):
    import importlib
    import deepagents

    captured = {}
    real_create = deepagents.create_deep_agent

    def _capturing_create_deep_agent(*args, **kwargs):
        captured.update(kwargs)
        return real_create(*args, **kwargs)

    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")
    deepagents.create_deep_agent = _capturing_create_deep_agent
    try:
        import agent as agent_module

        importlib.reload(agent_module)
    finally:
        deepagents.create_deep_agent = real_create

    interrupts = captured["interrupt_on"]
    assert captured["checkpointer"] is True
    assert interrupts["execute_lark_command"] is True
    assert interrupts["sync_copy_to_feishu"] is True
    assert interrupts["send_review_notification"] is True


def test_agent_does_not_start_scheduler_unless_enabled(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")
    monkeypatch.delenv("XHS_SYNC_ENABLED", raising=False)

    import importlib
    import dotenv
    import data_foundation.scheduler as scheduler

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    scheduler._started = False
    import agent as agent_module
    importlib.reload(agent_module)

    assert scheduler._started is False
