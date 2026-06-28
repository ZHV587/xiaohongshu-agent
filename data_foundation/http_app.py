from __future__ import annotations

import os
from contextlib import asynccontextmanager

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from config_center import latest_config_snapshot, project_config_to_env
from data_foundation.internal_api import internal_routes
from data_foundation.runtime_facts import create_runtime_snapshot, utc_now
from data_foundation.supervisor import build_supervisor
from model_health import build_model_health_probe


def shutdown_grace_seconds() -> float:
    return float(os.environ.get("XHS_SCHEDULER_SHUTDOWN_GRACE_SECONDS", "10"))


def _resolve_model_registry():
    """取 agent 进程内的 ModelRegistry 单例,供启动对齐与定时健康探测刷新模型池。

    延迟 import:agent.py 是图模块,模块级 import 会造成 http_app ←→ agent 导入
    顺序耦合。lifespan 启动时 graph 早已被 langgraph server 加载,此处命中同一份
    已初始化的单例(N_WORKERS=1 同进程同内存)。

    不做降级:拿不到 registry 意味着进程模型假设(graph 与 http_app 同进程)已被
    打破,静默降级会让模型热重载/探测失效。直接让异常上抛中断启动,暴露问题。
    """
    from agent import model_registry

    return model_registry


async def ok(_request):
    return JSONResponse({"ok": True})


@asynccontextmanager
async def lifespan(app: Starlette):
    # 启动期任一步失败都必须回滚已启动组件,否则 supervisor 的 cycle 线程/DB listen 连接、
    # health_probe 会泄漏(try/finally 的 finally 只在 yield 后才覆盖,startup 抛错到不了 yield)。
    supervisor = None
    health_probe = None
    try:
        supervisor = build_supervisor()
        await supervisor.start()
        runtime_snapshot = create_runtime_snapshot(supervisor)

        # 模型池单一数据源:启动对齐 —— 进程刚起时 registry 是空的(agent.py 不灌 env)。
        # 用 config-center 最新快照构池填充;config-center 为空(纯 env/全新部署)则
        # 跳过,registry 维持空池、router 回退到装配占位 model,待 admin 配置后生效。
        model_registry = _resolve_model_registry()
        startup_snapshot = latest_config_snapshot()
        if startup_snapshot is not None:
            # 冷启动对齐:把 config-center 当前配置投影进 os.environ,使 env-reading 消费方
            # (飞书工具等)遵从 config-center 为唯一权威源,而非启动时 .env 的旧值。
            project_config_to_env(startup_snapshot.values)
            model_registry.reload_from_config(startup_snapshot, force_discover=True)

        # 定时健康探测:独立后台任务(不绑 XHS_SYNC_ENABLED),周期强制重探刷新活跃池。
        health_probe = build_model_health_probe(model_registry)
        await health_probe.start()
    except BaseException:
        # 回滚:已起的 health_probe 先停,再停 supervisor(顺序与正常 finally 一致)。
        if health_probe is not None:
            await health_probe.stop()
        if supervisor is not None:
            await supervisor.stop(grace_seconds=shutdown_grace_seconds())
        raise

    app.state.supervisor = supervisor
    app.state.runtime_snapshot = runtime_snapshot
    app.state.model_health_probe = health_probe
    try:
        yield {"supervisor": supervisor, "runtime_snapshot": runtime_snapshot}
    finally:
        await health_probe.stop()
        await supervisor.stop(grace_seconds=shutdown_grace_seconds())
        runtime_snapshot.stop(observed_at=utc_now())
        app.state.supervisor = None
        app.state.runtime_snapshot = None
        app.state.model_health_probe = None


app = Starlette(routes=[Route("/ok", ok), *internal_routes], lifespan=lifespan)
