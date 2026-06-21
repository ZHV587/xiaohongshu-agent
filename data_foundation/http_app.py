from __future__ import annotations

import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from data_foundation.internal_api import internal_routes
from data_foundation.runtime_facts import create_runtime_snapshot, utc_now
from data_foundation.supervisor import build_supervisor


def shutdown_grace_seconds() -> float:
    return float(os.environ.get("XHS_SCHEDULER_SHUTDOWN_GRACE_SECONDS", "10"))


def _resolve_model_registry():
    """取 agent 进程内的 ModelRegistry 单例,供后台 cycle 热重载模型池。

    延迟 import:agent.py 是图模块,模块级 import 会造成 http_app ←→ agent 的导入
    顺序耦合。lifespan 启动时 graph 早已被 langgraph server 加载,此处 import 命中
    同一份已初始化的单例(N_WORKERS=1 同进程)。

    不做降级:拿不到 registry 意味着进程模型假设(graph 与 http_app 同进程同内存)
    已被打破,此时静默关闭热载会退回原 bug。直接让异常上抛中断启动,暴露问题。
    """
    from agent import model_registry

    return model_registry


async def ok(_request):
    return JSONResponse({"ok": True})


@asynccontextmanager
async def lifespan(app: Starlette):
    supervisor = build_supervisor(model_registry=_resolve_model_registry())
    await supervisor.start()
    runtime_snapshot = create_runtime_snapshot(supervisor)
    app.state.supervisor = supervisor
    app.state.runtime_snapshot = runtime_snapshot
    try:
        yield {"supervisor": supervisor, "runtime_snapshot": runtime_snapshot}
    finally:
        await supervisor.stop(grace_seconds=shutdown_grace_seconds())
        runtime_snapshot.stop(observed_at=utc_now())
        app.state.supervisor = None
        app.state.runtime_snapshot = None


app = Starlette(routes=[Route("/ok", ok), *internal_routes], lifespan=lifespan)
