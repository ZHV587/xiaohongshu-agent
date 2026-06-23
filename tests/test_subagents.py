"""executor subagents 回归测试。"""
from unittest.mock import Mock
from subagents_executor import (
    EXECUTOR_SUBAGENT_NAMES,
    build_knowledge_atom_retriever,
    build_topic_generator,
    build_copy_generator,
    build_state_manager,
    build_persona_distiller,
    build_executor_subagents,
)


def _registry():
    r = Mock()
    r.get_pool.return_value = []
    return r


def test_topic_generator_tools():
    ag = build_topic_generator(_registry(), Mock())
    names = {t.name for t in ag["tools"]}
    assert {"save_generated_topic", "sync_topic_to_feishu"} <= names


def test_copy_generator_tools():
    ag = build_copy_generator(_registry(), Mock())
    names = {t.name for t in ag["tools"]}
    assert {"save_generated_copy", "sync_copy_to_feishu"} <= names


def test_state_manager_tools():
    ag = build_state_manager(_registry(), Mock())
    names = {t.name for t in ag["tools"]}
    assert {"save_session_snapshot", "sync_diagnosis_to_feishu"} <= names


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


def test_build_executor_subagents_returns_declared_names():
    agents = build_executor_subagents(_registry(), Mock())
    names = {a["name"] for a in agents}
    assert names == EXECUTOR_SUBAGENT_NAMES
