"""模型健康探测后台任务:周期性强制重探网关,按质量序刷新 registry 活跃池。

与数据同步的 BackgroundServiceSupervisor 解耦——模型可用性是模型层的事,
不受 XHS_SYNC_ENABLED 门控。配置(网关/白名单)的唯一权威源是 config-center,
本任务每轮读 config-center 最新快照,强制重探(force_discover)后重建池:
- 网关新上线的白名单模型 → 自动进池(质量序)
- 网关下线/探测失败的模型 → 自动移出活跃池
- 全挂 → registry 保留旧池 + 记错(reload_from_config 内部处理),任务不崩

注:被动冷却(ModelRouterMiddleware 请求失败即冷却 30s)是两次探测之间的快反应,
本任务是慢周期(默认 300s)的权威刷新,二者互补。
"""
from __future__ import annotations

import asyncio
import logging
import os

from config_center import latest_config_snapshot

logger = logging.getLogger(__name__)


def probe_enabled() -> bool:
    return os.environ.get("XHS_MODEL_PROBE_ENABLED", "true").strip().lower() == "true"


def probe_interval_seconds() -> float:
    return float(os.environ.get("XHS_MODEL_PROBE_INTERVAL_SECONDS", "300"))


class ModelHealthProbe:
    """周期性刷新 registry 活跃池的轻量 asyncio 后台任务。"""

    def __init__(
        self,
        *,
        model_registry,
        enabled: bool = True,
        interval_seconds: float = 300.0,
        snapshot_provider=latest_config_snapshot,
    ):
        self.model_registry = model_registry
        self.enabled = enabled
        self.interval_seconds = max(1.0, float(interval_seconds))
        self.snapshot_provider = snapshot_provider
        self.last_probe_ok: bool | None = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="xhs-model-health-probe")

    async def stop(self, *, grace_seconds: float = 5.0) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=max(0.0, float(grace_seconds)))
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            finally:
                self._task = None

    def probe_once(self) -> None:
        """跑一轮探测刷新。同步方法,供 _run 在线程外调用或测试直接调。

        config-center 无快照(纯 env 部署/history 空)时跳过——本任务只刷新
        config-center 权威配置下的池;env 占位池由启动期决定,不在此覆盖。
        探测失败/全挂由 reload_from_config 吞下并记错,这里据返回值记录状态。
        """
        snapshot = self.snapshot_provider()
        if snapshot is None:
            return
        self.last_probe_ok = self.model_registry.reload_from_config(snapshot, force_discover=True)
        if not self.last_probe_ok:
            logger.warning("model_health_probe: 全挂或探测失败,保留旧活跃池 version=%s", snapshot.version)

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.to_thread(self.probe_once)
            except Exception:
                # 探测本身的意外异常不得让任务死掉(下一轮继续)。
                logger.warning("model_health_probe: 探测轮异常,跳过本轮", exc_info=True)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue


def build_model_health_probe(model_registry) -> ModelHealthProbe:
    return ModelHealthProbe(
        model_registry=model_registry,
        enabled=probe_enabled(),
        interval_seconds=probe_interval_seconds(),
    )
