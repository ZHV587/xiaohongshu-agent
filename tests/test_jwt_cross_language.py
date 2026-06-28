"""JWT 跨语言契约:前端 web/src/lib/server/jwt.ts 与后端 auth.py 必须对同一 HS256 token
口径一致(同 base64url 编码、同 HMAC-SHA256 签名输入、同 alg 限制、同过期判定)。

生产真实数据流:web BFF 在飞书 OAuth 回调用 signJwt 签发 → 写 httpOnly cookie →
后端 LangGraph auth.py 的 _verify_jwt 验签(同时 web authz.ts 的 verifyJwt 也验)。
两份手写实现独立演进,任一侧改算法/字段/编码都可能静默破坏登录。本测试用 node 直接跑
真实 jwt.ts,与 auth.py 交叉验签,把"前签后验"钉成回归用例,防单侧漂移。

无 node(或 node 太旧不支持直接跑 .ts)时整组 skip,不阻断纯 Python 环境。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

import auth

_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
_DRIVER = _WEB_DIR / "scripts" / "jwt-contract.mjs"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _reference_hs256(secret: str, payload: dict) -> str:
    """测试参考实现:与 jwt.ts/auth.py 同口径的 HS256 签名,仅用于驱动 node 的 verifyJwt。"""
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(sig)}"


def _run_driver(*args: str) -> str:
    result = subprocess.run(
        # --experimental-strip-types 让 node 22.6+ 也能直接 import .ts(23.6+ 默认开启,
        # 显式传保持向后兼容);node < 22.6 不识别该 flag → 非 0 退出 → fixture 优雅 skip。
        ["node", "--experimental-strip-types", str(_DRIVER), *args],
        cwd=str(_WEB_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"node driver failed: {result.stderr or result.stdout}")
    return result.stdout


@pytest.fixture(scope="module")
def node_driver():
    if shutil.which("node") is None:
        pytest.skip("node 不可用,跳过 JWT 跨语言契约测试")
    if not _DRIVER.exists():
        pytest.skip(f"缺少 node 驱动:{_DRIVER}")
    try:
        token = _run_driver("sign", "smoke-secret", "ou_smoke")
    except Exception as exc:  # noqa: BLE001 - node 太旧/不支持 .ts 类型擦除时优雅跳过
        pytest.skip(f"node 无法直接运行 jwt.ts(可能版本过旧):{exc}")
    if not token or token.count(".") != 2:
        pytest.skip("node 驱动未产出合法 JWT,跳过")
    return _run_driver


# --- 方向一:TS 签发 → Python 验签(生产真实路径)---

def test_ts_signed_token_verified_by_python(node_driver, monkeypatch):
    secret = "contract-secret-α-中文-混合"
    monkeypatch.setattr(auth, "_JWT_SECRET", secret)

    token = node_driver("sign", secret, "ou_alice", "Alice")
    payload = auth._verify_jwt(token)

    assert payload is not None
    assert payload["sub"] == "ou_alice"
    assert payload["name"] == "Alice"
    assert payload["exp"] > time.time()


def test_python_rejects_ts_token_with_wrong_secret(node_driver, monkeypatch):
    token = node_driver("sign", "the-real-secret", "ou_alice", "Alice")
    monkeypatch.setattr(auth, "_JWT_SECRET", "a-different-secret")
    assert auth._verify_jwt(token) is None


def test_python_rejects_ts_expired_token(node_driver, monkeypatch):
    secret = "contract-secret"
    monkeypatch.setattr(auth, "_JWT_SECRET", secret)
    # ttl 取负 → exp 落在过去
    token = node_driver("sign", secret, "ou_bob", "", "-120")
    assert auth._verify_jwt(token) is None


# --- 方向二:参考 HS256 → TS 验签(确保 node verifyJwt 接受标准 HS256 并拒错密钥/过期)---

def test_ts_verifies_reference_hs256(node_driver):
    secret = "contract-secret-β"
    now = int(time.time())
    token = _reference_hs256(secret, {"sub": "ou_carol", "name": "Carol", "iat": now, "exp": now + 3600})

    payload = json.loads(node_driver("verify", secret, token))
    assert payload is not None
    assert payload["sub"] == "ou_carol"
    assert payload["name"] == "Carol"


def test_ts_rejects_reference_token_with_wrong_secret(node_driver):
    now = int(time.time())
    token = _reference_hs256("real", {"sub": "ou_carol", "iat": now, "exp": now + 3600})
    assert json.loads(node_driver("verify", "wrong", token)) is None


def test_ts_rejects_reference_expired_token(node_driver):
    secret = "contract-secret"
    now = int(time.time())
    token = _reference_hs256(secret, {"sub": "ou_dave", "iat": now - 7200, "exp": now - 3600})
    assert json.loads(node_driver("verify", secret, token)) is None


# --- alg 混淆防护:两侧都必须拒绝 alg != HS256(防 alg=none 攻击)---

def test_both_sides_reject_alg_none(node_driver, monkeypatch):
    secret = "contract-secret"
    now = int(time.time())
    header = {"alg": "none", "typ": "JWT"}
    payload = {"sub": "ou_evil", "iat": now, "exp": now + 3600}
    forged = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
        + "."  # 空签名
    )
    # Python 侧
    monkeypatch.setattr(auth, "_JWT_SECRET", secret)
    assert auth._verify_jwt(forged) is None
    # TS 侧
    assert json.loads(node_driver("verify", secret, forged)) is None
