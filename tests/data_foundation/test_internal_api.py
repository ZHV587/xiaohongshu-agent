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
