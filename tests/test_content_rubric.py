"""Content rubric activation behavior."""

import pytest
from deepagents import RubricMiddleware
from deepagents.middleware.rubric import GraderResponse
from langchain_core.messages import AIMessage

from content_rubric import ContentRubricActivator, DEFAULT_CONTENT_RUBRIC


@pytest.mark.parametrize("block_name", ["xhs_topics", "xhs_copy"])
def test_structured_content_activates_default_rubric(block_name):
    middleware = ContentRubricActivator()
    state = {"messages": [AIMessage(content=f"```{block_name}\n{{}}\n```")]}

    assert middleware.after_agent(state, runtime=None) == {
        "rubric": DEFAULT_CONTENT_RUBRIC
    }


def test_ordinary_response_does_not_activate_rubric():
    middleware = ContentRubricActivator()
    state = {"messages": [AIMessage(content="今天先聊聊选题思路。")]}

    assert middleware.after_agent(state, runtime=None) is None


def test_caller_rubric_is_preserved():
    middleware = ContentRubricActivator()
    state = {
        "rubric": "调用方自定义标准",
        "messages": [AIMessage(content="```xhs_copy\n{}\n```")],
    }

    assert middleware.after_agent(state, runtime=None) is None
    assert state["rubric"] == "调用方自定义标准"


def test_only_final_ai_response_can_activate_rubric():
    middleware = ContentRubricActivator()
    state = {
        "messages": [
            AIMessage(content="```xhs_topics\n{}\n```"),
            AIMessage(content="这是最终的普通回复。"),
        ]
    }

    assert middleware.after_agent(state, runtime=None) is None


def test_activator_handoff_causes_real_rubric_evaluation():
    activator = ContentRubricActivator()
    rubric = RubricMiddleware(model="openai:test-model", max_iterations=1)

    class _Grader:
        def invoke(self, _input):
            return {
                "structured_response": GraderResponse(
                    result="satisfied",
                    explanation="依据完整",
                    criteria=[],
                )
            }

    rubric._grader = _Grader()
    state = {"messages": [AIMessage(content="```xhs_copy\n{}\n```")]}
    state.update(activator.after_agent(state, runtime=None) or {})

    result = rubric.after_agent(state, runtime=None)

    assert result is not None
    assert result["_rubric_status"] == "satisfied"
    assert result["_rubric_iterations"] == 1
