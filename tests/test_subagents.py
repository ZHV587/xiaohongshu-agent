"""executor subagents 回归测试。

子代理已收敛为 4 个执行型重任务路径:knowledge-atom-retriever(重检索)、
persona-distiller(风格提炼)、benchmark-analyst(对标分析)与
expert-panel-debater(多专家诊断)。原 thin 持久化子代理 topic-generator/
copy-generator/state-manager 已移除,落库/同步由主控用工具直调。
"""
from unittest.mock import Mock

import subagents_executor
from data_foundation.evidence import EvidencePackage
from subagents_executor import (
    EXECUTOR_SUBAGENT_NAMES,
    build_knowledge_atom_retriever,
    build_persona_distiller,
    build_imitation_writer,
    build_executor_subagents,
)


def _registry():
    r = Mock()
    r.get_pool.return_value = []
    return r


def test_executor_subagent_names_converged_to_eight():
    """子代理为 8 个:重检索、风格提炼、对标分析、多专家诊断、内容地图、自学课程、文案协处理、两段式仿写。"""
    assert EXECUTOR_SUBAGENT_NAMES == frozenset(
        {
            "knowledge-atom-retriever",
            "persona-distiller",
            "benchmark-analyst",
            "expert-panel-debater",
            "content-system-ingestor",
            "curriculum-designer",
            "copywriting-coprocessor",
            "imitation-writer",
        }
    )
    for removed in ("build_topic_generator", "build_copy_generator", "build_state_manager"):
        assert not hasattr(subagents_executor, removed), (
            f"{removed} 应已移除,职责收回主控直调"
        )


def test_imitation_writer_tools_and_contract():
    """两段式仿写:必须能 get_resource 精读范本原文;prompt 强调原文原样 + 两段(拆解+成品)。"""
    ag = build_imitation_writer(_registry(), Mock())
    assert ag["name"] == "imitation-writer"
    names = {t.name for t in ag["tools"]}
    assert {"get_resource", "retrieve_knowledge"} <= names
    assert {"search_resources", "semantic_search_resources", "graph_expand"}.isdisjoint(names)
    sp = ag["system_prompt"]
    # 范本原文原样铁律 + 两段式 + 学套路(形似不照抄)
    assert "范本原文" in sp or "原文" in sp
    assert "get_resource" in sp
    assert "拆解" in sp and "套路" in sp
    # 落库/同步类工具不应挂在仿写子代理上(职责收回主控直调)
    assert "save_generated_copy" not in names
    assert "adopt_online_notes" not in names


def test_build_executor_subagents_includes_imitation_writer():
    subs = build_executor_subagents(_registry(), Mock())
    assert "imitation-writer" in {s["name"] for s in subs}
    assert len(subs) == 8


def test_persona_distiller_tools():
    ag = build_persona_distiller(_registry(), Mock())
    names = {t.name for t in ag["tools"]}
    assert {"get_resource"} <= names
    assert "SKILL.md" in ag["system_prompt"]
    assert "写入 /.agents/skills" not in ag["system_prompt"]
    assert "返回" in ag["system_prompt"]


def test_knowledge_atom_retriever_tools():
    ag = build_knowledge_atom_retriever(_registry(), Mock())
    names = {t.name for t in ag["tools"]}
    assert {"retrieve_knowledge", "get_resource"} <= names
    assert {"semantic_search_resources", "search_resources", "graph_expand"}.isdisjoint(names)
    assert "save_generated_topic" not in names
    assert "save_generated_copy" not in names


def test_knowledge_atom_retriever_returns_structured_evidence():
    """重检索子代理必须以 EvidencePackage 作为结构化输出契约,产出结构化证据包。

    response_format 由裸 Pydantic 改为 ToolStrategy(EvidencePackage):走 tool-calling 提取,
    规避 anthropic 原生结构化输出在中转网关下偶发返空/非 JSON 的 StructuredOutputValidationError。
    契约 schema 仍是 EvidencePackage,断言深入 ToolStrategy.schema。"""
    from langchain.agents.structured_output import ToolStrategy

    ag = build_knowledge_atom_retriever(_registry(), Mock())
    rf = ag.get("response_format")
    assert isinstance(rf, ToolStrategy)
    assert rf.schema is EvidencePackage


def test_build_executor_subagents_returns_declared_names():
    agents = build_executor_subagents(_registry(), Mock())
    names = {a["name"] for a in agents}
    assert names == EXECUTOR_SUBAGENT_NAMES
