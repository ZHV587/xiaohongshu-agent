import os

import pytest


HOST_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def clear_host_proxy_env() -> list[str]:
    """Remove host proxy variables so offline model tests stay machine-independent."""
    present_keys = set(os.environ)
    present_upper_keys = {key.upper() for key in present_keys}
    removed = [
        key for key in HOST_PROXY_ENV_VARS
        if key in present_keys or key.upper() in present_upper_keys
    ]
    for key in HOST_PROXY_ENV_VARS:
        os.environ.pop(key, None)
    return sorted(removed)


def normalize_no_proxy() -> None:
    """Fix httpx NO_PROXY parsing on Windows when IPv6 entries such as ::1 are present."""
    if "NO_PROXY" not in os.environ:
        return
    os.environ["NO_PROXY"] = ",".join(
        item for item in os.environ["NO_PROXY"].split(",")
        if ":" not in item
    )


def pytest_configure(config):
    normalize_no_proxy()
    clear_host_proxy_env()


@pytest.fixture(autouse=True)
def _isolate_host_proxy_env(monkeypatch):
    for key in HOST_PROXY_ENV_VARS:
        monkeypatch.delenv(key, raising=False)
