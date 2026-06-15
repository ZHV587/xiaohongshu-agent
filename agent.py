"""agent 组装入口。create_deep_agent 装配主智能体 + 飞书工具 + 子智能体 + skill。"""
import os

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from prompts import MAIN_SYSTEM_PROMPT
from subagents import baokuan_analyst
from tools.feishu_bitable import read_xhs_data

load_dotenv()

# 主智能体默认 Claude(中文文案强);如需 GPT 改这里或用环境变量切换。
MAIN_MODEL = "anthropic:claude-sonnet-4-6"

model = init_chat_model(model=MAIN_MODEL, temperature=0.7)

# FilesystemBackend 让 skills 从磁盘加载、文件工具读写真实文件
# (默认 StateBackend 只读 LangGraph state 内的虚拟文件,看不到磁盘上的 skills/)
backend = FilesystemBackend(root_dir=os.getcwd())

agent = create_deep_agent(
    model=model,
    tools=[read_xhs_data],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
    backend=backend,
)
