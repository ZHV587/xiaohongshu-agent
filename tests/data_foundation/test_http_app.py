from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_langgraph_registers_http_app():
    config = json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))

    assert config["http"]["app"] == "./data_foundation/http_app.py:app"
    assert config["http"]["enable_custom_route_auth"] is False


def test_assert_single_worker_accepts_one_or_unset(monkeypatch):
    import data_foundation.http_app as http_app

    monkeypatch.delenv("N_WORKERS", raising=False)
    http_app._assert_single_worker()  # 未设 → 默认 1,通过
    monkeypatch.setenv("N_WORKERS", "1")
    http_app._assert_single_worker()  # 显式 1,通过


def test_assert_single_worker_rejects_multi_worker(monkeypatch):
    """N_WORKERS>1 会让冷启动 os.environ 对齐/模型池热重载在 worker 间分裂,须启动即拒绝。"""
    import data_foundation.http_app as http_app

    monkeypatch.setenv("N_WORKERS", "2")
    with pytest.raises(RuntimeError, match="N_WORKERS=2 is unsupported"):
        http_app._assert_single_worker()


@pytest.mark.asyncio
async def test_http_app_lifespan_starts_and_stops_supervisor(monkeypatch):
    import data_foundation.http_app as http_app

    events = []

    class FakeSupervisor:
        enabled = False
        interval_seconds = 30
        instance_id = "instance-1"
        accepting_work = False
        last_cycle_started_at = None
        last_cycle_finished_at = None
        last_cycle_status = None
        last_cycle_error_code = None

        async def start(self):
            events.append("start")

        async def stop(self, *, grace_seconds):
            events.append(("stop", grace_seconds))

    class FakeProbe:
        async def start(self):
            events.append("probe_start")

        async def stop(self):
            events.append("probe_stop")

    class FakeRegistry:
        def __init__(self):
            self.reloaded = []

        def reload_from_config(self, snapshot, *, force_discover=False):
            self.reloaded.append((snapshot.version, force_discover))
            return True

    registry = FakeRegistry()
    monkeypatch.setenv("FEISHU_APP_ID", "seed")  # lifespan 投影会写 os.environ,setenv 以便 teardown 回滚
    monkeypatch.setattr(http_app, "_run_startup_migrations", lambda: None)  # lifespan 现在启动即迁移,单测不连真库
    monkeypatch.setattr(http_app, "build_supervisor", lambda: FakeSupervisor())
    monkeypatch.setattr(http_app, "shutdown_grace_seconds", lambda: 7)
    monkeypatch.setattr(http_app, "_resolve_model_registry", lambda: registry)
    monkeypatch.setattr(http_app, "build_model_health_probe", lambda reg: FakeProbe())
    # 启动对齐:config-center 有快照 → 启动即投影 env + reload(force 探测)
    monkeypatch.setattr(
        http_app,
        "latest_config_snapshot",
        lambda: type("S", (), {"version": "v-start", "values": {"FEISHU_APP_ID": "cli_x"}})(),
    )

    async with http_app.lifespan(http_app.app) as state:
        assert "start" in events and "probe_start" in events
        assert state["supervisor"] is not None
        assert state["runtime_snapshot"].status == "running"

    # 关停顺序:先停探测,再停 supervisor
    assert events == ["start", "probe_start", "probe_stop", ("stop", 7)]
    assert state["runtime_snapshot"].status == "stopped"
    # 启动对齐确实 reload 了 config-center 快照(force 探测)
    assert registry.reloaded == [("v-start", True)]


@pytest.mark.asyncio
async def test_http_app_lifespan_skips_align_when_no_snapshot(monkeypatch):
    """config-center 为空(纯 env/全新部署):启动不 reload,registry 维持空池。"""
    import data_foundation.http_app as http_app

    class FakeSupervisor:
        enabled = True
        interval_seconds = 30
        instance_id = "instance-2"
        accepting_work = True
        last_cycle_started_at = None
        last_cycle_finished_at = None
        last_cycle_status = None
        last_cycle_error_code = None

        async def start(self):
            return None

        async def stop(self, *, grace_seconds):
            return None

    class FakeProbe:
        async def start(self):
            return None

        async def stop(self):
            return None

    class FakeRegistry:
        def __init__(self):
            self.reloaded = []

        def reload_from_config(self, snapshot, *, force_discover=False):
            self.reloaded.append(snapshot.version)
            return True

    registry = FakeRegistry()
    monkeypatch.setattr(http_app, "_run_startup_migrations", lambda: None)  # lifespan 现在启动即迁移,单测不连真库
    monkeypatch.setattr(http_app, "build_supervisor", lambda: FakeSupervisor())
    monkeypatch.setattr(http_app, "_resolve_model_registry", lambda: registry)
    monkeypatch.setattr(http_app, "build_model_health_probe", lambda reg: FakeProbe())
    monkeypatch.setattr(http_app, "latest_config_snapshot", lambda: None)

    async with http_app.lifespan(http_app.app):
        assert http_app.app.state.supervisor.instance_id == "instance-2"
        assert http_app.app.state.runtime_snapshot.status == "running"
    assert registry.reloaded == []  # 无快照,不启动对齐
