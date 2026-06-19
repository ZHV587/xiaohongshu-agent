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


def test_registry_reload_from_config_snapshot(monkeypatch):
    import models as models_mod
    from config_center import ConfigSnapshot

    def fake_discover(base_url, api_key):
        assert base_url == "https://gateway.example/v1"
        assert api_key == "sk-secret"
        return ["gpt-4o"]

    monkeypatch.setattr(models_mod, "discover_models", fake_discover)
    monkeypatch.setattr(
        models_mod,
        "_build_chat_model",
        lambda model_id, base_url, api_key: FakeListChatModel(responses=[model_id]),
    )

    registry = ModelRegistry()
    snapshot = ConfigSnapshot(
        version="v-center",
        values={
            "LLM_PROVIDER": "openai",
            "LLM_BASE_URL": "https://gateway.example/v1",
            "LLM_API_KEY": "sk-secret",
            "LLM_QUALITY_MODELS": "gpt-4o",
        },
        actor_open_id="ou_admin",
        changed_keys=["LLM_QUALITY_MODELS"],
        created_at=1.0,
    )

    registry.reload_from_config(snapshot)

    assert registry.status()["version"] == "v-center"
    assert registry.status()["active_models"] == ["gpt-4o"]
