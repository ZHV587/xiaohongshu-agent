from __future__ import annotations

from cryptography.fernet import Fernet
from starlette.testclient import TestClient


def _client(monkeypatch, *, secret: str = "internal-secret", admins: str = "ou_admin"):
    monkeypatch.setenv("XHS_INTERNAL_SECRET", secret)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", admins)
    import data_foundation.http_app as http_app

    return TestClient(http_app.app)


def test_internal_ok_rejects_missing_key(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/internal/ok")

    assert response.status_code == 401
    assert response.json()["error"] == "Unauthorized internal request"


def test_internal_ok_accepts_internal_key(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/internal/ok", headers={"X-XHS-Internal-Key": "internal-secret"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_admin_route_rejects_non_admin_even_if_header_claims_admin(monkeypatch):
    client = _client(monkeypatch, admins="ou_real_admin")

    response = client.get(
        "/internal/config",
        headers={
            "X-XHS-Internal-Key": "internal-secret",
            "X-XHS-Open-Id": "ou_normal",
            "X-XHS-Is-Admin": "true",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"] == "Forbidden"


def _admin_headers(secret: str = "internal-secret", open_id: str = "ou_admin") -> dict[str, str]:
    return {
        "X-XHS-Internal-Key": secret,
        "X-XHS-Open-Id": open_id,
        "X-XHS-Is-Admin": "true",
    }


def test_internal_config_round_trip_returns_plain_admin_values(monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    config_path = tmp_path / "config-center.enc"
    monkeypatch.setenv("XHS_CONFIG_ENCRYPTION_KEY", key)
    monkeypatch.setenv("XHS_CONFIG_CENTER_PATH", str(config_path))
    client = _client(monkeypatch)

    save_response = client.post(
        "/internal/config",
        headers=_admin_headers(),
        json={"configs": {"LLM_API_KEY": "sk-secret", "LLM_PROVIDER": "openai"}},
    )
    assert save_response.status_code == 200
    save_payload = save_response.json()
    assert save_payload["ok"] is True
    assert save_payload["changed_keys"] == ["LLM_API_KEY", "LLM_PROVIDER"]
    assert save_payload["version"]

    read_response = client.get("/internal/config", headers=_admin_headers())
    assert read_response.status_code == 200
    read_payload = read_response.json()
    assert read_payload["ok"] is True
    assert read_payload["configs"]["LLM_API_KEY"] == "sk-secret"
    assert read_payload["configs"]["LLM_PROVIDER"] == "openai"
    assert read_payload["version"] == save_payload["version"]


def test_internal_config_rejects_deploy_only_internal_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("XHS_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("XHS_CONFIG_CENTER_PATH", str(tmp_path / "config-center.enc"))
    client = _client(monkeypatch)

    response = client.post(
        "/internal/config",
        headers=_admin_headers(),
        json={"configs": {"XHS_INTERNAL_BASE_URL": "http://127.0.0.1:2024"}},
    )

    assert response.status_code == 400
    assert "not editable" in response.json()["error"]


def test_internal_config_missing_config_center_env_returns_500(monkeypatch):
    monkeypatch.delenv("XHS_CONFIG_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("XHS_CONFIG_CENTER_PATH", raising=False)
    client = _client(monkeypatch)

    response = client.get("/internal/config", headers=_admin_headers())

    assert response.status_code == 500
    assert "Config center missing required environment" in response.json()["error"]


def test_internal_uat_status_uses_current_open_id(monkeypatch):
    client = _client(monkeypatch)

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(internal_api, "get_uat", lambda open_id: "token" if open_id == "ou_user" else None)

    response = client.get(
        "/internal/feishu/status",
        headers={
            "X-XHS-Internal-Key": "internal-secret",
            "X-XHS-Open-Id": "ou_user",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "authorized": True}


def test_internal_uat_save_requires_user_identity(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/internal/feishu/uat",
        headers={"X-XHS-Internal-Key": "internal-secret"},
        json={"uat": "token", "refresh_token": "", "expires_at": 123, "scopes": [], "name": "User"},
    )

    assert response.status_code == 401
    assert response.json()["error"] == "Missing internal user"


def test_internal_chats_filters_group_chats(monkeypatch):
    client = _client(monkeypatch)

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(internal_api, "get_uat", lambda open_id: "token")
    monkeypatch.setattr(internal_api, "identity_config", lambda open_id: {"user": open_id})
    monkeypatch.setattr(
        internal_api,
        "lark_cli",
        lambda command, config=None: '{"data":{"chats":[{"chat_mode":"group","chat_id":"oc_1","name":"群"},{"chat_mode":"p2p","chat_id":"ou_1","name":"人"}]}}',
    )

    response = client.get(
        "/internal/feishu/chats",
        headers={"X-XHS-Internal-Key": "internal-secret", "X-XHS-Open-Id": "ou_user"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "chats": [{"chat_id": "oc_1", "name": "群"}]}


def test_internal_wiki_space_falls_back_without_uat(monkeypatch):
    monkeypatch.setenv("FEISHU_WIKI_SPACE_ID", "space_1")
    client = _client(monkeypatch)

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(internal_api, "get_uat", lambda open_id: None)

    response = client.get(
        "/internal/feishu/wiki-space",
        headers={"X-XHS-Internal-Key": "internal-secret", "X-XHS-Open-Id": "ou_user"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "name": "小红书爆单手册", "space_id": "space_1"}


def test_internal_health_facts_is_admin_only(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    response = client.get(
        "/internal/health/facts",
        headers={"X-XHS-Internal-Key": "internal-secret", "X-XHS-Open-Id": "ou_user"},
    )

    assert response.status_code == 403


def test_internal_health_facts_returns_safe_shape(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(
        internal_api,
        "runtime_facts_payload",
        lambda: {
            "ok": True,
            "scheduler": {"enabled": False},
            "outbox": {"pending": 0, "blocked": 0, "dead": 0},
            "embedding": {"active": None, "building": None},
            "sync": {"running": False},
            "errors": [],
        },
    )

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["scheduler"] == {"enabled": False}
    assert set(payload) == {"ok", "scheduler", "outbox", "embedding", "sync", "errors"}
    assert "credentials" not in response.text


def test_runtime_facts_payload_uses_sync_enabled_env(monkeypatch):
    import data_foundation.internal_api as internal_api

    monkeypatch.setenv("XHS_SYNC_ENABLED", "true")
    enabled_payload = internal_api.runtime_facts_payload()

    monkeypatch.setenv("XHS_SYNC_ENABLED", "false")
    disabled_payload = internal_api.runtime_facts_payload()

    assert enabled_payload["scheduler"]["enabled"] is True
    assert disabled_payload["scheduler"]["enabled"] is False
