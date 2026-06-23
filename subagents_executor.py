"""执行型子智能体。仅保留需要工具调用的持久化任务，对话逻辑已迁移至 .agents/skills/xhs-*/SKILL.md。"""
from typing import Any
from langchain_core.language_models import BaseChatModel
from deepagents import create_deep_agent
from models import ModelPoolProvider, build_router_middleware
from data_foundation.tools import get_resource, save_generated_topic, save_generated_copy, save_session_snapshot
from tools.feishu_actions import sync_topic_to_feishu, sync_copy_to_feishu, sync_diagnosis_to_feishu


def build_topic_generator(registry: ModelPoolProvider, initial_model: BaseChatModel, backend: Any = None) -> dict:
    return {
        "name": "topic-generator",
        "description": "根据选题分析结论生成3~5个选题卡片，持久化到Postgres数据库并同步飞书多维表格。",
        "system_prompt": """你是选题卡片生成与持久化专家。

任务：根据传入的选题方向、分析结论和对标依据，生成3~5个具体选题卡片，然后持久化。

每个选题卡片必须包含：具体选题名、切入角度、目标受众、预期痛点、以及所依据的真实 resource_id 列表。

执行顺序：
1. 生成选题卡片（JSON格式）
2. 调用 save_generated_topic(direction, topics, evidence) 存入数据库
3. 调用 sync_topic_to_feishu(direction, topics) 同步飞书

返回：数据库 resource_id 列表 + 飞书表格链接。""",
        "model": initial_model,
        "tools": [save_generated_topic, sync_topic_to_feishu],
        "middleware": [build_router_middleware(registry)],
    }


def build_copy_generator(registry: ModelPoolProvider, initial_model: BaseChatModel, backend: Any = None) -> dict:
    return {
        "name": "copy-generator",
        "description": "将已确认的文案草稿持久化到Postgres数据库并同步飞书多维表格。",
        "system_prompt": """你是文案持久化专家。

任务：接收已经确认的文案标题、正文、标签和来源选题，持久化到数据库和飞书。

执行顺序：
1. 调用 save_generated_copy(title, body, tags, source_topic, evidence) 存入数据库
2. 调用 sync_copy_to_feishu(title, content, tags) 同步飞书草稿

返回：数据库 resource_id + 飞书草稿链接。""",
        "model": initial_model,
        "tools": [save_generated_copy, sync_copy_to_feishu],
        "middleware": [build_router_middleware(registry)],
    }


def build_state_manager(registry: ModelPoolProvider, initial_model: BaseChatModel, backend: Any = None) -> dict:
    return {
        "name": "state-manager",
        "description": "将会话的关键诊断结论持久化到数据库并同步飞书，支持后续 restore 恢复。",
        "system_prompt": """你是会话状态持久化专家。

任务：将传入的诊断结论、定位报告或会话摘要持久化到系统数据库和飞书云端。

执行顺序：
1. 调用 save_session_snapshot(project_name, title, content) 存入数据库
2. 调用 sync_diagnosis_to_feishu(project_name, title, content) 同步飞书

返回：数据库 resource_id + 飞书表格链接。""",
        "model": initial_model,
        "tools": [save_session_snapshot, sync_diagnosis_to_feishu, get_resource],
        "middleware": [build_router_middleware(registry)],
    }


def build_persona_distiller(registry: ModelPoolProvider, initial_model: BaseChatModel, backend: Any = None) -> dict:
    return {
        "name": "persona-distiller",
        "description": "分析博主历史爆款素材，逆向提炼风格DNA，生成符合DeepAgents规范的博主人设SKILL.md文件。",
        "system_prompt": """你是博主风格DNA提炼专家。

任务：分析创作者的历史爆款文案，提炼风格人设，写入SKILL.md文件。

流程：
1. 调用 get_resource(resource_id) 精读历史素材
2. 提炼以下维度：
   - 思维模型（3~5个看待世界的视角）
   - 决策偏好（写作抉择原则）
   - 表达DNA（语气、词汇、排版习惯）
   - 负面禁忌（硬性禁止的AI腔词汇）
3. 生成符合DeepAgents规范的完整SKILL.md，写入 /.agents/skills/blogger-style-{name}/SKILL.md

SKILL.md 必须包含：
- YAML Frontmatter：name: blogger-style-{name}，triggers 包含该博主名
- 思维模型、决策偏好、表达DNA、负面禁忌四个部分""",
        "model": initial_model,
        "tools": [get_resource],
        "middleware": [build_router_middleware(registry)],
    }


def build_executor_subagents(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> list[dict]:
    """返回全部执行型子智能体列表，直接传给 create_deep_agent(subagents=...)。"""
    return [
        build_topic_generator(registry, initial_model, backend),
        build_copy_generator(registry, initial_model, backend),
        build_state_manager(registry, initial_model, backend),
        build_persona_distiller(registry, initial_model, backend),
    ]
