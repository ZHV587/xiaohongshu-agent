from __future__ import annotations

from pathlib import Path

from scripts import deploy, deploy_health_check, runtime_import_smoke


class _FakeStdout:
    def __init__(self, lines: list[str], status: int) -> None:
        self._lines = lines
        self.channel = self
        self._status = status

    def __iter__(self):
        return iter(self._lines)

    def recv_exit_status(self) -> int:
        return self._status


class _FakeSsh:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.commands: list[str] = []

    def exec_command(self, cmd: str):
        self.commands.append(cmd)
        status = self.statuses.pop(0)
        return None, _FakeStdout([f"ran {cmd}\n"], status), []


def test_deployment_commands_use_runtime_smoke_not_pytest() -> None:
    commands = deploy.deployment_commands()

    joined = "\n".join(commands)

    assert "pytest" not in joined
    assert "uv pip install" not in joined
    assert "scripts/runtime_import_smoke.py" in joined
    assert "scripts/deploy_health_check.py" in joined


def test_runtime_import_smoke_adds_repo_root_to_pythonpath(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    without_root = [item for item in runtime_import_smoke.sys.path if item != str(root)]
    monkeypatch.setattr(runtime_import_smoke.sys, "path", without_root)

    runtime_import_smoke._ensure_repo_root_on_path()

    assert runtime_import_smoke.sys.path[0] == str(root)


def test_execute_commands_aborts_on_first_failure() -> None:
    ssh = _FakeSsh([0, 23, 0])
    commands = ["first", "second", "third"]

    status = deploy.execute_commands(ssh, commands)

    assert status == 23
    assert ssh.commands == ["first", "second"]


def test_health_check_accepts_healthy_runtime(monkeypatch) -> None:
    def fake_request_json(url: str, headers: dict[str, str]) -> dict:
        assert headers["X-XHS-Internal-Key"] == "secret"
        assert headers["X-XHS-Open-Id"] == "ou_admin"
        if url == "http://127.0.0.1:2030/internal/model/status":
            return {
                "ok": True,
                "config_center_enabled": True,
                "registry": {"active_models": ["model-a"], "last_error": None},
            }
        assert url == "http://127.0.0.1:2030/internal/health/facts"
        return {
            "ok": True,
            "modules": {
                "startup": {"status": "running"},
                "scheduler": {"status": "healthy"},
                "database": {"status": "healthy"},
            },
        }

    monkeypatch.setattr(deploy_health_check, "_request_json", fake_request_json)

    assert deploy_health_check.check_health(
        "http://127.0.0.1:2030",
        {"XHS_INTERNAL_SECRET": "secret", "XHS_ADMIN_OPEN_IDS": "ou_admin,ou_other"},
    )


def test_health_check_rejects_degraded_database(monkeypatch) -> None:
    def fake_request_json(url: str, _headers: dict[str, str]) -> dict:
        if url.endswith("/internal/model/status"):
            return {
                "ok": True,
                "config_center_enabled": True,
                "registry": {"active_models": ["model-a"], "last_error": None},
            }
        return {
            "ok": True,
            "modules": {
                "startup": {"status": "running"},
                "scheduler": {"status": "healthy"},
                "database": {"status": "degraded"},
            },
        }

    monkeypatch.setattr(deploy_health_check, "_request_json", fake_request_json)

    assert not deploy_health_check.check_health(
        "http://127.0.0.1:2030",
        {"XHS_INTERNAL_SECRET": "secret", "XHS_ADMIN_OPEN_IDS": "ou_admin"},
    )


def test_health_check_rejects_empty_config_center_model_pool(monkeypatch) -> None:
    def fake_request_json(url: str, _headers: dict[str, str]) -> dict:
        if url.endswith("/internal/model/status"):
            return {
                "ok": True,
                "config_center_enabled": True,
                "registry": {"active_models": [], "last_error": "discovery failed"},
            }
        return {
            "ok": True,
            "modules": {
                "startup": {"status": "running"},
                "scheduler": {"status": "healthy"},
                "database": {"status": "healthy"},
            },
        }

    monkeypatch.setattr(deploy_health_check, "_request_json", fake_request_json)

    assert not deploy_health_check.check_health(
        "http://127.0.0.1:2030",
        {"XHS_INTERNAL_SECRET": "secret", "XHS_ADMIN_OPEN_IDS": "ou_admin"},
    )


def test_health_check_allows_env_mode_without_registry_pool(monkeypatch) -> None:
    def fake_request_json(url: str, _headers: dict[str, str]) -> dict:
        if url.endswith("/internal/model/status"):
            return {
                "ok": True,
                "config_center_enabled": False,
                "registry": {"active_models": [], "last_error": None},
            }
        return {
            "ok": True,
            "modules": {
                "startup": {"status": "running"},
                "scheduler": {"status": "healthy"},
                "database": {"status": "healthy"},
            },
        }

    monkeypatch.setattr(deploy_health_check, "_request_json", fake_request_json)

    assert deploy_health_check.check_health(
        "http://127.0.0.1:2030",
        {"XHS_INTERNAL_SECRET": "secret", "XHS_ADMIN_OPEN_IDS": "ou_admin"},
    )
