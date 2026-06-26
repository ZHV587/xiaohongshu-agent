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


class _FakeUser:
    def __init__(self, identity):
        self.identity = identity


class _FakeCtx:
    def __init__(self, identity):
        self.user = _FakeUser(identity)


@pytest.mark.anyio
async def test_on_store_rewrites_user_memory_namespace_to_self(monkeypatch):
    """安全回归:客户端指定他人 user-memories namespace,必须被改写为当前用户 ——
    否则经 BFF 直调 /store/* 可越权读写他人私有记忆。"""
    ctx = _FakeCtx("ou_alice")
    # 攻击者把 namespace 指向受害者私有分区
    value = {"namespace": ("ou_victim", "user-memories"), "key": "AGENTS.md"}
    await auth_mod.on_store(ctx, value)
    assert value["namespace"] == ("ou_alice", "user-memories")
    assert "ou_victim" not in value["namespace"]


@pytest.mark.anyio
async def test_on_store_normalizes_tampered_user_memory_namespace(monkeypatch):
    """颠倒顺序/加额外段也一律规范化为当前用户两段。"""
    ctx = _FakeCtx("ou_alice")
    value = {"namespace": ("user-memories", "ou_victim", "extra")}
    await auth_mod.on_store(ctx, value)
    assert value["namespace"] == ("ou_alice", "user-memories")


@pytest.mark.anyio
async def test_on_store_leaves_shared_namespace_untouched(monkeypatch):
    """团队共享 namespace(/shared → ("xhs-shared",))不受影响,保持共享。"""
    ctx = _FakeCtx("ou_alice")
    value = {"namespace": ("xhs-shared",), "key": "xhs-style.md"}
    await auth_mod.on_store(ctx, value)
    assert value["namespace"] == ("xhs-shared",)


@pytest.mark.anyio
async def test_on_store_leaves_team_memory_namespace_untouched(monkeypatch):
    """团队记忆 namespace(("xhs-team-memory",) 及其子空间)放行,保持全员共享。"""
    ctx = _FakeCtx("ou_alice")
    value = {"namespace": ("xhs-team-memory",), "key": "AGENTS.md"}
    await auth_mod.on_store(ctx, value)
    assert value["namespace"] == ("xhs-team-memory",)
    sub = {"namespace": ("xhs-team-memory", "team")}
    await auth_mod.on_store(ctx, sub)
    assert sub["namespace"] == ("xhs-team-memory", "team")


@pytest.mark.anyio
async def test_on_store_scopes_ancestor_prefix_to_self(monkeypatch):
    """P0 安全回归:按受害者**裸 open_id 祖先前缀** search/list 必须被收窄到自己。

    旧实现只在 namespace 字面含 "user-memories" 时改写,裸前缀 ("ou_victim",) 不含 marker
    → 放行 → LangGraph 前缀匹配命中 ("ou_victim","user-memories") 整棵子树,泄露他人私有记忆。
    """
    ctx = _FakeCtx("ou_alice")
    value = {"namespace": ("ou_victim",)}
    await auth_mod.on_store(ctx, value)
    assert value["namespace"] == ("ou_alice", "user-memories")
    assert "ou_victim" not in value["namespace"]


@pytest.mark.anyio
async def test_on_store_scopes_none_prefix_to_self(monkeypatch):
    """P0 安全回归:ListNamespaces 的 None 全量前缀必须被收窄到自己,杜绝枚举全员分区。"""
    ctx = _FakeCtx("ou_alice")
    value = {"namespace": None}
    await auth_mod.on_store(ctx, value)
    assert value["namespace"] == ("ou_alice", "user-memories")
