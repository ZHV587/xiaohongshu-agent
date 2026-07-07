"""agent 组装入口。xhs-router 主智能体 + Skills + 4 个执行型子智能体。"""
import os
if "NO_PROXY" in os.environ:
    del os.environ["NO_PROXY"]
if "no_proxy" in os.environ:
    del os.environ["no_proxy"]

import langchain
# 生产默认关闭 verbose 调试日志:debug 会把 prompt 与模型 I/O(可能含敏感内容)打进日志,
# 有性能开销且违背"日志不打敏感信息"铁律。需要排查时设 LANGCHAIN_DEBUG=1 临时开启。
langchain.debug = os.environ.get("LANGCHAIN_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")

import json
from deepagents import (
    FilesystemPermission,
    HarnessProfileConfig,
    create_deep_agent,
    register_harness_profile,
)
from dotenv import load_dotenv

from backends import build_backend
from middlewares import build_retry_middleware, FrontendStateMiddleware
from model_registry import ModelRegistry
from models import build_initial_placeholder_model, build_router_middleware
from prompts import MAIN_SYSTEM_PROMPT
from subagents_executor import build_executor_subagents
from data_foundation.agent_trace import trace_tool
from data_foundation.tools import data_foundation_tools
from tools.feishu_actions import feishu_action_tools
from tools.redfox_search import search_xhs_online
from tools.online_adopt import adopt_online_notes
from tools.lark_cli import lark_cli


load_dotenv()

with open("deepagents_harness.json", "r", encoding="utf-8") as f:
    _harness_cfg = json.load(f)
# harness profile 按模型 provider 匹配:create_deep_agent 传入模型实例时,deepagents 用
# get_model_provider(model) 解析 key(openai→"openai"、anthropic→"anthropic")。这里的配置
# (排除 execute 工具 + 关 general-purpose 子 agent)与 provider 无关,故对所有受支持 provider
# 都注册,避免切换 LLM_PROVIDER 后 profile 静默失效、execute/通用子 agent 被意外启用。
for _provider_key in ("openai", "anthropic", "google_genai"):
    register_harness_profile(_provider_key, HarnessProfileConfig.from_dict(_harness_cfg))

initial_model = build_initial_placeholder_model()
model_registry = ModelRegistry()
backend = build_backend()

TRACE_TOOL_STAGES = {
    "semantic_search_resources": ("retrieve", "查找相关素材"),
    "search_resources": ("retrieve", "按关键词补查素材"),
    "search_local_note_cards": ("retrieve", "检索本地笔记卡"),
    "get_resource": ("retrieve", "打开原文细看"),
    "graph_expand": ("retrieve", "顺着图谱找关联"),
    "get_operations_data": ("retrieve", "读取运营数据"),
    "get_resource_performance": ("retrieve", "读取效果表现"),
    "save_generated_topic": ("persist", "保存选题"),
    "save_generated_copy": ("persist", "保存文案"),
    "save_user_feedback": ("persist", "沉淀反馈"),
    "save_performance_metric": ("persist", "沉淀效果指标"),
    "sync_copy_to_feishu": ("persist", "同步文案到飞书"),
    "sync_topic_to_feishu": ("persist", "同步选题到飞书"),
    "sync_diagnosis_to_feishu": ("persist", "同步诊断到飞书"),
    "send_review_notification": ("persist", "发送审阅通知"),
    "adopt_online_notes": ("persist", "采纳线上笔记"),
    "search_xhs_online": ("retrieve", "搜索小红书线上"),
}


def _with_trace(tools):
    wrapped = []
    for tool_obj in tools:
        stage = TRACE_TOOL_STAGES.get(getattr(tool_obj, "name", ""))
        wrapped.append(trace_tool(tool_obj, stage_id=stage[0], label=stage[1]) if stage else tool_obj)
    return wrapped


assembled_tools = _with_trace(data_foundation_tools + feishu_action_tools + [search_xhs_online, adopt_online_notes, lark_cli])

agent = create_deep_agent(
    model=initial_model,
    tools=assembled_tools,
    system_prompt=MAIN_SYSTEM_PROMPT,
    skills=["/skills/"],
    subagents=build_executor_subagents(model_registry, initial_model, backend),
    backend=backend,
    interrupt_on={
        "lark_cli": True,
        "sync_copy_to_feishu": True,
        "sync_topic_to_feishu": True,
        "sync_diagnosis_to_feishu": True,
        "send_review_notification": True,
        # 采纳:笔记数据由前端经 InjectedState 直传(权威),编辑无意义,只允许批准/驳回。
        "adopt_online_notes": {"allowed_decisions": ["approve", "reject"]},
    },
    checkpointer=True,
    # ⚠️ Middleware 顺序是 load-bearing,改动前先想清楚:
    #   retry(最外) → frontend-state → router(最内)
    # - retry 在最外:整轮模型调用(含 router 的网关 failover)失败耗尽后仍能重来一次。
    # - router 在最内:贴近真实模型调用,质量优先热切(override 最强健康候选)由它发起。
    middleware=[
        build_retry_middleware(),
        FrontendStateMiddleware(),
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
