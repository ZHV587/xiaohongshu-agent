"""执行型子智能体。仅保留需要"隔离上下文"的重任务:重检索(knowledge-atom-retriever)与风格提炼(persona-distiller)。

按 deepagents 官方原语:子代理用于复杂、多步、需隔离上下文的任务,无状态、只回最终报告。
轻量检索、出选题、写文案、落库、同步均由主控用工具直调(见 prompts.py 的《检索与证据规约》与 §3),
不再设 thin 持久化子代理(原 topic-generator/copy-generator/state-manager 已移除,职责收回主控)。
"""
from typing import Any
from langchain_core.language_models import BaseChatModel
from models import ModelPoolProvider, build_router_middleware
from data_foundation.evidence import EvidencePackage
from data_foundation.tools import (
    get_resource,
    graph_expand,
    search_resources,
    semantic_search_resources,
)


EXECUTOR_SUBAGENT_NAMES = frozenset({
    "knowledge-atom-retriever",
    "persona-distiller",
})


def build_knowledge_atom_retriever(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> dict:
    return {
        "name": "knowledge-atom-retriever",
        "description": "重检索专用:在隔离上下文里大规模召回并精读多篇历史素材/知识原子/图谱上下文,返回结构化证据包 EvidencePackage。仅当需要精读大量全文时由主控委派。",
        "system_prompt": """你是知识原子检索专家,只负责找证据,不负责最终诊断或写作。

任务:围绕主控给出的问题/主题/创作目标,从数据底座大规模召回并精读,返回结构化证据包。

严格遵循主控《检索与证据规约》的检索顺序与口径(本子代理是"重检索"路径,适合精读大量全文):
1. `semantic_search_resources(query, top_k=10)` 语义召回为主
2. 语义不足/关键词明确时 `search_resources(query, limit=10)` 补全文
3. 选最相关的 3~8 个 resource_id;需要关联上下文时 `graph_expand(resource_ids, hops=1)`
4. 对最关键的若干 resource_id 调 `get_resource` 精读正文

按 EvidencePackage 结构返回(response_format 已强制):
- `retrieval_mode`:semantic / keyword_fallback / insufficient_relevance
- `evidence[]`:每条含 resource_id、title、summary、source_updated_at、indexed_at、score、why_selected
- `gaps`:证据不足或 retrieval_mode 为 insufficient_relevance 时,明确说明缺什么

时效/防伪:source_updated_at 与 indexed_at 严格区分,未知写"未知"不猜;
数据不足(insufficient_relevance)时 evidence 留空、gaps 说明,不编造、不强行用关键词凑。
只返回证据包,不写最终小红书文案、不保存数据、不同步飞书。""",
        "model": initial_model,
        "tools": [semantic_search_resources, search_resources, graph_expand, get_resource],
        "response_format": EvidencePackage,
        "middleware": [build_router_middleware(registry)],
    }


def build_persona_distiller(registry: ModelPoolProvider, initial_model: BaseChatModel, backend: Any = None) -> dict:
    return {
        "name": "persona-distiller",
        "description": "分析博主历史爆款素材，逆向提炼风格DNA，生成符合DeepAgents规范的博主人设SKILL.md草稿。",
        "system_prompt": """你是博主风格DNA提炼专家。

任务：分析创作者的历史爆款文案，提炼风格人设，返回一份可由用户审核的SKILL.md草稿内容。

流程：
1. 调用 get_resource(resource_id) 精读历史素材
2. 提炼以下维度：
   - 思维模型（3~5个看待世界的视角）
   - 决策偏好（写作抉择原则）
   - 表达DNA（语气、词汇、排版习惯）
   - 负面禁忌（硬性禁止的AI腔词汇）
3. 生成符合DeepAgents规范的完整SKILL.md草稿，并在最终回复中用 markdown 代码块返回，不执行文件写入

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
        build_knowledge_atom_retriever(registry, initial_model, backend),
        build_persona_distiller(registry, initial_model, backend),
    ]
