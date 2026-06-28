"""Content rubric activation behavior."""

from deepagents import RubricMiddleware
from langchain_core.messages import AIMessage

from content_rubric import ContentRubricActivator, DEFAULT_CONTENT_RUBRIC


def test_xhs_copy_activates_default_rubric():
    middleware = ContentRubricActivator()
    state = {"messages": [AIMessage(content="```xhs_copy\n{}\n```")]}

    assert middleware.after_agent(state, runtime=None) == {
        "rubric": DEFAULT_CONTENT_RUBRIC
    }


def test_xhs_topics_does_not_activate_rubric():
    """选题菜单(中间产物)不触发质检:其 evidence 由前端经 InjectedState 权威直传、
    结构性已保证,无需强模型 grader 兜;质检只收敛到 xhs_copy 这个最终交付物上。"""
    middleware = ContentRubricActivator()
    state = {"messages": [AIMessage(content="```xhs_topics\n{}\n```")]}

    assert middleware.after_agent(state, runtime=None) is None


def test_ordinary_response_does_not_activate_rubric():
    middleware = ContentRubricActivator()
    state = {"messages": [AIMessage(content="今天先聊聊选题思路。")]}

    assert middleware.after_agent(state, runtime=None) is None


def test_structured_content_activates_from_message_blocks():
    middleware = ContentRubricActivator()
    state = {
        "messages": [
            AIMessage(content=[{"type": "text", "text": "```xhs_copy\n{}\n```"}])
        ]
    }

    assert middleware.after_agent(state, runtime=None) == {
        "rubric": DEFAULT_CONTENT_RUBRIC
    }


def test_caller_rubric_is_preserved():
    middleware = ContentRubricActivator()
    state = {
        "rubric": "调用方自定义标准",
        "messages": [AIMessage(content="```xhs_copy\n{}\n```")],
    }

    assert middleware.after_agent(state, runtime=None) is None
    assert state["rubric"] == "调用方自定义标准"


def test_only_final_ai_response_can_activate_rubric():
    """非最终轮的结构化交付物不应激活:只看最后一条 AI 消息。"""
    middleware = ContentRubricActivator()
    state = {
        "messages": [
            AIMessage(content="```xhs_copy\n{}\n```"),
            AIMessage(content="这是最终的普通回复。"),
        ]
    }

    assert middleware.after_agent(state, runtime=None) is None


def test_activator_handoff_causes_real_rubric_evaluation():
    activator = ContentRubricActivator()
    rubric = RubricMiddleware(model="openai:test-model", max_iterations=1)

    # 桩 grader 返回普通 dict —— 框架 _extract_graded 的官方前向兼容路径会
    # 自行 GraderResponse.model_validate(),故测试无需 import 私有的 GraderResponse。
    class _Grader:
        def invoke(self, _input):
            return {
                "structured_response": {
                    "result": "satisfied",
                    "explanation": "依据完整",
                    "criteria": [],
                }
            }

    rubric._grader = _Grader()
    state = {"messages": [AIMessage(content="```xhs_copy\n{}\n```")]}
    state.update(activator.after_agent(state, runtime=None) or {})

    result = rubric.after_agent(state, runtime=None)

    assert result is not None
    assert result["_rubric_status"] == "satisfied"
    assert result["_rubric_iterations"] == 1
