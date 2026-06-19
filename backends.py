"""三路由文件后端工厂。

CompositeBackend 按路径前缀路由(已实测:路由会剥掉前缀):
- /skills/ → FilesystemBackend,root_dir 指向项目下的 skills/ 目录本身
  (因为前缀 /skills/ 被剥掉后,/topic-content/SKILL.md 需对应 skills/topic-content/SKILL.md)。
  共享只读,virtual_mode=True 避免 Windows 绝对路径问题。
- /shared/ → StoreBackend,跨会话/用户共享(风格沉淀)。server 注入 store。
- /memories/ → StoreBackend,团队共享自学习记忆(MemoryMiddleware 的 AGENTS.md)。
- /shared/ → ConcurrencySafeStoreBackend,跨会话/用户共享(风格沉淀)。server 注入 store。
- /memories/ → ConcurrencySafeStoreBackend,团队共享自学习记忆(MemoryMiddleware 的 AGENTS.md)。
  与 /shared/ 同 namespace,全员一份团队方法论。
- /user-memories/ → ConcurrencySafeStoreBackend,按 user 隔离的个人记忆(namespace 含 open_id)。
- /drafts/ 及其他 → 默认 StateBackend,随会话隔离。
"""
import os

from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.state import StateBackend
from deepagents.backends.store import StoreBackend

# __file__ 是 backends.py 的绝对路径,其所在目录即项目根——
# 不随调用时的工作目录漂移,比 os.getcwd() 健壮。
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))


class ConcurrencySafeStoreBackend(StoreBackend):
    """已废弃进程内悲观锁，直接继承官方 StoreBackend 原生操作以实现水平扩展友好。"""
    pass


def _user_memory_namespace(rt) -> tuple[str, ...]:
    """个人记忆的 Store namespace:按当前用户身份物理分区。

    身份取 `rt.server_info.user.identity`(auth.py 里即飞书 open_id)。
    两处 None 兜底——否则无身份请求会 AttributeError 崩在 Store 操作上:
    - server_info 为 None:无 LangGraph server 的进程内运行,
      但回调仍可能被探测调用)。
    - user 为 None:server 在但请求未携带可解析身份(已被 auth 拦在 401,双保险)。
    兜底归到 "__anon__" 分区,与任何真实 open_id 不冲突。
    """
    identity = "__anon__"
    server_info = getattr(rt, "server_info", None)
    user = getattr(server_info, "user", None) if server_info is not None else None
    if user is not None:
        # BaseUser 协议:既支持属性也支持下标访问,优先属性。
        ident = getattr(user, "identity", None)
        if ident:
            identity = str(ident)
    return (identity, "user-memories")


def build_backend() -> CompositeBackend:
    """构造多路由 CompositeBackend(server 模式)。"""
    skills_root = os.path.join(_PROJECT_ROOT, ".agents", "skills")
    skills_backend = FilesystemBackend(root_dir=skills_root, virtual_mode=True)
    shared_store = ConcurrencySafeStoreBackend(namespace=lambda rt: ("xhs-shared",))
    team_memory = ConcurrencySafeStoreBackend(namespace=lambda rt: ("xhs-shared",))
    user_memory = ConcurrencySafeStoreBackend(namespace=_user_memory_namespace)
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": skills_backend,
            "/shared/": shared_store,
            "/memories/": team_memory,
            "/user-memories/": user_memory,
        },
    )

