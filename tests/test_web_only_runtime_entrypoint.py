from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_project_has_no_interactive_cli_entrypoint():
    assert not (ROOT / "cli.py").exists()


def test_packaging_does_not_expose_cli_module():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"cli"' not in pyproject


def test_backend_has_no_cli_backend_factory():
    backends = (ROOT / "backends.py").read_text(encoding="utf-8")
    assert "build_cli_backend" not in backends
    assert "CLI" not in backends


def test_web_bridge_uses_web_bridge_runner_name():
    internal_client = (ROOT / "web" / "src" / "lib" / "server" / "internal-client.ts").read_text(
        encoding="utf-8"
    )
    assert "web_bridge_runner.py" in internal_client
    assert "cli_runner" not in internal_client
    assert (ROOT / "tools" / "web_bridge_runner.py").exists()
    assert not (ROOT / "tools" / "cli_runner.py").exists()
