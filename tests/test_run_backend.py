from __future__ import annotations

from pathlib import Path

from tools.run_backend import build_langgraph_dev_args


def test_run_backend_uses_project_venv_and_local_langgraph_server():
    project_root = Path("/srv/xhs")

    args = build_langgraph_dev_args(project_root)

    assert args == [
        "/srv/xhs/.venv/bin/python3",
        "-m",
        "langgraph_cli",
        "dev",
        "--port",
        "2030",
        "--host",
        "127.0.0.1",
    ]
