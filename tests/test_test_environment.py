import os

from tests.conftest import HOST_PROXY_ENV_VARS, clear_host_proxy_env, normalize_no_proxy


def test_clear_host_proxy_env_removes_upper_and_lowercase_proxy_vars(monkeypatch):
    for key in HOST_PROXY_ENV_VARS:
        monkeypatch.setenv(key, "socks5://127.0.0.1:7897")

    removed = clear_host_proxy_env()

    assert {key.upper() for key in removed} == {"ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY"}
    for key in HOST_PROXY_ENV_VARS:
        assert key not in os.environ


def test_clear_host_proxy_env_reports_only_present_proxy_vars(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "socks5://127.0.0.1:7897")

    removed = clear_host_proxy_env()

    assert removed == ["HTTPS_PROXY"]
    assert "HTTPS_PROXY" not in os.environ


def test_normalize_no_proxy_removes_ipv6_entries_but_keeps_hostnames(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1,example.com")

    normalize_no_proxy()

    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,example.com"
