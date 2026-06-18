"""agent 组装入口。create_deep_agent 装配主智能体 + 飞书工具 + 子智能体 + skill。"""
import os
if "NO_PROXY" in os.environ:
    del os.environ["NO_PROXY"]
if "no_proxy" in os.environ:
    del os.environ["no_proxy"]

# Patch deepagents model resolver to support LangChain RunnableWithFallbacks as a model
try:
    import deepagents._models
    import deepagents.graph
    import deepagents.middleware.summarization
    from langchain_core.runnables.fallbacks import RunnableWithFallbacks
    
    _orig_resolve_model = deepagents._models.resolve_model
    
    def custom_resolve_model(model):
        if isinstance(model, RunnableWithFallbacks):
            return model
        return _orig_resolve_model(model)
        
    deepagents._models.resolve_model = custom_resolve_model
    deepagents.graph.resolve_model = custom_resolve_model

    _orig_isinstance = isinstance
    def custom_isinstance(obj, class_or_tuple):
        from langchain_core.language_models import BaseChatModel
        if _orig_isinstance(obj, RunnableWithFallbacks):
            if class_or_tuple is BaseChatModel or (_orig_isinstance(class_or_tuple, tuple) and BaseChatModel in class_or_tuple):
                return True
            try:
                from langchain.chat_models import BaseChatModel as RuntimeBaseChatModel
                if class_or_tuple is RuntimeBaseChatModel or (_orig_isinstance(class_or_tuple, tuple) and RuntimeBaseChatModel in class_or_tuple):
                    return True
            except ImportError:
                pass
        return _orig_isinstance(obj, class_or_tuple)

    deepagents.middleware.summarization.isinstance = custom_isinstance
except Exception as e:
    import logging
    logging.getLogger(__name__).warning(f"Failed to patch deepagents resolve_model: {e}")

from deepagents import (
    FilesystemPermission,
    GeneralPurposeSubagentProfile,
    HarnessProfileConfig,
    RubricMiddleware,
    create_deep_agent,
    register_harness_profile,
)
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from backends import build_backend
from middlewares import build_retry_middleware
from prompts import MAIN_MODEL, MAIN_SYSTEM_PROMPT
from subagents import ANALYST_MODEL_NAME, baokuan_analyst
from tools.feishu_bitable import read_xhs_data
from tools.lark_cli import lark_cli, auto_update_lark_skills, auto_update_lark_cli
from tools.internal_server import start_internal_server

# 启动时自动从官方仓库同步最新的飞书技能（下载失败时自动静默降级，不影响启动）
if os.environ.get("DISABLE_AUTO_UPDATE") != "true":
    auto_update_lark_skills()
    auto_update_lark_cli()
start_internal_server()


load_dotenv()

# ── 安全加固:关掉本场景不需要的内置工具和默认子智能体 ──────────────────
# - execute: Shell 命令执行,文案场景不需要,留着是安全隐患
# - write_todos: todo list,两步式工作流(出选题→写文案)不需要
# - general-purpose: 默认通用子智能体,已有 baokuan-analyst,多一个会让模型选错
register_harness_profile("anthropic", HarnessProfileConfig(
    excluded_tools=frozenset({"execute", "write_todos"}),
    general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
))

