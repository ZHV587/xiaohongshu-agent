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

# FilesystemBackend 让 skills 从磁盘加载、文件工具读写真实文件。
# virtual_mode=True:所有路径都是锚定在项目目录下的虚拟绝对路径
# (如 /skills/、/analysis/、/drafts/、/shared/),映射到磁盘对应子目录,
# 避免 Windows 绝对路径被 backend 拒绝,同时提供路径沙箱。
backend = FilesystemBackend(root_dir=os.getcwd(), virtual_mode=True)

agent = create_deep_agent(
    model=model,
    tools=[read_xhs_data],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
    backend=backend,
)
