import os

from tests.conftest import HOST_PROXY_ENV_VARS, clear_host_proxy_env, normalize_no_proxy


def test_clear_host_proxy_env_removes_upper_and_lowercase_proxy_vars(monkeypatch):
    for key in HOST_PROXY_ENV_VARS:
        monkeypatch.setenv(key, "socks5://127.0.0.1:7897")

    removed = clear_host_proxy_env()

    assert removed == sorted(HOST_PROXY_ENV_VARS)
    for key in HOST_PROXY_ENV_VARS:
        assert key not in os.environ


def test_normalize_no_proxy_removes_ipv6_entries_but_keeps_hostnames(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1,example.com")

    normalize_no_proxy()

    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,example.com"
