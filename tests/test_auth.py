import os
import time
import base64
import json
import hmac
import hashlib
import pytest

import auth as auth_mod


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _make_jwt(sub: str, name: str, secret: str, expired: bool = False) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    exp_time = int(time.time()) - 3600 if expired else int(time.time()) + 3600
    payload = _b64url(json.dumps({"sub": sub, "name": name, "exp": exp_time}).encode())
    sig = _b64url(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


@pytest.mark.anyio
async def test_auth_no_secret_mock_allowed(monkeypatch):
    monkeypatch.setattr(auth_mod, "_JWT_SECRET", "")
    monkeypatch.setenv("XHS_DEV_FALLBACK_USER", "fallback_bob")

    # mock token is allowed
    res = await auth_mod.authenticate({"authorization": "Bearer mock-user-alice"})
    assert res["identity"] == "alice"
    assert res["display_name"] == "alice"

    # fallback works when token is missing
    res2 = await auth_mod.authenticate({})
    assert res2["identity"] == "fallback_bob"


@pytest.mark.anyio
async def test_auth_with_secret_mock_rejected(monkeypatch):
    monkeypatch.setattr(auth_mod, "_JWT_SECRET", "my-super-secret")

    # mock token should be rejected
    with pytest.raises(Exception):
        await auth_mod.authenticate({"authorization": "Bearer mock-user-alice"})


@pytest.mark.anyio
async def test_auth_with_secret_valid_jwt(monkeypatch):
    secret = "my-super-secret"
    monkeypatch.setattr(auth_mod, "_JWT_SECRET", secret)

    token = _make_jwt("ou_alice_001", "Alice", secret)
    res = await auth_mod.authenticate({"authorization": f"Bearer {token}"})
    assert res["identity"] == "ou_alice_001"
    assert res["display_name"] == "Alice"


@pytest.mark.anyio
async def test_auth_with_secret_expired_jwt(monkeypatch):
    secret = "my-super-secret"
    monkeypatch.setattr(auth_mod, "_JWT_SECRET", secret)

    token = _make_jwt("ou_alice_001", "Alice", secret, expired=True)
    with pytest.raises(Exception):
        await auth_mod.authenticate({"authorization": f"Bearer {token}"})
