from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_langgraph_registers_http_app():
    config = json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))

    assert config["http"]["app"] == "./data_foundation/http_app.py:app"
    assert config["http"]["enable_custom_route_auth"] is False


@pytest.mark.asyncio
async def test_http_app_lifespan_starts_and_stops_supervisor(monkeypatch):
    import data_foundation.http_app as http_app

    events = []
    captured = {}

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

    sentinel_registry = object()

    def fake_build_supervisor(*, model_registry=None):
        captured["model_registry"] = model_registry
        return FakeSupervisor()

    # 隔离对 agent 模块的真实 import(避免拉起模型探测),只验证 registry 被透传。
    monkeypatch.setattr(http_app, "_resolve_model_registry", lambda: sentinel_registry)
    monkeypatch.setattr(http_app, "build_supervisor", fake_build_supervisor)
    monkeypatch.setattr(http_app, "shutdown_grace_seconds", lambda: 7)

    async with http_app.lifespan(http_app.app) as state:
        assert events == ["start"]
        assert state["supervisor"] is not None
        assert state["runtime_snapshot"].status == "running"

    assert events == ["start", ("stop", 7)]
    assert state["runtime_snapshot"].status == "stopped"
    # 模型池热重载依赖 registry 被注入 supervisor → scheduler。
    assert captured["model_registry"] is sentinel_registry


@pytest.mark.asyncio
async def test_http_app_lifespan_persists_runtime_state_on_application(monkeypatch):
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

    monkeypatch.setattr(http_app, "_resolve_model_registry", lambda: object())
    monkeypatch.setattr(http_app, "build_supervisor", lambda *, model_registry=None: FakeSupervisor())

    async with http_app.lifespan(http_app.app):
        assert http_app.app.state.supervisor.instance_id == "instance-2"
        assert http_app.app.state.runtime_snapshot.status == "running"
