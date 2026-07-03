from subagents_executor import build_executor_subagents, EXECUTOR_SUBAGENT_NAMES
from unittest.mock import Mock
from pathlib import Path
from deepagents.middleware.subagents import SubAgent
from pydantic import BaseModel


def test_subagents_refactoring_configs():
    r = Mock()
    r.get_pool.return_value = []

    subagents = build_executor_subagents(r, Mock())

    # 确认所有子代理被正确挂载，且名称正确
    names = {agent["name"] for agent in subagents}
    assert names == EXECUTOR_SUBAGENT_NAMES
    assert names == {
        "knowledge-atom-retriever",
        "persona-distiller",
        "benchmark-analyst",
        "expert-panel-debater",
        "content-system-ingestor",
        "curriculum-designer",
        "copywriting-coprocessor",
    }

    # 验证各子代理契约是否为 BaseModel
    for name in EXECUTOR_SUBAGENT_NAMES:
        agent = next(a for a in subagents if a["name"] == name)
        if name not in ("knowledge-atom-retriever", "persona-distiller"):
            assert issubclass(agent["response_format"], BaseModel)


def test_subagent_specs_use_only_official_deepagents_fields():
    r = Mock()
    r.get_pool.return_value = []

    subagents = build_executor_subagents(r, Mock())

    official_fields = set(SubAgent.__annotations__)
    for agent in subagents:
        assert set(agent) <= official_fields


def test_subagents_executor_is_typed_against_public_subagent_contract():
    src = Path("subagents_executor.py").read_text(encoding="utf-8")

    assert "from deepagents.middleware.subagents import SubAgent" in src
    assert "-> SubAgent" in src
    assert "-> list[SubAgent]" in src


def test_subagent_docs_avoid_private_deepagents_tracing_hooks():
    spec = Path("docs/superpowers/specs/2026-07-03-subagent-refactoring-spec.md").read_text(encoding="utf-8")
    plan = Path("docs/superpowers/plans/2026-07-03-subagent-refactoring.md").read_text(encoding="utf-8")

    assert "_subagent_tracing_context" not in spec
    assert "_subagent_tracing_context" not in plan
    assert "lc_agent_name" in spec
