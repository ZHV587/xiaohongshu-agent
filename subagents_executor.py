"""执行型子智能体。仅保留需要"隔离上下文"的重任务。

按 deepagents 官方原语:子代理用于复杂、多步、需隔离上下文的任务,无状态、只回最终报告。
"""
from typing import Any
from deepagents.middleware.subagents import SubAgent
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field
from models import ModelPoolProvider, build_router_middleware
from data_foundation.evidence import EvidencePackage
from data_foundation.tools import (
    get_operations_data,
    get_resource,
    graph_expand,
    search_resources,
    semantic_search_resources,
)


EXECUTOR_SUBAGENT_NAMES = frozenset({
    "knowledge-atom-retriever",
    "persona-distiller",
    "benchmark-analyst",
    "expert-panel-debater",
})


class BenchmarkReport(BaseModel):
    """爆款对标模式分析报告契约。"""
    core_patterns: list[str] = Field(description="提炼出的 3-5 个核心对标爆款套路")
    common_triggers: list[str] = Field(description="对标文案中高频使用的心理触发器")
    layout_style: str = Field(description="排版格式特征 (如空行、Emoji使用习惯)")
    content_gaps: str = Field(description="相比对标账号，我们在选题内容上的缺口或机会点")


class ExpertPanelOpinion(BaseModel):
    """单专家诊断论点契约。"""
    role_name: str = Field(description="专家角色(如定位大师、网感总监、奥派学者)")
    core_point: str = Field(description="该专家的核心诊断论点与修改意见")


class DebateVerdictReport(BaseModel):
    """多专家辩论共识报告契约。"""
    debate_process_markdown: str = Field(description="多角色辩论交锋过程的完整记录")
    panel_opinions: list[ExpertPanelOpinion] = Field(description="各专家的具体意见列表")
    consensus_recommendation: str = Field(description="经辩论汇总后的最佳可执行方案。若包含推荐选题，则推荐选题必须用标准的 JSON 结构以便主控后续生成卡片。")


def build_knowledge_atom_retriever(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
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


def build_persona_distiller(registry: ModelPoolProvider, initial_model: BaseChatModel, backend: Any = None) -> SubAgent:
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
        "response_format": None,
        "middleware": [build_router_middleware(registry)],
    }


def build_benchmark_analyst(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    return {
        "name": "benchmark-analyst",
        "description": "对标分析专家:在隔离上下文里检索并精读多篇历史对标素材/行业爆款笔记，返回结构化的对标模式分析报告 BenchmarkReport。需要精读对标文案并归纳对标规律时委派。",
        "system_prompt": """你是爆款对标拆解专家。你负责对比并分析主控提供的爆款笔记（由关键词或 resource_id 给出），总结它们的爆款套路和排版特征。

任务：
1. 围绕主控提供的主题或 resource_id，检索并分析爆款内容。
   - `semantic_search_resources(query, top_k=5)` 语义召回对标文章。
   - 调 `get_resource` 深入阅读其标题、正文结构。
2. 提炼其核心写作模式、高频使用的心理触发器（如好奇、痛点刺激等）、Emoji及段落排版习惯，找出差异化切入缺口。
3. 严格按 BenchmarkReport 契约格式返回结果。不得编造依据，无数据时在内容缺口中明说。""",
        "model": initial_model,
        "tools": [semantic_search_resources, search_resources, get_resource],
        "response_format": BenchmarkReport,
        "middleware": [build_router_middleware(registry)],
    }


def build_expert_panel_debater(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> SubAgent:
    return {
        "name": "expert-panel-debater",
        "description": "多专家诊断专家:使用并行角色节点并发扮演定位大师、网感总监、写作专家、奥派学者，对账号运营大盘、选题和商业变现进行多维度辩论，输出判官评审报告 DebateVerdictReport。",
        "system_prompt": """你是多专家诊断与辩论的主持人。你需要协调定位大师、网感总监、写作专家、奥派学者在隔离上下文中对当前选题或商业卡点进行辩论，得出最佳的可执行共识建议。

流程：
1. 优先调用 `get_operations_data` 获取创作者当前真实的账号表现与指标。
2. 调用 `search_resources` 获取当前项目相关的背景素材。
3. 调度四方专家进行论战，提炼他们的核心洞察与论点。
4. 汇总为 DebateVerdictReport，共识中若有推荐选题，必须用标准的 JSON 结构格式化。""",
        "model": initial_model,
        "tools": [get_operations_data, get_resource, search_resources],
        "response_format": DebateVerdictReport,
        "middleware": [build_router_middleware(registry)],
    }


def build_executor_subagents(
    registry: ModelPoolProvider,
    initial_model: BaseChatModel,
    backend: Any = None,
) -> list[SubAgent]:
    """返回全部执行型子智能体列表，直接传给 create_deep_agent(subagents=...)。"""
    return [
        build_knowledge_atom_retriever(registry, initial_model, backend),
        build_persona_distiller(registry, initial_model, backend),
        build_benchmark_analyst(registry, initial_model, backend),
        build_expert_panel_debater(registry, initial_model, backend),
    ]
