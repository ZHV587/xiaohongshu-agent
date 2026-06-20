from __future__ import annotations

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
