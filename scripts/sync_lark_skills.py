"""同步 lark skill 文件到与钉死的 lark-cli 二进制**同版**。

为什么是显式脚本而非运行时/build 时自动拉取:
- 运行时拉取写镜像烘焙路径(.agents/skills/),容器重建即丢 = no-op;且若拉 main
  会与钉死的 CLI 版本错配(skill 教的新语法旧 CLI 不认)。
- langgraph-cli 的 dockerfile_lines 恒在 `ADD .`(源码 COPY)之前执行,无法在 build 时
  覆盖随源码进镜像的 skill 文件,且无 post-copy 钩子。
- 故同步左移到源码层:本脚本拉取 → git diff 审阅 → commit → 随 `ADD .` 进镜像。
  CLI 与 skill 原子同版、可审计、可回滚。

版本权威源是 langgraph.json 里 lark-cli 二进制的 pin(单一事实源),不在本脚本重复维护;
升级 CLI 时改 langgraph.json 的 pin → 跑本脚本 → git diff → commit → rebuild。

用法:
    uv run python scripts/sync_lark_skills.py            # 跟随 langgraph.json 的 CLI pin
    uv run python scripts/sync_lark_skills.py --tag v1.2.0   # 显式覆盖(预演升级)
    uv run python scripts/sync_lark_skills.py --check    # 只检查是否漂移,不写盘(CI 用)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

# 与运行时一同烘焙进镜像的三个官方 lark skill(见 backends.py 的 /skills/ 路由)。
SKILLS = ("lark-shared", "lark-im", "lark-base")
RAW_URL = "https://raw.githubusercontent.com/larksuite/cli/{tag}/skills/{skill}/SKILL.md"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SKILLS_DIR = _PROJECT_ROOT / ".agents" / "skills"
_LANGGRAPH_JSON = _PROJECT_ROOT / "langgraph.json"

# 从 langgraph.json 的 lark-cli 二进制 URL 提取版本 tag,作为 skill 同步的默认版本。
# 形如 .../lark-cli/v1.0.58/lark-cli-1.0.58-linux-amd64.tar.gz
_CLI_PIN_RE = re.compile(r"lark-cli/(v[0-9][0-9A-Za-z.\-]*)/")


def cli_pinned_tag() -> str:
    """读 langgraph.json,返回 lark-cli 二进制钉死的版本 tag(如 'v1.0.58')。"""
    text = _LANGGRAPH_JSON.read_text(encoding="utf-8")
    match = _CLI_PIN_RE.search(text)
    if not match:
        raise SystemExit(
            "无法从 langgraph.json 解析 lark-cli 版本 pin;请检查 dockerfile_lines 里的二进制 URL。"
        )
    return match.group(1)


def fetch_skill(tag: str, skill: str, *, timeout: float = 15.0) -> bytes:
    url = RAW_URL.format(tag=tag, skill=skill)
    req = urllib.request.Request(url, headers={"User-Agent": "xhs-sync-lark-skills"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise SystemExit(f"拉取 {skill}@{tag} 失败:HTTP {resp.status} ({url})")
        content = resp.read()
    if not content.strip():
        raise SystemExit(f"拉取 {skill}@{tag} 得到空内容 ({url})")
    return content


def main() -> int:
    parser = argparse.ArgumentParser(description="同步 lark skill 到与 lark-cli 二进制同版")
    parser.add_argument(
        "--tag",
        default=None,
        help="显式指定 larksuite/cli 的 git tag;默认跟随 langgraph.json 的 CLI pin",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查本地 skill 是否与目标版本一致,不写盘;有漂移则非零退出(CI 用)",
    )
    args = parser.parse_args()

    tag = args.tag or cli_pinned_tag()
    print(f"目标版本 tag: {tag}  (来源: {'--tag' if args.tag else 'langgraph.json CLI pin'})")

    drifted: list[str] = []
    for skill in SKILLS:
        remote = fetch_skill(tag, skill)
        target = _SKILLS_DIR / skill / "SKILL.md"
        local = target.read_bytes() if target.exists() else b""

        if remote == local:
            print(f"  {skill}: 已是 {tag},跳过")
            continue

        drifted.append(skill)
        if args.check:
            print(f"  {skill}: 与 {tag} 不一致(--check 模式不写盘)", file=sys.stderr)
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(remote)
        print(f"  {skill}: 已更新到 {tag}")

    if args.check and drifted:
        print(f"\n漂移的 skill: {', '.join(drifted)};跑 `uv run python scripts/sync_lark_skills.py` 同步。", file=sys.stderr)
        return 1
    if not args.check and drifted:
        print(f"\n已同步 {len(drifted)} 个 skill 到 {tag}。请 `git diff .agents/skills/` 审阅后提交。")
    else:
        print(f"\n全部 skill 已与 {tag} 一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
