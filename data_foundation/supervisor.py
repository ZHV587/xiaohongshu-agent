from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

from data_foundation.scheduler import SchedulerConfig, build_scheduler


SCHEDULER_CYCLE_FAILED = "SCHEDULER_CYCLE_FAILED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BackgroundServiceSupervisor:
    def __init__(
        self,
        *,
        scheduler_factory: Callable[[], object] = build_scheduler,
        config: SchedulerConfig | None = None,
        enabled: bool = True,
        interval_seconds: float = 30.0,
    ):
        self.scheduler_factory = scheduler_factory
        self.config = config or SchedulerConfig()
        self.enabled = enabled
        self.interval_seconds = max(0.01, float(interval_seconds))
        self.instance_id = uuid4().hex
        self.accepting_work = False
        self.start_count = 0
        self.last_cycle_started_at: str | None = None
        self.last_cycle_finished_at: str | None = None
        self.last_cycle_status: str | None = None
        self.last_cycle_error_code: str | None = None
        self._scheduler = None
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # 独占单线程池跑 cycle:与默认 executor 分开,关停时可精确 join 本任务线程。
        self._executor: ThreadPoolExecutor | None = None
        self._cycle_future = None
        self._listener_task = None
        self._wake_event = asyncio.Event()

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self.accepting_work = True
        self._stop_event.clear()
        self._wake_event.clear()
        self._scheduler = self.scheduler_factory()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xhs-sched-cycle")
        self._task = asyncio.create_task(self._run(), name="xhs-data-foundation-supervisor")
        self.start_count += 1

    async def stop(self, *, grace_seconds: float = 10.0) -> None:
        self.accepting_work = False
        self._stop_event.set()
        self._wake_event.set()
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
        # 协作通知 cycle 尽快收敛(租户循环每轮检查 _stop_event)。
        scheduler = self._scheduler
        request_stop = getattr(scheduler, "request_stop", None)
        if callable(request_stop):
            request_stop()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=max(0.0, float(grace_seconds)))
            except TimeoutError:
                # _run 协程可被取消(它只是 await future);但底层 cycle 线程不取消 ——
                # 由下面 executor.shutdown(wait=True) 阻塞 join,绝不 detach(detach 会让
                # 孤儿线程与 _stop_scheduler 关 conn 抢同一连接)。
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            finally:
                self._task = None
        # 关键时序:先 join cycle 线程(确保它真正结束、不再用 conn),再关 conn/登记下线。
        if self._executor is not None:
            await asyncio.to_thread(self._executor.shutdown, True)  # wait=True
            self._executor = None
        self._stop_scheduler()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        self._listener_task = asyncio.create_task(self._listen_db_notifies())
        while self.accepting_work:
            self._wake_event.clear()
            scheduler = self._scheduler
            if scheduler is not None and self._executor is not None:
                self.last_cycle_started_at = _utc_now()
                try:
                    # 在独占线程池跑整轮 cycle(同步阻塞 DB/HTTP),不堵主事件循环。
                    # 跟踪 future:stop 时不 cancel 它(底层线程无法取消),而是靠
                    # scheduler.request_stop() 协作收敛 + executor.shutdown(wait=True) join。
                    self._cycle_future = loop.run_in_executor(
                        self._executor, lambda: asyncio.run(scheduler.run_cycle())
                    )
                    await self._cycle_future
                    self.last_cycle_status = "succeeded"
                    self.last_cycle_error_code = None
                except Exception:
                    self.last_cycle_status = "failed"
                    self.last_cycle_error_code = SCHEDULER_CYCLE_FAILED
                finally:
                    self._cycle_future = None
                    self.last_cycle_finished_at = _utc_now()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue

    async def _listen_db_notifies(self) -> None:
        """异步监听当前 Schema 的 PG 发件箱广播通知，连接断开时自动 5 秒退避重连。"""
        import logging
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row
        from data_foundation.db import database_url
        
        logger = logging.getLogger(__name__)
        db_url = database_url()
        
        while self.accepting_work:
            try:
                async with await AsyncConnection.connect(db_url, autocommit=True) as conn:
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute("SELECT current_schema()")
                        row = await cur.fetchone()
                        schema = row["current_schema"] if (row and row["current_schema"]) else "public"
                        channel = f"outbox_work_{schema}"
                        await cur.execute(f"LISTEN {channel}")
                    
                    logger.info("Outbox listener connected and listening to channel: %s", channel)
                    
                    async for notify in conn.notifies():
                        self._wake_event.set()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "Outbox listener connection lost, retrying in 5 seconds. Error: %s", 
                    exc
                )
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break

    def _stop_scheduler(self) -> None:
        scheduler = self._scheduler
        self._scheduler = None
        if scheduler is None:
            return
        stop = getattr(scheduler, "stop", None)
        if callable(stop):
            stop()
            return
        telemetry = getattr(scheduler, "telemetry", None)
        config = getattr(scheduler, "config", self.config)
        if telemetry is not None:
            telemetry.stop_instance(
                component=config.component,
                instance_id=config.instance_id,
                deployment_id=config.deployment_id,
            )


def supervisor_enabled() -> bool:
    return os.environ.get("XHS_SYNC_ENABLED", "false").strip().lower() == "true"


def build_supervisor() -> BackgroundServiceSupervisor:
    return BackgroundServiceSupervisor(
        enabled=supervisor_enabled(),
        interval_seconds=float(os.environ.get("XHS_SCHEDULER_INTERVAL_SECONDS", "30")),
    )
