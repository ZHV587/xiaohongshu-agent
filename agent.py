"""agent 组装入口。create_deep_agent 装配主智能体 + 飞书工具 + 子智能体 + skill。"""
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from deepagents import create_deep_agent

from prompts import MAIN_SYSTEM_PROMPT
from subagents import baokuan_analyst
from tools.feishu_bitable import read_xhs_data

load_dotenv()

# 主智能体默认 Claude(中文文案强);如需 GPT 改这里或用环境变量切换。
MAIN_MODEL = "anthropic:claude-sonnet-4-6"

model = init_chat_model(model=MAIN_MODEL, temperature=0.7)

agent = create_deep_agent(
    model=model,
    tools=[read_xhs_data],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
)
