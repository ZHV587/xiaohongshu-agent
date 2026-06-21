from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
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

    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self.accepting_work = True
        self._stop_event.clear()
        self._scheduler = self.scheduler_factory()
        self._task = asyncio.create_task(self._run(), name="xhs-data-foundation-supervisor")
        self.start_count += 1

    async def stop(self, *, grace_seconds: float = 10.0) -> None:
        self.accepting_work = False
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
        self._stop_scheduler()

    async def _run(self) -> None:
        while self.accepting_work:
            scheduler = self._scheduler
            if scheduler is not None:
                self.last_cycle_started_at = _utc_now()
                try:
                    await asyncio.to_thread(lambda: asyncio.run(scheduler.run_cycle()))
                    self.last_cycle_status = "succeeded"
                    self.last_cycle_error_code = None
                except Exception:
                    self.last_cycle_status = "failed"
                    self.last_cycle_error_code = SCHEDULER_CYCLE_FAILED
                finally:
                    self.last_cycle_finished_at = _utc_now()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                continue

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
