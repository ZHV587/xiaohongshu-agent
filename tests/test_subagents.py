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
    build_executor_subagents,
)


def _registry():
    r = Mock()
    r.get_pool.return_value = []
    return r


def test_executor_subagent_names_converged_to_seven():
    """子代理已升级为 7 个，包含重检索、风格提炼、对标分析、多专家诊断、内容地图、自学课程和文案协处理。"""
    assert EXECUTOR_SUBAGENT_NAMES == frozenset(
        {
            "knowledge-atom-retriever",
            "persona-distiller",
            "benchmark-analyst",
            "expert-panel-debater",
            "content-system-ingestor",
            "curriculum-designer",
            "copywriting-coprocessor",
        }
    )
    for removed in ("build_topic_generator", "build_copy_generator", "build_state_manager"):
        assert not hasattr(subagents_executor, removed), (
            f"{removed} 应已移除,职责收回主控直调"
        )


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
    assert {"semantic_search_resources", "search_resources", "graph_expand", "get_resource"} <= names
    assert "save_generated_topic" not in names
    assert "save_generated_copy" not in names


def test_knowledge_atom_retriever_returns_structured_evidence():
    """重检索子代理必须以 EvidencePackage 作为 response_format,产出结构化证据包。"""
    ag = build_knowledge_atom_retriever(_registry(), Mock())
    assert ag.get("response_format") is EvidencePackage


def test_build_executor_subagents_returns_declared_names():
    agents = build_executor_subagents(_registry(), Mock())
    names = {a["name"] for a in agents}
    assert names == EXECUTOR_SUBAGENT_NAMES
