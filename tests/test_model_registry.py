import pytest

from langchain_core.language_models.fake_chat_models import FakeListChatModel

from model_registry import ModelRegistry
from models import ModelCandidate, ModelRouterMiddleware


def _candidate(version: str, model_id: str) -> ModelCandidate:
    return ModelCandidate(
        gateway_name=f"gateway-{version}",
        model_id=model_id,
        model=FakeListChatModel(responses=[f"{version}:{model_id}"]),
    )


def test_registry_reload_replaces_active_pool():
    registry = ModelRegistry()
    registry.replace(version="v1", pool=[_candidate("v1", "gpt-4o")])
    assert registry.status()["version"] == "v1"
    assert registry.status()["active_models"] == ["gpt-4o"]

    registry.replace(version="v2", pool=[_candidate("v2", "claude-sonnet-4-6")])
    assert registry.status()["version"] == "v2"
    assert registry.get_pool()[0].model_id == "claude-sonnet-4-6"


def test_router_reads_registry_on_each_sync_call():
    registry = ModelRegistry()
    registry.replace(version="v1", pool=[_candidate("v1", "gpt-4o")])
    middleware = ModelRouterMiddleware(registry)
    seen = []

    class Request:
        def override(self, model):
            seen.append(model)
            return self

    def handler(request):
        return "ok"

    assert middleware.wrap_model_call(Request(), handler) == "ok"
    registry.replace(version="v2", pool=[_candidate("v2", "claude-sonnet-4-6")])
    assert middleware.wrap_model_call(Request(), handler) == "ok"

    assert seen[0] is not seen[1]


@pytest.mark.asyncio
async def test_router_reads_registry_on_each_async_call():
    registry = ModelRegistry()
    registry.replace(version="v1", pool=[_candidate("v1", "gpt-4o")])
    middleware = ModelRouterMiddleware(registry)
    seen = []

    class Request:
        def override(self, model):
            seen.append(model)
            return self

    async def handler(request):
        return "ok"

    assert await middleware.awrap_model_call(Request(), handler) == "ok"
    registry.replace(version="v2", pool=[_candidate("v2", "claude-sonnet-4-6")])
    assert await middleware.awrap_model_call(Request(), handler) == "ok"

    assert seen[0] is not seen[1]