# ── 动态解析大模型通用配置 ──────────────────────────────────────────
def build_llm_model(default_model: str):
    llm_model = os.environ.get("LLM_MODEL")
    llm_api_key = os.environ.get("LLM_API_KEY")
    llm_base_url = os.environ.get("LLM_BASE_URL")

    # 1. 确定并构造主模型
    primary_model_name = ""
    
    if llm_model and llm_api_key:
        if ":" in llm_model:
            provider, model_name = llm_model.split(":", 1)
        else:
            model_name = llm_model
            model_name_lower = model_name.lower()
            if "gpt" in model_name_lower or "o1" in model_name_lower or "o3" in model_name_lower:
                provider = "openai"
            elif "claude" in model_name_lower:
                provider = "anthropic"
            elif "gemini" in model_name_lower:
                provider = "google_genai"
            else:
                provider = "openai"
        
        primary_model_name = model_name

        # 动态对齐对应的底层环境变量
        if provider == "openai":
            os.environ["OPENAI_API_KEY"] = llm_api_key
            if llm_base_url:
                os.environ["OPENAI_API_BASE"] = llm_base_url
                os.environ["OPENAI_BASE_URL"] = llm_base_url
        elif provider == "anthropic":
            os.environ["ANTHROPIC_API_KEY"] = llm_api_key
            if llm_base_url:
                os.environ["ANTHROPIC_BASE_URL"] = llm_base_url
                os.environ["ANTHROPIC_API_BASE"] = llm_base_url

        primary_model = init_chat_model(
            model=model_name,
            model_provider=provider,
            temperature=0.7,
            timeout=60,
            max_retries=4,
            api_key=llm_api_key,
            base_url=llm_base_url if llm_base_url else None
        )
    else:
        # 默认 fallback
        primary_model_name = default_model
        primary_model = init_chat_model(
            model=default_model,
            temperature=0.7,
            timeout=60,
            max_retries=4,
        )

    # 2. 智能装配备用 Fallback 链：Kimi -> DeepSeek -> GPT -> Gemini -> Claude
    fallbacks = []
    
    # 辅助判断当前主模型特征，避免备用链路里填入主模型自身
    is_primary_kimi = "kimi" in primary_model_name.lower() or "moonshot" in primary_model_name.lower()
    is_primary_deepseek = "deepseek" in primary_model_name.lower()
    is_primary_gpt = "gpt" in primary_model_name.lower() or "o1" in primary_model_name.lower() or "o3" in primary_model_name.lower()
    is_primary_gemini = "gemini" in primary_model_name.lower()
    is_primary_claude = "claude" in primary_model_name.lower()

    # Kimi 备用
    kimi_key = os.environ.get("KIMI_API_KEY")
    if kimi_key and not is_primary_kimi:
        try:
            fallbacks.append(init_chat_model(
                model="moonshot-v1-8k",
                model_provider="openai",
                temperature=0.7,
                timeout=60,
                max_retries=2,
                api_key=kimi_key,
                base_url="https://api.moonshot.cn/v1"
            ))
        except Exception as e:
            logger.warning(f"Failed to initialize backup Kimi model: {e}")

    # DeepSeek 备用
    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    if deepseek_key and not is_primary_deepseek:
        try:
            fallbacks.append(init_chat_model(
                model="deepseek-chat",
                model_provider="openai",
                temperature=0.7,
                timeout=60,
                max_retries=2,
                api_key=deepseek_key,
                base_url="https://api.deepseek.com/v1"
            ))
        except Exception as e:
            logger.warning(f"Failed to initialize backup DeepSeek model: {e}")

    # GPT 备用
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key and not is_primary_gpt:
        try:
            fallbacks.append(init_chat_model(
                model="gpt-4o",
                model_provider="openai",
                temperature=0.7,
                timeout=60,
                max_retries=2,
                api_key=openai_key,
                base_url="https://api.openai.com/v1"
            ))
        except Exception as e:
            logger.warning(f"Failed to initialize backup GPT model: {e}")

    # Gemini 备用
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key and not is_primary_gemini:
        try:
            fallbacks.append(init_chat_model(
                model="gemini-2.5-flash",
                model_provider="google_genai",
                temperature=0.7,
                timeout=60,
                max_retries=2,
                api_key=gemini_key,
            ))
        except Exception as e:
            logger.warning(f"Failed to initialize backup Gemini model: {e}")

    # Claude 备用
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key and not is_primary_claude:
        try:
            if anthropic_key != "sk-ant-test":
                fallbacks.append(init_chat_model(
                    model="claude-3-5-sonnet-latest",
                    model_provider="anthropic",
                    temperature=0.7,
                    timeout=60,
                    max_retries=2,
                    api_key=anthropic_key,
                    base_url="https://api.anthropic.com"
                ))
        except Exception as e:
            logger.warning(f"Failed to initialize backup Claude model: {e}")

    # 3. 组合 fallback 链
    if fallbacks:
        return primary_model.with_fallbacks(fallbacks)
    return primary_model

model = build_llm_model(MAIN_MODEL)

# 三路由 CompositeBackend:/skills/(磁盘共享只读)、/shared/(Store 共享)、
# /drafts/ 及默认(State 随会话隔离)。详见 backends.py。
backend = build_backend()

# ── 文案质量评分中间件 ────────────────────────────────────────────
# 生成文案后自动评估质量,不合格让智能体重写(最多重试 2 轮)。
# 用便宜的 Haiku 做评分模型,控制成本。
# 仅当调用方传入 rubric 时才激活,平时不增加开销。
rubric_middleware = RubricMiddleware(
    model=ANALYST_MODEL_NAME,
    system_prompt="""你是小红书文案质量检查员。评估文案是否满足以下标准:
1. 标题有钩子,不平淡,能引起点击欲望
2. 正文像真人写的小红书笔记,无 AI 腔(不要"首先/其次/总之"、不要"在…领域"等八股)
3. 有 emoji 点缀但不过度
4. 标签 5~10 个且与内容相关
5. 选题和文案有数据依据,不是凭空编的
6. 文案有记忆点,读完能记住一两个关键信息

如果文案不满足以上标准,请给出具体修改建议。""",
    max_iterations=2,
)

agent = create_deep_agent(
    model=model,
    tools=[read_xhs_data, lark_cli],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
    backend=backend,
    middleware=[build_retry_middleware(), rubric_middleware],
    # 自学习记忆:团队共享(全员一份方法论)+ 用户私有(按 open_id 隔离)。
    # 团队在前、个人在后 —— sources 按序拼接注入,个人记忆覆盖团队默认。
    # MemoryMiddleware 用 edit_file 写回,文件不存在时首轮跳过、由 agent 创建。
    memory=["/memories/team/AGENTS.md", "/user-memories/AGENTS.md"],
    # ── 文件权限:限制可写路径,防止模型乱写 ─────────────────────────
    # 规则按声明顺序匹配,首条命中即停止。读操作全部放行,写操作只允许白名单路径。
    permissions=[
        FilesystemPermission(operations=["read"], paths=["/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/drafts/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/analysis/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/shared/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/user-memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ],
    # LangSmith 追踪时显示的名称,方便在 trace 里快速识别。
    name="xhs-content-agent",
)
