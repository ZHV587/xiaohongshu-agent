"""LangGraph 自定义鉴权(1b-3 多用户隔离 + 真飞书 OAuth)。

身份来源(按优先级):
  1) 真飞书 OAuth:前端 Next.js 在飞书登录回调里用飞书 open_id 签发 HS256 JWT,
     经 Authorization: Bearer <jwt> 传入。本模块用共享密钥 XHS_JWT_SECRET 验签,
     取 payload.sub(飞书 open_id)作身份,payload.name 作显示名。
  2) 本地 mock(仅当未配置 JWT 密钥时):token 形如 "mock-user-A" 直接当身份,
     方便单机/脚本调试(verify_1b3.py 等)。
  3) 兜底用户:未带 token 时用 XHS_DEV_FALLBACK_USER。上云务必置空 → 无 token 返 401。

隔离模型(对应设计):
  - thread(会话)/ 其 /drafts → 按 user 隔离:owner metadata + search/read filter
  - /shared(风格)/ /skills(爆款方法论)→ 全员共享:store 不按 user 过滤
"""
import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langgraph_sdk import Auth

# auth 作为鉴权中间件被 langgraph 用 importlib 独立加载,其加载时机/工作目录
# 与主进程不同 —— 无参 load_dotenv() 可能找不到 .env,导致密钥读空而静默退回
# mock 模式。故用 __file__ 显式推导 .env 路径(对齐项目历史教训:路径用 __file__)。
load_dotenv(Path(__file__).resolve().parent / ".env")

auth = Auth()

# 与前端 Next.js 共享的 JWT 签名密钥。配置后启用真飞书 OAuth 身份校验
_JWT_SECRET = os.environ.get("XHS_JWT_SECRET", "")


def _b64url_decode(seg: str) -> bytes:
    """解码 JWT 的 base64url 段(补足 padding)。"""
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def _verify_jwt(token: str) -> dict | None:
    """验证 HS256 JWT 签名与过期时间,通过则返回 payload,否则 None。

    只接受 alg=HS256(防 alg=none / 算法混淆攻击)。
    """
    try:
        header_seg, payload_seg, sig_seg = token.split(".")
    except ValueError:
        return None

    try:
        header = json.loads(_b64url_decode(header_seg))
    except (ValueError, json.JSONDecodeError):
        return None
    if header.get("alg") != "HS256":
        return None

    try:
        jwt_key = _JWT_SECRET.encode()
    except Exception:
        return None

    expected = hmac.new(
        jwt_key,
        f"{header_seg}.{payload_seg}".encode(),
        hashlib.sha256,
    ).digest()
    try:
        actual = _b64url_decode(sig_seg)
    except (ValueError, Exception):
        return None
    if not hmac.compare_digest(expected, actual):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_seg))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = payload.get("exp")
    if exp is not None and time.time() > exp:
        return None  # 已过期
    return payload


def _strip_bearer(raw: str | None) -> str | None:
    """剥掉 Authorization 头里的 "Bearer " 前缀,取出裸 token。"""
    if not raw:
        return None
    raw = raw.strip()
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip()
    return raw or None


def _resolve_identity(raw: str | None) -> tuple[str | None, str | None]:
    """从 Authorization 头解析 (identity, display_name)。"""
    token = _strip_bearer(raw)

    # 优先检查 JWT 秘钥是否配置
    if _JWT_SECRET:
        # JWT 模式: 必须是合法 JWT，拒绝 mock tokens
        if not token:
            return None, None
        payload = _verify_jwt(token)
        if not payload:
            return None, None
        sub = payload.get("sub")
        if not sub:
            return None, None
        return sub, payload.get("name") or sub
    else:
        # Mock/开发模式: 未配置 XHS_JWT_SECRET
        if token and token.startswith("mock-user-"):
            ident = token[len("mock-user-"):]
            return ident, ident

        # 兜底用户
        fallback = os.environ.get("XHS_DEV_FALLBACK_USER", "").strip()
        if fallback:
            return fallback, fallback

        return None, None



@auth.authenticate
async def authenticate(headers: dict) -> dict:
    """从请求头解析身份。返回的 dict 至少含 identity。

    headers 的 key 可能是 bytes(starlette),统一按小写 str 处理。
    """
    raw = None
    for k, v in headers.items():
        key = k.decode() if isinstance(k, bytes) else k
        if key.lower() == "authorization":
            raw = v.decode() if isinstance(v, bytes) else v
            break

    identity, display_name = _resolve_identity(raw)
    if not identity:
        raise Auth.exceptions.HTTPException(status_code=401, detail="缺少身份令牌(Authorization)或签名无效")
    return {
        "identity": identity,
        "is_authenticated": True,
        "display_name": display_name or identity,
    }


@auth.on.threads.create
async def on_thread_create(ctx: Auth.types.AuthContext, value: dict) -> None:
    """创建会话时,把 owner 写进 metadata,标记归属当前用户。
    注:此 handler 通过原地修改 value 注入 owner,不返回 filter(故返回 None),
    与下方 read/search 等返回 dict filter 的 handler 不同。"""
    metadata = value.setdefault("metadata", {})
    metadata["owner"] = ctx.user.identity


@auth.on.threads.read
async def on_thread_read(ctx: Auth.types.AuthContext, value: dict) -> dict:
    """读取会话:只允许读自己拥有的(返回 owner filter)。"""
    return {"owner": ctx.user.identity}


@auth.on.threads.search
async def on_thread_search(ctx: Auth.types.AuthContext, value: dict) -> dict:
    """列出/搜索会话:只返回自己的(实现左侧会话列表的按用户隔离)。"""
    return {"owner": ctx.user.identity}


@auth.on.threads.update
async def on_thread_update(ctx: Auth.types.AuthContext, value: dict) -> dict:
    """更新会话:限定自己的。"""
    return {"owner": ctx.user.identity}


@auth.on.threads.delete
async def on_thread_delete(ctx: Auth.types.AuthContext, value: dict) -> dict:
    """删除会话:限定自己的。"""
    return {"owner": ctx.user.identity}


@auth.on.threads.create_run
async def on_thread_create_run(ctx: Auth.types.AuthContext, value: dict) -> dict:
    """在会话上跑 run(发消息):只能在自己拥有的会话上跑,防止越权在他人会话执行。"""
    return {"owner": ctx.user.identity}


# --- 共享资源:显式放行(全员可读写,实现共享爆款库/风格) ---
# store = /shared 风格沉淀、/skills 方法论;assistants = 只读图。
# 这些是团队共享资产,放行(返回 None = 不加 owner 过滤)。


@auth.on.store
async def on_store(ctx: Auth.types.AuthContext, value: dict) -> None:
    """store(/shared、/skills)全员共享,不按 user 过滤。"""
    return None


@auth.on.assistants
async def on_assistants(ctx: Auth.types.AuthContext, value: dict) -> None:
    """assistants(图定义)全员共享(本地单图,所有操作放行)。
    注:返回 None = 不加过滤,放行全部 assistant 操作,非仅只读。"""
    return None


# --- 默认拒绝:上面没显式处理的资源/动作一律拒绝(default-deny,防越权口子) ---
@auth.on
async def deny_by_default(ctx: Auth.types.AuthContext, value: dict) -> bool:
    """兜底:未显式授权的操作一律拒绝。crons 等未用到的资源走这里。"""
    return False


