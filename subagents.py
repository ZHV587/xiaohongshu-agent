"""子智能体定义。爆款分析子智能体在独立上下文拆解数据,结论落盘。"""
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

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
import logging
import os

from tools.feishu_bitable import read_xhs_data

logger = logging.getLogger(__name__)

# 本模块在 agent.py 里先于其 load_dotenv() 被 import,而下面 init_chat_model 在
# 模块加载时即构造,需要 ANTHROPIC_BASE_URL/KEY 已在环境里 —— 故这里自行加载 .env,
# 不依赖调用方的导入顺序(否则子智能体可能读不到中转 BASE_URL)。
load_dotenv()

# 子智能体默认用便宜快的模型(设计:子智能体用便宜快模型)。
# 模型名提取为常量,agent.py 的 RubricMiddleware 也用它(避免重复硬编码)。
ANALYST_MODEL_NAME = "anthropic:claude-haiku-4-5-20251001"

def build_analyst_model():
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
        primary_model_name = ANALYST_MODEL_NAME
        primary_model = init_chat_model(
            ANALYST_MODEL_NAME,
            timeout=60,
            max_retries=4,
        )

    # 2. 智能装配备用 Fallback 链：Kimi -> DeepSeek -> GPT -> Gemini -> Claude
    fallbacks = []
    
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

ANALYST_MODEL = build_analyst_model()

ANALYST_SYSTEM_PROMPT = """你是小红书爆款分析助手。你的任务是拆解给定方向的爆款笔记,
提炼可复用的创作规律,并把结论写入指定文件。

## 你的工具
- read_xhs_data():读取飞书表里的爆款数据(列名 + 数据行)
- write_file(file_path, content):保存你的分析结论

## 流程
1. 调 read_xhs_data 获取数据。你需自行判断哪列是标题、正文、互动数据(点赞/收藏)、
   话题标签等——列名可能不规范,按语义理解。
2. 筛选与任务给定方向相关的笔记。
3. 拆解并总结这些维度:
   - 选题角度:这些爆款都从什么角度切入
   - 标题套路:标题的结构、关键词、情绪词、数字/emoji 用法
   - 正文结构:开头怎么钩人、中间怎么展开、结尾怎么收
   - 情绪触发点:激发了读者什么情绪(种草/焦虑/共鸣/好奇)
   - 话题标签习惯:常用哪些标签、几个
4. 用 write_file 把结论写到任务里指定的文件路径(如 /analysis/<方向>.md)。

## 要求
- 结论要具体、可操作,引用数据里的真实例子,不要空泛。
- 如果某方向相关数据很少,如实说明,不要硬编。
- 输出中文。
"""

baokuan_analyst = {
    "name": "baokuan-analyst",
    "description": (
        "拆解飞书数据里某个方向的小红书爆款,提炼选题角度、标题套路、正文结构、"
        "情绪点与标签习惯。委派时请说明:分析哪个方向,以及把结论写到哪个文件路径"
        "(如 '分析露营装备方向,结论写到 /analysis/露营装备.md')。"
    ),
    "system_prompt": ANALYST_SYSTEM_PROMPT,
    "model": ANALYST_MODEL,
    "tools": [read_xhs_data],
}
