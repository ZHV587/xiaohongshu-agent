from __future__ import annotations

import asyncio
import threading

import pytest

from data_foundation.scheduler import SchedulerConfig
from data_foundation.supervisor import BackgroundServiceSupervisor, build_supervisor, supervisor_enabled


class FakeScheduler:
    def __init__(self):
        self.cycles = 0
        self.stops = []
        self.calls = []  # 记录 request_stop / stop 调用顺序,验证关停时序

    async def run_cycle(self):
        self.cycles += 1

    def request_stop(self):
        self.calls.append("request_stop")

    def stop(self):
        self.calls.append("stop")
        self.stops.append(True)


@pytest.mark.asyncio
async def test_supervisor_starts_once_and_stops_gracefully():
    scheduler = FakeScheduler()
    supervisor = BackgroundServiceSupervisor(
        scheduler_factory=lambda: scheduler,
        config=SchedulerConfig(component="scheduler", instance_id="i1", deployment_id="d1"),
        interval_seconds=0.01,
    )

    await supervisor.start()
    await supervisor.start()
    await asyncio.sleep(0.03)
    await supervisor.stop(grace_seconds=1)

    assert supervisor.start_count == 1
    assert supervisor.accepting_work is False
    assert scheduler.cycles >= 1
    assert scheduler.stops == [True]
    # 关停时序:先 request_stop(协作通知)再 stop(关 conn/登记下线),且 executor 已清。
    assert scheduler.calls == ["request_stop", "stop"]
    assert supervisor._executor is None


@pytest.mark.asyncio
async def test_supervisor_does_not_start_when_disabled():
    scheduler = FakeScheduler()
    supervisor = BackgroundServiceSupervisor(
        scheduler_factory=lambda: scheduler,
        enabled=False,
        interval_seconds=0.01,
    )

    await supervisor.start()
    await asyncio.sleep(0.02)
    await supervisor.stop(grace_seconds=1)

    assert supervisor.start_count == 0
    assert scheduler.cycles == 0


@pytest.mark.asyncio
async def test_supervisor_runs_scheduler_cycles_off_event_loop_thread():
    event_loop_thread = threading.get_ident()
    cycle_threads = []

    class ThreadCheckingScheduler(FakeScheduler):
        async def run_cycle(self):
            cycle_threads.append(threading.get_ident())
            await super().run_cycle()

    scheduler = ThreadCheckingScheduler()
    supervisor = BackgroundServiceSupervisor(
        scheduler_factory=lambda: scheduler,
        interval_seconds=0.01,
    )

    await supervisor.start()
    await asyncio.sleep(0.03)
    await supervisor.stop(grace_seconds=1)

    assert cycle_threads
    assert all(thread_id != event_loop_thread for thread_id in cycle_threads)


def test_build_supervisor_is_env_gated(monkeypatch):
    monkeypatch.delenv("XHS_SYNC_ENABLED", raising=False)
    assert supervisor_enabled() is False

    disabled = build_supervisor()
    assert disabled.enabled is False

    monkeypatch.setenv("XHS_SYNC_ENABLED", "true")
    enabled = build_supervisor()
    assert supervisor_enabled() is True
    assert enabled.enabled is True


@pytest.mark.asyncio
async def test_supervisor_keeps_running_after_cycle_exception():
    class FlakyScheduler(FakeScheduler):
        async def run_cycle(self):
            self.cycles += 1
            if self.cycles == 1:
                raise RuntimeError("first cycle fails")

    scheduler = FlakyScheduler()
    supervisor = BackgroundServiceSupervisor(
        scheduler_factory=lambda: scheduler,
        interval_seconds=0.01,
    )

    await supervisor.start()
    await asyncio.sleep(0.05)
    await supervisor.stop(grace_seconds=1)

    assert scheduler.cycles >= 2
    assert scheduler.stops == [True]
