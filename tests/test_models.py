import httpx
from middlewares import is_retryable_error


class FakeStatusError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


def test_is_retryable_error_on_503():
    assert is_retryable_error(FakeStatusError(503)) is True


def test_is_retryable_error_on_429():
    assert is_retryable_error(FakeStatusError(429)) is True


def test_is_retryable_error_on_400_is_false():
    assert is_retryable_error(FakeStatusError(400)) is False


def test_is_retryable_error_on_httpx_transport():
    assert is_retryable_error(httpx.ConnectError("boom")) is True


def test_is_retryable_error_on_value_error_is_false():
    assert is_retryable_error(ValueError("nope")) is False


from models import ModelCandidate


def test_model_candidate_holds_fields():
    sentinel = object()  # 占位模型实例
    c = ModelCandidate(gateway_name="g1", model_id="claude-sonnet-4-6", model=sentinel)
    assert c.gateway_name == "g1"
    assert c.model_id == "claude-sonnet-4-6"
    assert c.model is sentinel


import models as models_mod


def _fake_models_response():
    return {"data": [{"id": "claude-sonnet-4-6"}, {"id": "gpt-4o"}]}


def test_discover_models_parses_ids(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()

    class FakeResp:
        status_code = 200
        def json(self): return _fake_models_response()
        def raise_for_status(self): pass

    def fake_get(url, headers=None, timeout=None):
        return FakeResp()

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    ids = models_mod.discover_models("https://gw/v1", "key")
    assert ids == ["claude-sonnet-4-6", "gpt-4o"]


def test_discover_models_non_200_returns_none(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()

    def fake_get(url, headers=None, timeout=None):
        raise httpx.HTTPStatusError("500", request=None, response=None)

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    assert models_mod.discover_models("https://gw/v1", "key") is None


def test_discover_models_timeout_returns_none(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()

    def fake_get(url, headers=None, timeout=None):
        raise httpx.TimeoutException("slow")

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    assert models_mod.discover_models("https://gw/v1", "key") is None


def test_discover_models_cached(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    calls = {"n": 0}

    class FakeResp:
        status_code = 200
        def json(self): return _fake_models_response()
        def raise_for_status(self): pass

    def fake_get(url, headers=None, timeout=None):
        calls["n"] += 1
        return FakeResp()

    monkeypatch.setattr(models_mod.httpx, "get", fake_get)
    monkeypatch.delenv("DISCOVER_MODELS", raising=False)
    models_mod.discover_models("https://gw/v1", "key")
    models_mod.discover_models("https://gw/v1", "key")
    assert calls["n"] == 1


def test_discover_models_disabled_returns_none(monkeypatch):
    models_mod._DISCOVER_CACHE.clear()
    monkeypatch.setenv("DISCOVER_MODELS", "false")
    assert models_mod.discover_models("https://gw/v1", "key") is None
