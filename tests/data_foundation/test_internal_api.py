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


def test_admin_claim_mismatch_rejects_admin_claimed_as_non_admin(monkeypatch, caplog):
    client = _client(monkeypatch, admins="ou_real_admin")

    response = client.get(
        "/internal/config",
        headers={
            "X-XHS-Internal-Key": "internal-secret",
            "X-XHS-Open-Id": "ou_real_admin",
            "X-XHS-Is-Admin": "false",
        },
    )

    assert response.status_code == 403
    assert "internal_admin_claim_mismatch" in caplog.text
    assert "ou_real_admin" not in caplog.text


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


def test_internal_data_foundation_status_is_admin_only(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    response = client.get(
        "/internal/data-foundation/status",
        headers={
            "X-XHS-Internal-Key": "internal-secret",
            "X-XHS-Open-Id": "ou_user",
            "X-XHS-Is-Admin": "false",
        },
    )

    assert response.status_code == 403


def test_internal_data_foundation_status_returns_repository_summary(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")
    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(
        internal_api,
        "data_foundation_status_payload",
        lambda: {
            "tenant_id": "default",
            "resources": {"total": 2, "by_type": {"document": 2}},
            "sync": {"running": False},
            "outbox": {"pending": 0},
        },
    )

    response = client.get("/internal/data-foundation/status", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json()["status"]["resources"]["total"] == 2
    assert "credentials" not in response.text


def test_internal_data_foundation_status_error_does_not_log_exception_details(monkeypatch, caplog):
    client = _client(monkeypatch, admins="ou_admin")
    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(
        internal_api,
        "data_foundation_status_payload",
        lambda: (_ for _ in ()).throw(RuntimeError("postgresql://user:db-secret@example/db")),
    )

    response = client.get("/internal/data-foundation/status", headers=_admin_headers())

    assert response.status_code == 503
    assert "db-secret" not in caplog.text


def test_internal_health_facts_returns_safe_shape(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(
        internal_api,
        "database_runtime_fact",
        lambda observed_at: {
            "status": "healthy",
            "source": "database",
            "observed_at": observed_at,
            "stale_after_seconds": 30,
            "data": {
                "outbox": {"pending": 0, "blocked": 0, "dead": 0},
                "embedding": {"active": None, "building": None},
                "errors": [],
            },
        },
    )

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"ok", "observed_at", "modules"}
    assert set(payload["modules"]) == {"startup", "scheduler", "database"}
    assert payload["modules"]["database"]["data"]["outbox"]["dead"] == 0
    assert "credentials" not in response.text


def test_internal_health_facts_combines_instance_and_database_modules(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(
        internal_api,
        "database_runtime_fact",
        lambda observed_at: {
            "status": "healthy",
            "source": "database",
            "observed_at": observed_at,
            "stale_after_seconds": 30,
            "data": {"outbox": {"dead": 1}},
        },
    )

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["modules"]["startup"]["source"] == "process"
    assert payload["modules"]["scheduler"]["source"] == "instance"
    assert payload["modules"]["database"]["data"]["outbox"]["dead"] == 1


def test_internal_health_facts_reads_runtime_state_from_application(monkeypatch):
    import data_foundation.http_app as http_app
    import data_foundation.internal_api as internal_api

    class FakeSupervisor:
        enabled = True
        interval_seconds = 30
        instance_id = "instance-from-app"
        accepting_work = True
        last_cycle_started_at = "2026-06-21T00:00:00+00:00"
        last_cycle_finished_at = "2026-06-21T00:00:01+00:00"
        last_cycle_status = "succeeded"
        last_cycle_error_code = None

        async def start(self):
            return None

        async def stop(self, *, grace_seconds):
            return None

    monkeypatch.setattr(http_app, "_resolve_model_registry", lambda: object())
    monkeypatch.setattr(http_app, "build_supervisor", lambda *, model_registry=None: FakeSupervisor())
    monkeypatch.setattr(
        internal_api,
        "database_runtime_fact",
        lambda observed_at: {
            "status": "healthy",
            "source": "database",
            "observed_at": observed_at,
            "stale_after_seconds": 30,
            "data": {},
        },
    )

    with _client(monkeypatch, admins="ou_admin") as client:
        response = client.get("/internal/health/facts", headers=_admin_headers())

    payload = response.json()
    assert payload["modules"]["startup"]["status"] == "running"
    assert payload["modules"]["scheduler"]["data"]["instance_id"] == "instance-from-app"


def test_internal_health_facts_keeps_partial_result_when_database_fails(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    import data_foundation.internal_api as internal_api

    monkeypatch.setattr(
        internal_api,
        "database_runtime_fact",
        lambda observed_at: (_ for _ in ()).throw(RuntimeError("postgresql://user:db-secret@example/db")),
    )

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["modules"]["database"]["status"] == "unavailable"
    assert payload["modules"]["database"]["error"]["code"] == "RUNTIME_FACTS_DATABASE_UNAVAILABLE"
    assert "db-secret" not in response.text


def test_internal_health_facts_security_regression_redacts_secret_markers(monkeypatch, caplog):
    client = _client(monkeypatch, admins="ou_admin")

    import data_foundation.internal_api as internal_api

    secret_markers = [
        "sk-runtime-secret",
        "postgresql://user:db-secret@host/db",
        "Authorization: Bearer token",
    ]
    monkeypatch.setattr(
        internal_api,
        "database_runtime_fact",
        lambda observed_at: (_ for _ in ()).throw(RuntimeError(" ".join(secret_markers))),
    )

    response = client.get("/internal/health/facts", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["modules"]["database"]["status"] == "unavailable"
    rendered = response.text + caplog.text
    for marker in secret_markers:
        assert marker not in rendered


def test_internal_health_facts_rejects_non_admin_user(monkeypatch):
    client = _client(monkeypatch, admins="ou_admin")

    response = client.get(
        "/internal/health/facts",
        headers=_admin_headers(open_id="ou_user"),
    )

    assert response.status_code == 403
