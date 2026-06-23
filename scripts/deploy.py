from __future__ import annotations

import os
import sys
from collections.abc import Iterable

import paramiko


HOSTNAME = os.environ.get("XHS_DEPLOY_HOST", "124.221.173.80")
USERNAME = os.environ.get("XHS_DEPLOY_USER", "ubuntu")
KEY_PATH = os.path.expanduser(os.environ.get("XHS_DEPLOY_KEY", "~/.ssh/xhs_deploy"))
PROJECT_DIR = os.environ.get("XHS_DEPLOY_PROJECT_DIR", "/home/ubuntu/xiaohongshu-agent")


def _in_project(command: str) -> str:
    return f"cd {PROJECT_DIR} && {command}"


def deployment_commands() -> list[str]:
    return [
        _in_project("git pull --ff-only origin master"),
        _in_project("/home/ubuntu/.local/bin/langgraph build -t xhs-langgraph:latest"),
        _in_project("docker compose up -d --build"),
        _in_project(
            "for i in $(seq 1 30); do "
            "status=$(docker inspect -f '{{.State.Health.Status}}' xhs-langgraph 2>/dev/null || echo missing); "
            'echo "xhs-langgraph health: $status"; '
            '[ "$status" = healthy ] && exit 0; '
            "sleep 2; "
            "done; "
            "docker compose ps; "
            "exit 1"
        ),
        _in_project("docker compose ps"),
        _in_project("docker compose exec -T langgraph python scripts/runtime_import_smoke.py"),
        _in_project("python3 scripts/deploy_health_check.py --public-url http://127.0.0.1:9091/"),
    ]


def execute_commands(ssh: paramiko.SSHClient, commands: Iterable[str]) -> int:
    for cmd in commands:
        print(f"\nExecuting: {cmd}")
        _stdin, stdout, stderr = ssh.exec_command(cmd)

        for line in stdout:
            print(line, end="")
        for line in stderr:
            print(line, end="", file=sys.stderr)

        status = stdout.channel.recv_exit_status()
        print(f"\nExit code: {status}")
        if status != 0:
            print("Command failed. Aborting deployment.", file=sys.stderr)
            return status

    return 0


def connect() -> paramiko.SSHClient:
    if not os.path.exists(KEY_PATH):
        print(f"找不到部署私钥: {KEY_PATH}", file=sys.stderr)
        print("请设置 XHS_DEPLOY_KEY 指向正确的私钥文件。", file=sys.stderr)
        sys.exit(1)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {HOSTNAME} via SSH key ...")
    ssh.connect(HOSTNAME, username=USERNAME, key_filename=KEY_PATH, timeout=15)
    print("Connected successfully.")
    return ssh


def main() -> int:
    try:
        ssh = connect()
    except Exception as exc:
        print(f"Failed to connect: {exc}", file=sys.stderr)
        return 1

    try:
        return execute_commands(ssh, deployment_commands())
    finally:
        ssh.close()


if __name__ == "__main__":
    raise SystemExit(main())
