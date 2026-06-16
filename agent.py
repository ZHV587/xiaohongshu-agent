"""agent 组装入口。create_deep_agent 装配主智能体 + 飞书工具 + 子智能体 + skill。"""
from deepagents import create_deep_agent
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from backends import build_backend
from middlewares import build_retry_middleware
from prompts import MAIN_MODEL, MAIN_SYSTEM_PROMPT
from subagents import baokuan_analyst
from tools.feishu_bitable import read_xhs_data

load_dotenv()

# 主智能体默认 Claude(中文文案强);如需 GPT 改这里或用环境变量切换。
# timeout/max_retries:中转(43.255.157.166)偶发 502,加单次超时+重试,
# 避免单次调用卡死拖到几分钟才报错(中转通常重试 2-3 次内恢复)。
model = init_chat_model(
    model=MAIN_MODEL,
    temperature=0.7,
    timeout=60,
    max_retries=4,
)

# 三路由 CompositeBackend:/skills/(磁盘共享只读)、/shared/(Store 共享)、
# /drafts/ 及默认(State 随会话隔离)。详见 backends.py。
backend = build_backend()

agent = create_deep_agent(
    model=model,
    tools=[read_xhs_data],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
    backend=backend,
    middleware=[build_retry_middleware()],
)
