"""agent 组装回归测试。

除验证 agent 可装配外,钉死两个收敛期修过的 Critical 安全回归:
- 安全点A:register_harness_profile 的 key 必须 "openai"。铁律一钉死
  provider=openai,key 若误写 "anthropic" 则 profile 失配 →
  excluded_tools={execute} 失效 → execute(shell)暴露。
  拦截方式:patch 公开的 register_harness_profile 捕获本次装配传参,
  不读框架私有的 _HARNESS_PROFILES 全局表。
- 安全点B:RubricMiddleware 必须收 BaseChatModel 实例(非裸 id 字符串)。
  收字符串会按名推断 provider(claude-*→anthropic)拿真实 ANTHROPIC_API_KEY
  绕网关泄漏。

所有用例先把禁探测 + 设池 env 写好再 reload agent,避免装配阶段真实
打网关 / 真实初始化外部模型。框架公开扩展面契约(导入路径稳定性)另见
test_public_api_contract.py。
"""


def _set_assembly_env(monkeypatch):
    """禁真实探测 + 喂模型池所需 env,使 agent 可离线装配。"""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DISCOVER_MODELS", "false")
    monkeypatch.setenv("LLM_BASE_URL", "https://test-gw/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_QUALITY_MODELS", "claude-sonnet-4-6")
    monkeypatch.setenv("XHS_SYNC_ENABLED", "false")


def _reload_subagents():
    import sys
    import importlib
    if "subagents_executor" in sys.modules:
        importlib.reload(sys.modules["subagents_executor"])


def test_agent_importable_and_compiled(monkeypatch):
    # 组装阶段会构造模型池,需要禁探测 + 池 env(不真实调用)
    _set_assembly_env(monkeypatch)
    import importlib
    import agent as agent_module
    importlib.reload(agent_module)
    # create_deep_agent 返回一个 CompiledStateGraph,应有 invoke 方法
    assert hasattr(agent_module.agent, "invoke")
    assert hasattr(agent_module.agent, "astream")


def test_skills_middleware_wired(monkeypatch):
    """官方 skill 机制已接线:create_deep_agent(skills=["/skills/"]) 必须装上
    SkillsMiddleware,它在 before_agent 期把 .agents/skills/ 下的 SKILL.md 清单
    注入 system prompt(渐进式披露)。

    钉死这条线的存在,防止 skills= 被误删退回"死配置"(SKILL.md 存在但 agent
    看不到)。断言用 graph 节点名——SkillsMiddleware 的 before_agent hook 会落成
    一个 `SkillsMiddleware.before_agent` 图节点。

    注:skills 的 ls/download 发生在 before_agent 运行期(请求时),不在 import 期,
    故离线装配(DISCOVER_MODELS=false)不会因 skills= 触网。
    """
    _set_assembly_env(monkeypatch)
    import importlib
    import agent as agent_module
    importlib.reload(agent_module)

    nodes = list(agent_module.agent.get_graph().nodes)
    assert any("SkillsMiddleware" in n for n in nodes), (
        f"SkillsMiddleware 未接线(skills= 可能被删),当前节点:{nodes}"
    )


def test_harness_profile_excludes_execute(monkeypatch):
    """安全点A:profile 必须注册在 key="openai" 下,且排除 execute(shell 执行)。

    机制:agent.py 装配时调 register_harness_profile("openai", ...)。
    deepagents 用 model 的 provider(铁律一钉死 openai)拼 "openai:<model>"
    去查 profile,profile 的 excluded_tools 驱动 _ToolExclusionMiddleware
    在模型调用时把工具从 request.tools 抹掉。若 key 误写 "anthropic",
    查 "openai:claude-sonnet-4-6" 命中不到本次注册,excluded_tools 退回空集
    → execute 暴露。

    注:write_todos 已重新启用(长任务规划需要),故不在排除集;真正的危险
    工具是 execute(shell 命令执行),它必须始终被排除。

    拦截方式:patch 公开的 register_harness_profile(agent.py 的调用入口),
    直接捕获本次装配传入的 (key, profile),而非读框架私有的 _HARNESS_PROFILES
    全局表(后者跨 reload 累积、需手工清污染,且依赖内部实现)。直接看调用
    参数语义更强:本次装配到底用什么 key、排除了哪些工具。
    """
    import importlib

    import deepagents

    captured = {}
    real_register = deepagents.register_harness_profile

    def _capturing_register(key, profile):
        # 只记录本次 agent 装配关心的那次注册(provider key "openai")
        if key == "openai":
            captured["key"] = key
            captured["profile"] = profile
        return real_register(key, profile)

    _set_assembly_env(monkeypatch)
    monkeypatch.setattr(deepagents, "register_harness_profile", _capturing_register)
    import agent as agent_module
    importlib.reload(agent_module)  # 触发 register_harness_profile("openai", ...)

    # key 必须是 "openai":铁律一钉死 provider=openai,查 openai:<model> 才命中。
    assert captured.get("key") == "openai", (
        "register_harness_profile 未以 key='openai' 调用 —— "
        "key 写错会导致 harness profile 失配,execute 暴露"
    )
    profile = captured["profile"]
    assert "execute" in profile.excluded_tools
    assert "write_todos" not in profile.excluded_tools  # write_todos 已启用(长任务规划)



