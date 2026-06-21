from __future__ import annotations

import asyncio

import pytest

from model_health import ModelHealthProbe, build_model_health_probe


class FakeRegistry:
    def __init__(self, reload_result=True):
        self.calls = []
        self.reload_result = reload_result

    def reload_from_config(self, snapshot, *, force_discover=False):
        self.calls.append((snapshot.version, force_discover))
        if isinstance(self.reload_result, Exception):
            raise self.reload_result
        return self.reload_result


class _Snap:
    def __init__(self, version):
        self.version = version


def test_probe_once_reloads_with_force():
    reg = FakeRegistry(reload_result=True)
    probe = ModelHealthProbe(
        model_registry=reg,
        snapshot_provider=lambda: _Snap("v1"),
    )
    probe.probe_once()
    assert reg.calls == [("v1", True)]  # 强制重探
    assert probe.last_probe_ok is True


def test_probe_once_skips_when_no_snapshot():
    reg = FakeRegistry()
    probe = ModelHealthProbe(model_registry=reg, snapshot_provider=lambda: None)
    probe.probe_once()
    assert reg.calls == []  # config-center 空,不刷新


def test_probe_once_records_failure_without_raising():
    reg = FakeRegistry(reload_result=False)  # 全挂:reload 返回 False
    probe = ModelHealthProbe(model_registry=reg, snapshot_provider=lambda: _Snap("v-down"))
    probe.probe_once()  # 不抛
    assert probe.last_probe_ok is False


@pytest.mark.asyncio
async def test_probe_loop_runs_and_stops():
    reg = FakeRegistry(reload_result=True)
    probe = ModelHealthProbe(
        model_registry=reg,
        interval_seconds=3600,  # 长间隔:只跑首轮就停
        snapshot_provider=lambda: _Snap("v1"),
    )
    await probe.start()
    # 让首轮 probe_once 跑完
    for _ in range(50):
        if reg.calls:
            break
        await asyncio.sleep(0.01)
    await probe.stop()
    assert reg.calls and reg.calls[0] == ("v1", True)
    assert probe._task is None


@pytest.mark.asyncio
async def test_probe_disabled_does_not_start():
    reg = FakeRegistry()
    probe = ModelHealthProbe(
        model_registry=reg, enabled=False, snapshot_provider=lambda: _Snap("v1")
    )
    await probe.start()
    await asyncio.sleep(0.02)
    assert reg.calls == []
    assert probe._task is None
    await probe.stop()  # stop 在未启动时安全


@pytest.mark.asyncio
async def test_probe_loop_survives_reload_exception():
    """reload 抛意外异常,任务不死(下一轮继续)。"""
    reg = FakeRegistry(reload_result=RuntimeError("boom"))
    probe = ModelHealthProbe(
        model_registry=reg, interval_seconds=3600, snapshot_provider=lambda: _Snap("v1")
    )
    await probe.start()
    for _ in range(50):
        if reg.calls:
            break
        await asyncio.sleep(0.01)
    await probe.stop()
    assert reg.calls  # 跑过且没让任务崩到无法 stop


def test_build_model_health_probe_env_gated(monkeypatch):
    monkeypatch.setenv("XHS_MODEL_PROBE_ENABLED", "false")
    monkeypatch.setenv("XHS_MODEL_PROBE_INTERVAL_SECONDS", "120")
    probe = build_model_health_probe(FakeRegistry())
    assert probe.enabled is False
    assert probe.interval_seconds == 120
