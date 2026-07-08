from __future__ import annotations

import asyncio
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


def _assert_single_worker() -> None:
    """强制单进程不变量:模型池/健康探测/config 热重载与冷启动 os.environ 对齐,全部依赖
    graph 与 http_app 共享**同一进程内**的单例与进程环境(见 docker-compose N_WORKERS 注释、
    config_center.project_config_to_env)。N_WORKERS>1 时每个 worker 各持一份独立 registry、
    且 lifespan 的 os.environ 冷启动对齐只作用于 http_app 所在 worker —— 其余 worker 的飞书/检索
    配置静默停留在启动时 .env 旧值,admin 改配置也只热切中招的那个 worker,形成难排查的分裂脑。

    这里把隐式前提显式化:启动即校验,>1 直接拒绝启动,暴露误配,而不是带病运行到线上才发现
    配置在 worker 间不一致。需横向扩容须先改造为跨进程 registry/config 广播再放开此限制。
    """
    raw = os.environ.get("N_WORKERS", "1").strip() or "1"
    try:
        workers = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"N_WORKERS must be an integer, got {raw!r}") from exc
    if workers > 1:
        raise RuntimeError(
            f"N_WORKERS={workers} is unsupported: the model registry, health probe, "
            "config hot-reload and cold-start os.environ alignment all assume a single "
            "process. Set N_WORKERS=1 (or implement cross-process config broadcast first)."
        )


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


def _run_startup_migrations() -> None:
    """启动即迁移:对生产库执行 schema.sql(全量幂等:create ... if not exists / drop if exists /
    upsert 重算,含 ivfflat→HNSW 向量索引的条件升级块)。

    根因:run_migrations 此前在整个代码库没有任何运行时/部署调用点(只有测试用),
    生产 schema 与 schema.sql 静默漂移 —— HNSW 升级块从未执行,向量检索仍走 ivfflat
    (probes 默认 1,每次只扫约 1% 向量),`SET LOCAL hnsw.ef_search` 一直是死代码,
    "放宽召回"在生产上是 no-op。启动时显式跑迁移,让 schema.sql 成为唯一权威来源;
    失败直接上抛中断启动(带病运行比启动失败更难排查)。
    """
    from data_foundation import db

    with db.connect() as conn:
        db.run_migrations(conn)


async def ok(_request):
    return JSONResponse({"ok": True})


@asynccontextmanager
async def lifespan(app: Starlette):
    # 启动期任一步失败都必须回滚已启动组件,否则 supervisor 的 cycle 线程/DB listen 连接、
    # health_probe 会泄漏(try/finally 的 finally 只在 yield 后才覆盖,startup 抛错到不了 yield)。
    supervisor = None
    health_probe = None
    try:
        # 启动即校验单进程不变量:>1 worker 会让 os.environ 冷启动对齐/模型池热重载在 worker
        # 间分裂。放在最前,误配立即失败而非带病运行。
        _assert_single_worker()
        # 迁移先于一切组件:supervisor/检索都假设 schema 与 schema.sql 一致。
        # 同步 psycopg 调用卸到线程,不阻塞事件循环(首次建 HNSW 索引可能要数十秒)。
        await asyncio.to_thread(_run_startup_migrations)
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
