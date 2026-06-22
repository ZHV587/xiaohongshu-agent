"""agent 组装入口。create_deep_agent 装配主智能体 + 飞书工具 + 子智能体 + skill。"""
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
from subagents import build_baokuan_analyst

from data_foundation.tools import data_foundation_tools
from tools.feishu_actions import feishu_action_tools
from tools.lark_mcp import load_lark_mcp_tools


load_dotenv()

# ── 安全加固:关掉本场景不需要的内置工具和默认子智能体 ──────────────────
# - execute: Shell 命令执行,文案场景不需要,留着是安全隐患
# - write_todos: 已重新启用，方便长任务执行规划
# - general-purpose: 默认通用子智能体,已有 baokuan-analyst,多一个会让模型选错
# 采用官方推荐的外部声明式配置文件进行初始化，彻底移除 Python 代码级硬编码配置
with open("deepagents_harness.json", "r", encoding="utf-8") as f:
    register_harness_profile("openai", HarnessProfileConfig.from_dict(json.load(f)))

# ── 高质量模型自主调度 ──────────────────────────────────────────────
# 单一数据源:运行时模型池只来自 config-center(经探测∩白名单按质量序),
# 由 server lifespan 启动对齐 + 定时健康探测 + 配置事件三条引线填充/刷新。
# 这里 registry 创建即空,不灌 env —— env 不再是平行运行时配置源。
#
# initial_model:create_deep_agent / 子智能体装配时各需一个 BaseChatModel 实例作占位。
# 用 env 构一个(不探测不联网、不进 registry、非配置源);运行时主/子 agent 的真实调用
# 经 ModelRouterMiddleware 被 registry 池覆盖,registry 空时(填充前/测试态)才落到占位上。
initial_model = build_initial_placeholder_model()
model_registry = ModelRegistry()

# 三路由 CompositeBackend:/skills/(磁盘共享只读)、/shared/(Store 共享)、
# /drafts/ 及默认(State 随会话隔离)。详见 backends.py。
backend = build_backend()

# ── 文案质量评分中间件 ────────────────────────────────────────────
# 生成文案后自动评估质量,不合格让智能体重写(最多重试 2 轮)。
# rubric 的 grader 是 deepagents 内部 create_agent 子图,不经 ModelRouterMiddleware,
# 故 model 传 RegistryRoutedChatModel:它每次评分从 registry 取当前最强候选(空池回退
# 占位),让评分也吃 config-center 热重载,质量优先不降级,且 env 不再钉死评分模型。
rubric_middleware = RubricMiddleware(
    model=RegistryRoutedChatModel(model_registry, initial_model),
    system_prompt="""你是小红书文案质量检查员。评估文案是否满足以下标准:
1. 标题有钩子,不平淡,能引起点击欲望
2. 正文像真人写的小红书笔记,无 AI 腔(不要"首先/其次/总之"、不要"在…领域"等八股)
3. 有 emoji 点缀但不过度
4. 标签 5~10 个且与内容相关
5. 使用数据时,选题和文案必须带关键依据摘要及对应 resource_id,不能只声称“来自数据”
6. 检查来源 source_updated_at 与 indexed_at:源端过时不能被包装成当前事实,索引时间不能冒充源端更新时间
7. 删除或改写检索内容无法支持的无依据断言;创意推断必须明确是推断,不能冒充事实
8. 没有可用来源时必须明确说“当前数据不足”,并建议同步飞书资源或补充数据,不得凭空编造
9. 文案有记忆点,读完能记住一两个关键信息

如果文案不满足以上标准,请给出具体修改建议。""",
    max_iterations=2,
)
content_rubric_activator = ContentRubricActivator()

agent = create_deep_agent(
    model=initial_model,
    tools=data_foundation_tools + feishu_action_tools + load_lark_mcp_tools(),
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[build_baokuan_analyst(model_registry, initial_model)],
    backend=backend,
    interrupt_on={
        "execute_lark_command": True,
        "sync_copy_to_feishu": True,
        "send_review_notification": True,
    },
    checkpointer=True,
    middleware=[
        build_retry_middleware(),
        rubric_middleware,
        content_rubric_activator,
        build_router_middleware(model_registry),
    ],
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
        FilesystemPermission(operations=["write"], paths=["/shared/**"], mode="interrupt"),
        FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/user-memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ],
    # LangSmith 追踪时显示的名称,方便在 trace 里快速识别。
    name="xhs-content-agent",
)
