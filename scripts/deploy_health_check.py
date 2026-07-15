from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _request_json(url: str, headers: dict[str, str]) -> dict:
    request = Request(url, headers=headers, method="GET")
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _head_ok(url: str) -> int:
    request = Request(url, method="HEAD")
    with urlopen(request, timeout=20) as response:
        return response.status


def _module_status(value: object) -> object:
    if isinstance(value, dict):
        return value.get("status", value.get("state", value.get("ok")))
    return value


def check_health(base_url: str, env: dict[str, str]) -> bool:
    secret = env.get("XHS_INTERNAL_SECRET", "")
    admin_open_ids = env.get("XHS_ADMIN_OPEN_IDS", "")
    if not secret or not admin_open_ids:
        print("Missing XHS_INTERNAL_SECRET or XHS_ADMIN_OPEN_IDS.", file=sys.stderr)
        return False

    headers = {
        "X-XHS-Internal-Key": secret,
        "X-XHS-Open-Id": admin_open_ids.split(",")[0],
        "X-XHS-Is-Admin": "true",
    }
    health_url = base_url.rstrip("/") + "/internal/health/facts"
    data = _request_json(health_url, headers)

    modules = data.get("modules")
    if not isinstance(modules, dict):
        print("health.modules is missing or invalid.", file=sys.stderr)
        return False

    expected = {
        "startup": "running",
        "scheduler": "healthy",
        "database": "healthy",
    }
    ok = data.get("ok") is True
    print(f"ok={data.get('ok')}")
    for module_name, expected_status in expected.items():
        actual = _module_status(modules.get(module_name))
        print(f"module.{module_name}={actual}")
        ok = ok and actual == expected_status

    # A config-center deployment can report healthy infrastructure while its
    # process-local model registry is empty after a failed cold-start discovery.
    # In that state every chat request falls through to a stale import-time model,
    # so deployment must fail instead of producing a false-green handoff.
    model_url = base_url.rstrip("/") + "/internal/model/status"
    model_data = _request_json(model_url, headers)
    config_center_enabled = model_data.get("config_center_enabled") is True
    registry = model_data.get("registry")
    active_models = registry.get("active_models") if isinstance(registry, dict) else None
    last_error = registry.get("last_error") if isinstance(registry, dict) else None
    print(f"model.config_center_enabled={config_center_enabled}")
    print(f"model.active_count={len(active_models) if isinstance(active_models, list) else 0}")
    print(f"model.last_error_present={bool(last_error)}")
    if config_center_enabled:
        ok = ok and model_data.get("ok") is True and bool(active_models)

    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deployed XHS runtime health.")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--base-url")
    parser.add_argument("--public-url")
    args = parser.parse_args()

    env = os.environ.copy()
    env.update(_load_env_file(Path(args.env_file)))
    base_url = args.base_url or env.get("XHS_INTERNAL_BASE_URL") or "http://127.0.0.1:2030"

    try:
        healthy = check_health(base_url, env)
        if args.public_url:
            status = _head_ok(args.public_url)
            print(f"public_http_status={status}")
            healthy = healthy and 200 <= status < 400
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"Deployment health check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if not healthy:
        print("Deployment health check failed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
