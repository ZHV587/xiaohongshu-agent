# tools/run_backend.py
import os
import sys
from pathlib import Path


def build_langgraph_dev_args(project_root: Path) -> list[str]:
    venv_python = project_root / ".venv" / "bin" / "python3"
    return [
        venv_python.as_posix(),
        "-m",
        "langgraph_cli",
        "dev",
        "--port",
        "2030",
        "--host",
        "127.0.0.1",
    ]


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    args = build_langgraph_dev_args(base_dir)
    os.chdir(base_dir)
    os.execv(args[0], args)


if __name__ == "__main__":
    main()
