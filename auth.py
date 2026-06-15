"""LangGraph 自定义鉴权(1b-3 多用户隔离)。

本地阶段:用请求头里的 mock token 模拟用户身份(无真飞书 OAuth,localhost 无公网回调)。
  前端通过 Authorization: Bearer <token> 传身份,token 形如 "mock-user-<id>"。
上云阶段:把 _identity_from_token 换成校验真飞书 OAuth token / JWT 即可,其余隔离逻辑不变。

隔离模型(对应设计):
  - thread(会话)/ 其 /drafts → 按 user 隔离:owner metadata + search/read filter
  - /shared(风格)/ /skills(爆款方法论)→ 全员共享:store 不按 user 过滤
"""
import os

from langgraph_sdk import Auth

auth = Auth()

# 本地开发兜底用户:未带 token 时用它,保证单机调试不被挡。
# ⚠️ 生产/上云前必须把 XHS_DEV_FALLBACK_USER 设为空(或代码改默认 None),
#    否则任何不带 token 的请求都会被认成同一个用户,可越权访问其会话。
#    设为空字符串时,下方 authenticate 会因 identity 为空而返回 401。
_DEV_FALLBACK_USER = os.environ.get("XHS_DEV_FALLBACK_USER", "dev-user")


def _identity_from_token(token: str | None) -> str | None:
    """从 Bearer token 解析用户标识。

    本地约定:token 形如 "mock-user-A" → 身份 "mock-user-A"。
    上云时替换为:校验飞书 OAuth access_token → 返回飞书 open_id/user_id。
    """
    if not token:
        return None
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token or None


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

    identity = _identity_from_token(raw) or _DEV_FALLBACK_USER
    if not identity:
        raise Auth.exceptions.HTTPException(status_code=401, detail="缺少身份令牌(Authorization)")
    return {
        "identity": identity,
        "is_authenticated": True,
        "display_name": identity,
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