def test_rubric_uses_model_instance_not_string(monkeypatch):
    """安全点B:RubricMiddleware 必须收 BaseChatModel 实例,不能收裸 id 字符串。

    机制:agent.py 用 `from deepagents import RubricMiddleware`,装配时
    RubricMiddleware(model=RegistryRoutedChatModel(model_registry, initial_model), ...)。
    若改回传字符串(如 model="claude-sonnet-4-6"),deepagents 会按名推断 provider 自建
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
    # 且必须是 registry 驱动的 RegistryRoutedChatModel:rubric grader 不经 router,
    # 唯有传它才能让评分吃 config-center 热重载(env 不再钉死评分模型)。
    from rubric_model import RegistryRoutedChatModel
    assert isinstance(model, RegistryRoutedChatModel)

    rubric_prompt = captured["system_prompt"]
    assert "resource_id" in rubric_prompt
    assert "source_updated_at" in rubric_prompt
    assert "indexed_at" in rubric_prompt
    assert "无依据" in rubric_prompt or "没有依据" in rubric_prompt
    assert "当前数据不足" in rubric_prompt


def test_content_rubric_activator_registered_immediately_after_rubric(monkeypatch):
    """after_agent 逆序执行,故 activator 必须紧跟 rubric 注册。"""
    import importlib

    import deepagents
    from content_rubric import ContentRubricActivator

    captured = {}
    real_create = deepagents.create_deep_agent

    def _capturing_create_deep_agent(*args, **kwargs):
        captured["middleware"] = kwargs["middleware"]
        return real_create(*args, **kwargs)

    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")
    deepagents.create_deep_agent = _capturing_create_deep_agent
    try:
        import agent as agent_module

        importlib.reload(agent_module)
    finally:
        deepagents.create_deep_agent = real_create

    middleware = captured["middleware"]
    rubric_index = middleware.index(agent_module.rubric_middleware)
    assert isinstance(middleware[rubric_index + 1], ContentRubricActivator)


def test_agent_exposes_shared_model_registry(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_mod

    agent_mod = importlib.reload(agent_mod)

    # 单一数据源:registry 启动即空(不灌 env),池由 server lifespan 从 config-center
    # 构建填充。装配期 router 经空池回退到 initial_model 占位,不报错。
    status = agent_mod.model_registry.status()
    assert status["version"] == ""          # 启动未对齐任何 config 版本
    assert status["active_models"] == []    # 空池,等 lifespan 填充
    assert status["hot_reload_coverage"]["main_agent"] is True
    assert status["hot_reload_coverage"]["subagents"] is True
    assert status["hot_reload_coverage"]["rubric"] is True
    # 占位模型仍可装配出可用 agent(空池下 router 回退到它)
    assert hasattr(agent_mod.agent, "invoke")


def test_agent_registers_data_foundation_tools(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_module

    agent_module = importlib.reload(agent_module)
    assert not hasattr(agent_module, "phase3_tools")
    tool_names = {getattr(tool, "name", "") for tool in agent_module.data_foundation_tools}

    assert {
        "search_resources",
        "semantic_search_resources",
        "graph_expand",
        "get_resource",
        "get_data_foundation_status",
        "sync_feishu_resources",
        "save_generated_topic",
        "save_generated_copy",
        "save_user_feedback",
        "save_performance_metric",
        "get_resource_performance",
    } <= tool_names


def test_agent_does_not_expose_raw_feishu_readers(monkeypatch):
    import importlib
    import deepagents

    captured = {}
    real_create = deepagents.create_deep_agent

    def _capturing_create_deep_agent(*args, **kwargs):
        captured["tools"] = kwargs["tools"]
        return real_create(*args, **kwargs)

    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")
    deepagents.create_deep_agent = _capturing_create_deep_agent
    try:
        import agent as agent_module

        importlib.reload(agent_module)
    finally:
        deepagents.create_deep_agent = real_create

    tool_names = {getattr(tool, "name", "") for tool in captured["tools"]}
    assert "read_xhs_data" not in tool_names
    assert "read_feishu_wiki" not in tool_names
    assert "sync_feishu_resources" in tool_names


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
    assert interrupts["sync_topic_to_feishu"] is True
    assert interrupts["sync_diagnosis_to_feishu"] is True
    assert interrupts["send_review_notification"] is True


def test_agent_does_not_import_scheduler_daemon_entrypoint(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import data_foundation.scheduler as scheduler
    from data_foundation.supervisor import BackgroundServiceSupervisor

    async def forbidden_start(self):
        raise AssertionError("agent import must not start background services")

    monkeypatch.setattr(BackgroundServiceSupervisor, "start", forbidden_start)
    import agent as agent_module
    importlib.reload(agent_module)

    assert not hasattr(scheduler, "start_background_services")


def test_agent_import_does_not_update_lark_adapters(monkeypatch):
    """导入 agent 不应触发飞书适配器的自更新。"""
    import importlib
    import sys

    import tools.lark_cli as lark_cli

    update_calls = []

    def _record_update(name):
        def _update():
            update_calls.append(name)

        return _update

    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "false")
    monkeypatch.setattr(lark_cli, "auto_update_lark_skills", _record_update("skills"))
    monkeypatch.setattr(lark_cli, "auto_update_lark_cli", _record_update("cli"))
    monkeypatch.delitem(sys.modules, "agent", raising=False)

    import agent as agent_module

    importlib.reload(agent_module)

    assert update_calls == []


def test_agent_registers_executor_subagents(monkeypatch):
    """xhs-router 必须注册全部4个执行型子智能体，不多不少。"""
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import deepagents
    from subagents_executor import EXECUTOR_SUBAGENT_NAMES

    captured_subagents = []
    real_create = deepagents.create_deep_agent

    def _capturing_create(*args, **kwargs):
        captured_subagents.extend(kwargs.get("subagents", []))
        return real_create(*args, **kwargs)

    monkeypatch.setattr(deepagents, "create_deep_agent", _capturing_create)
    _reload_subagents()

    import agent as agent_module
    importlib.reload(agent_module)

    # 只有执行型子智能体，不含旧的域主 agent
    names = {s["name"] for s in captured_subagents}
    assert names == EXECUTOR_SUBAGENT_NAMES


def test_executor_subagents_have_persistence_tools(monkeypatch):
    """每个执行型子智能体必须持有其负责的持久化工具。"""
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import deepagents

    captured_subagents = []
    real_create = deepagents.create_deep_agent

    def _capturing_create(*args, **kwargs):
        captured_subagents.extend(kwargs.get("subagents", []))
        return real_create(*args, **kwargs)

    monkeypatch.setattr(deepagents, "create_deep_agent", _capturing_create)
    _reload_subagents()

    import agent as agent_module
    importlib.reload(agent_module)

    by_name = {s["name"]: s for s in captured_subagents}

    topic = by_name["topic-generator"]
    assert any(getattr(t, "name", "") == "save_generated_topic" for t in topic["tools"])
    assert any(getattr(t, "name", "") == "sync_topic_to_feishu" for t in topic["tools"])

    copy = by_name["copy-generator"]
    assert any(getattr(t, "name", "") == "save_generated_copy" for t in copy["tools"])
    assert any(getattr(t, "name", "") == "sync_copy_to_feishu" for t in copy["tools"])

    state = by_name["state-manager"]
    assert any(getattr(t, "name", "") == "save_session_snapshot" for t in state["tools"])
    assert any(getattr(t, "name", "") == "sync_diagnosis_to_feishu" for t in state["tools"])


def test_knowledge_retriever_subagent_uses_data_foundation_retrieval_tools(monkeypatch):
    """知识检索子智能体必须复用底层检索能力,不能另起一套数据通道。"""
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import deepagents

    captured_subagents = []
    real_create = deepagents.create_deep_agent

    def _capturing_create(*args, **kwargs):
        captured_subagents.extend(kwargs.get("subagents", []))
        return real_create(*args, **kwargs)

    monkeypatch.setattr(deepagents, "create_deep_agent", _capturing_create)
    _reload_subagents()

    import agent as agent_module
    importlib.reload(agent_module)

    by_name = {s["name"]: s for s in captured_subagents}
    retriever = by_name["knowledge-atom-retriever"]
    tool_names = {getattr(t, "name", "") for t in retriever["tools"]}

    assert {
        "semantic_search_resources",
        "search_resources",
        "graph_expand",
        "get_resource",
    } <= tool_names
    assert "save_generated_topic" not in tool_names
    assert "save_generated_copy" not in tool_names
