from __future__ import annotations

import importlib
import sys
from pathlib import Path


RUNTIME_MODULES = [
    "agent",
    "data_foundation.http_app",
    "deepagents",
    "langgraph",
    "langchain",
    "psycopg",
    "redis",
    "meilisearch",
    "falkordb",
]


def _ensure_repo_root_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    root = str(repo_root)
    if root not in sys.path:
        sys.path.insert(0, root)


def main() -> int:
    _ensure_repo_root_on_path()
    failed: list[str] = []
    for module_name in RUNTIME_MODULES:
        try:
            importlib.import_module(module_name)
        except Exception as exc:  # pragma: no cover - exercised in deployed images
            failed.append(f"{module_name}: {type(exc).__name__}: {exc}")
            print(f"{module_name}=FAIL", file=sys.stderr)
        else:
            print(f"{module_name}=OK")

    if failed:
        print("Runtime import smoke failed:", file=sys.stderr)
        for line in failed:
            print(f"- {line}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
