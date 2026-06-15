"""三路由文件后端工厂。

CompositeBackend 按路径前缀路由(已实测:路由会剥掉前缀):
- /skills/ → FilesystemBackend,root_dir 指向项目下的 skills/ 目录本身
  (因为前缀 /skills/ 被剥掉后,/topic-content/SKILL.md 需对应 skills/topic-content/SKILL.md)。
  共享只读,virtual_mode=True 避免 Windows 绝对路径问题。
- /shared/ → StoreBackend,跨会话/用户共享(风格沉淀)。server 注入 store。
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


def build_backend() -> CompositeBackend:
    """构造三路由 CompositeBackend。"""
    skills_root = os.path.join(_PROJECT_ROOT, "skills")
    skills_backend = FilesystemBackend(root_dir=skills_root, virtual_mode=True)
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": skills_backend,
            "/shared/": StoreBackend(namespace=lambda rt: ("xhs-shared",)),
        },
    )


def build_cli_backend() -> FilesystemBackend:
    """CLI/进程内模式用:全部走磁盘 FilesystemBackend(与 1a 一致)。

    StoreBackend 需要 server 注入 store,进程内 agent.stream 没有 server,
    故 CLI 不用 CompositeBackend,直接用磁盘后端(覆盖写友好、无需 store)。
    """
    return FilesystemBackend(root_dir=_PROJECT_ROOT, virtual_mode=True)

