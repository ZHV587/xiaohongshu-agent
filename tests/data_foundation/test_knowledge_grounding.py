from types import SimpleNamespace

from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from data_foundation.knowledge_grounding import KnowledgeGroundingMiddleware


def _runtime():
    return SimpleNamespace(context=None, stream_writer=None, store=None)


def _result():
    return {
        "retrieval_mode": "keyword_only",
        "evidence": [
            {
                "resource_id": "11111111-1111-4111-8111-111111111111",
                "resource_version": 2,
                "type": "xhs_note",
                "asset_kind": "copy",
                "source_kind": "adopted",
                "niche": "露营",
                "title": "轻量露营清单",
                "summary": "三件核心装备",
                "source_updated_at": "未知",
                "indexed_at": "2026-07-15T00:00:00+00:00",
                "score": 0.8,
                "relevance": 0.7,
                "freshness": 1.0,
                "quality": 0.8,
                "performance": 0.4,
                "retrieval_sources": ["keyword"],
                "why_selected": "关键词与效果命中",
            }
        ],
        "engines_used": ["keyword"],
        "degraded_engines": [],
        "gaps": None,
    }


def test_middleware_automatically_retrieves_latest_human_request_and_binds_turn():
    calls = []

    def retrieve(query, limit, config):
        calls.append((query, limit, config))
        return _result()

    middleware = KnowledgeGroundingMiddleware(retriever=retrieve)
    update = middleware.before_agent(
        {
            "messages": [
                HumanMessage(content="先聊别的"),
                {"role": "assistant", "content": "好的"},
                HumanMessage(content="写一篇轻量露营文案"),
            ]
        },
        _runtime(),
        {"configurable": {"turn_id": "turn-1"}},
    )

    assert calls[0][0] == "写一篇轻量露营文案"
    assert update["latest_user_request"] == "写一篇轻量露营文案"
    assert update["knowledge_grounding"]["status"] == "ready"
    assert update["knowledge_grounding"]["turn_id"] == "turn-1"
    assert update["knowledge_grounding"]["evidence"][0]["resource_version"] == 2


def test_middleware_injects_authoritative_grounding_into_model_prompt():
    middleware = KnowledgeGroundingMiddleware(retriever=lambda *_args: _result())
    grounding = {
        "status": "ready",
        "query": "露营",
        "turn_id": "turn-1",
        **_result(),
    }
    request = ModelRequest(
        model=object(),
        messages=[],
        system_message=SystemMessage(content="平台规则"),
        tools=[],
        state={"knowledge_grounding": grounding},
        runtime=_runtime(),
    )
    captured = {}

    middleware.wrap_model_call(
        request,
        lambda modified: captured.setdefault("request", modified),
    )

    prompt = str(captured["request"].system_message.content)
    assert "<automatic_knowledge_grounding>" in prompt
    assert "轻量露营清单" in prompt
    assert "11111111-1111-4111-8111-111111111111" in prompt


def test_middleware_fails_closed_without_a_user_query():
    middleware = KnowledgeGroundingMiddleware(
        retriever=lambda *_args: (_ for _ in ()).throw(AssertionError("must not call"))
    )
    update = middleware.before_agent({"messages": []}, _runtime(), {})
    assert update["knowledge_grounding"]["status"] == "error"
    assert update["knowledge_grounding"]["error"] == "MISSING_USER_QUERY"


def test_revision_grounding_keeps_latest_feedback_but_retrieves_with_recent_topic():
    calls = []

    def retrieve(query, limit, config):
        calls.append(query)
        return _result()

    update = KnowledgeGroundingMiddleware(retriever=retrieve).before_agent(
        {
            "messages": [
                HumanMessage(content="写一篇轻量露营装备清单，面向第一次露营的人"),
                {"role": "assistant", "content": "这是上一版"},
                HumanMessage(content="把这个再改短一点"),
            ]
        },
        _runtime(),
        {"configurable": {"turn_id": "turn-revision"}},
    )

    assert "轻量露营装备清单" in calls[0]
    assert calls[0].endswith("当前修改要求：把这个再改短一点")
    assert update["latest_user_request"] == "把这个再改短一点"
