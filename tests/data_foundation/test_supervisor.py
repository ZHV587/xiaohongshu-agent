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

    async def run_cycle(self):
        self.cycles += 1

    def stop(self):
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
