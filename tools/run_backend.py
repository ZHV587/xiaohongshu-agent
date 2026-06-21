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
        # 飞书工具(lark_cli)走同步 subprocess,已由 LangGraph 经线程池调度,不阻塞主
        # 事件循环。但 langgraph dev 的 blockbuster 会对同步 IO 过严误报(Blocking call
        # to os.read),导致 agent 运行时调 sync_feishu_resources / 飞书操作必然失败。
        # 关掉该开发期检测。生产 langgraph 部署不启用 blockbuster,无此问题。
        "--allow-blocking",
    ]


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    args = build_langgraph_dev_args(base_dir)
    os.chdir(base_dir)
    os.execv(args[0], args)


if __name__ == "__main__":
    main()
