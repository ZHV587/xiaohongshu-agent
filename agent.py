"""agent 组装入口。xhs-router 主智能体 + Skills + 4 个执行型子智能体。"""
import os
if "NO_PROXY" in os.environ:
    del os.environ["NO_PROXY"]
if "no_proxy" in os.environ:
    del os.environ["no_proxy"]

import json
from deepagents import (
    FilesystemPermission,
    HarnessProfileConfig,
    RubricMiddleware,
    create_deep_agent,
    register_harness_profile,
)
from dotenv import load_dotenv

from backends import build_backend
from content_rubric import ContentRubricActivator
from middlewares import build_retry_middleware
from model_registry import ModelRegistry
from models import build_initial_placeholder_model, build_router_middleware
from prompts import MAIN_SYSTEM_PROMPT
from rubric_model import RegistryRoutedChatModel
from subagents_executor import build_executor_subagents
from data_foundation.tools import data_foundation_tools
from tools.feishu_actions import feishu_action_tools
from tools.lark_mcp import load_lark_mcp_tools


load_dotenv()

with open("deepagents_harness.json", "r", encoding="utf-8") as f:
    register_harness_profile("openai", HarnessProfileConfig.from_dict(json.load(f)))

initial_model = build_initial_placeholder_model()
model_registry = ModelRegistry()
backend = build_backend()

rubric_middleware = RubricMiddleware(
    model=RegistryRoutedChatModel(model_registry, initial_model),
    system_prompt="""你是小红书文案质量检查员。评估文案是否满足以下标准:
1. 标题有钩子,不平淡,能引起点击欲望
2. 正文像真人写的小红书笔记,无 AI 腔(不要"首先/其次/总之"、不要"在…领域"等八股)
3. 有 emoji 点缀但不过度
4. 标签 5~10 个且与内容相关
5. 使用数据时,选题和文案必须带关键依据摘要及对应 resource_id,不能只声称"来自数据"
6. 检查来源 source_updated_at 与 indexed_at:源端过时不能被包装成当前事实,索引时间不能冒充源端更新时间
7. 删除或改写检索内容无法支持的无依据断言;创意推断必须明确是推断,不能冒充事实
8. 没有可用来源时必须明确说"当前数据不足",并建议同步飞书资源或补充数据,不得凭空编造
9. 文案有记忆点,读完能记住一两个关键信息

如果文案不满足以上标准,请给出具体修改建议。""",
    max_iterations=2,
)
content_rubric_activator = ContentRubricActivator()

agent = create_deep_agent(
    model=initial_model,
    tools=data_foundation_tools + feishu_action_tools + load_lark_mcp_tools(),
    system_prompt=MAIN_SYSTEM_PROMPT,
    skills=["/skills/"],
    subagents=build_executor_subagents(model_registry, initial_model, backend),
    backend=backend,
    interrupt_on={
        "execute_lark_command": True,
        "sync_copy_to_feishu": True,
        "sync_topic_to_feishu": True,
        "sync_diagnosis_to_feishu": True,
        "send_review_notification": True,
    },
    checkpointer=True,
    middleware=[
        build_retry_middleware(),
        rubric_middleware,
        content_rubric_activator,
        build_router_middleware(model_registry),
    ],
    memory=["/memories/team/AGENTS.md", "/user-memories/AGENTS.md"],
    permissions=[
        FilesystemPermission(operations=["read"], paths=["/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/user-memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ],
    name="xhs-router",
)
