import os
import subprocess
import platform
import pytest
from unittest.mock import patch, MagicMock, ANY
from tools.lark_cli import lark_cli

@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(os.environ, {
        "FEISHU_APP_ID": "cli_mock_app",
        "FEISHU_APP_SECRET": "cli_mock_secret",
        "XHS_JWT_SECRET": "mock_jwt_secret"
    }):
        yield

def test_lark_cli_empty_command():
    # 测试空命令的情况
    assert "Error" in lark_cli.func("")
    assert "Error" in lark_cli.func("   ")

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_blacklist(mock_run):
    # auth 属于安全黑名单，应该直接拦截且不执行 subprocess
    res = lark_cli.func("auth status")
    assert "disallowed" in res
    mock_run.assert_not_called()


class _MockServerInfoWithoutIdentity:
    user = object()


class _MockConfigWithoutIdentity:
    server_info = _MockServerInfoWithoutIdentity()


@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_server_mode_without_identity_does_not_fallback_to_bot(mock_run):
    res = lark_cli.func("im +chat-list", config=_MockConfigWithoutIdentity())
    assert "Current server request has no Feishu user identity" in res
    mock_run.assert_not_called()

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_successful_run(mock_run):
    mock_resp = MagicMock()
    mock_resp.stdout = "User identity: ready"
    mock_resp.stderr = ""
    mock_resp.returncode = 0
    mock_run.return_value = mock_resp
    
    # 传入非黑名单命令
    res = lark_cli.func("im status")
    
    expected_bin = "lark-cli.cmd" if platform.system() == "Windows" else "lark-cli"
    
    # 校验调用参数：自动拼装，加上 --format json，且 shell=False
    mock_run.assert_called_once_with(
        [expected_bin, "im", "status", "--format", "json"],
        env=ANY,
        capture_output=True,
        text=True,
        timeout=45,
        shell=False
    )
    assert "User identity: ready" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_strip_prefix(mock_run):
    mock_resp = MagicMock()
    mock_resp.stdout = "Command run"
    mock_resp.stderr = ""
    mock_resp.returncode = 0
    mock_run.return_value = mock_resp
    
    # 传入带 lark-cli 前缀的命令，应该被正确裁剪，且 --format json 不重复追加
    res = lark_cli.func("lark-cli im +messages-send --chat-id 123 --format json")
    
    expected_bin = "lark-cli.cmd" if platform.system() == "Windows" else "lark-cli"
    
    mock_run.assert_called_once_with(
        [expected_bin, "im", "+messages-send", "--chat-id", "123", "--format", "json"],
        env=ANY,
        capture_output=True,
        text=True,
        timeout=45,
        shell=False
    )
    assert "Command run" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_exit_10_confirmation(mock_run):
    # 模拟 exit code 10 的安全确认
    mock_resp = MagicMock()
    mock_resp.returncode = 10
    mock_resp.stdout = ""
    mock_resp.stderr = "Write safety check failed"
    mock_run.return_value = mock_resp
    
    res = lark_cli.func("im +messages-send --chat-id 1", yes=False)
    assert "Human-in-the-Loop Required" in res
    assert "Write safety check failed" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_exit_10_approved(mock_run):
    mock_resp = MagicMock()
    mock_resp.returncode = 0
    mock_resp.stdout = "Message sent successfully"
    mock_resp.stderr = ""
    mock_run.return_value = mock_resp
    
    # yes=True 时应追加 --yes 并成功运行
    res = lark_cli.func("im +messages-send --chat-id 1", yes=True)
    
    expected_bin = "lark-cli.cmd" if platform.system() == "Windows" else "lark-cli"
    mock_run.assert_called_once_with(
        [expected_bin, "im", "+messages-send", "--chat-id", "1", "--yes", "--format", "json"],
        env=ANY,
        capture_output=True,
        text=True,
        timeout=45,
        shell=False
    )
    assert "Message sent successfully" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_exit_3_insufficient_scopes(mock_run):
    mock_resp = MagicMock()
    mock_resp.returncode = 3
    mock_resp.stderr = "Permission denied: scope missing"
    mock_run.return_value = mock_resp
    
    res = lark_cli.func("im status")
    assert "Feishu authorization scope insufficient" in res
    assert "Permission denied: scope missing" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_timeout(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(["lark-cli", "im"], timeout=45)
    res = lark_cli.func("im status")
    assert "timed out" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_generic_exception(mock_run):
    mock_run.side_effect = OSError("Binary not found")
    res = lark_cli.func("im status")
    assert "Error executing Lark CLI" in res
    assert "Binary not found" in res

def test_auto_update_lark_cli():
    with patch("threading.Thread") as mock_thread, \
         patch("tools.lark_cli.subprocess.run") as mock_run:
        
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        from tools.lark_cli import auto_update_lark_cli
        auto_update_lark_cli()
        
        mock_thread.assert_called_once()
        args, kwargs = mock_thread.call_args
        assert kwargs.get("daemon") is True
        mock_thread_instance.start.assert_called_once()

def test_run_lark_cli_update_success():
    from tools.lark_cli import _run_lark_cli_update
    with patch("tools.lark_cli.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "[OK] lark-cli is up to date"
        mock_run.return_value.stderr = ""
        
        _run_lark_cli_update()
        
        mock_run.assert_called_once_with(
            ["lark-cli", "update"],
            capture_output=True,
            text=True,
            timeout=60,
            shell=True
        )
