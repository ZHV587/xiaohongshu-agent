from __future__ import annotations

import importlib
import sys


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


def main() -> int:
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
