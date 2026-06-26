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


@pytest.fixture(autouse=True)
def skip_lark_config_provisioning():
    """命令执行类用例:置就绪标志跳过 config.json provisioning(真函数遇标志提前返回),
    避免额外 subprocess.run 干扰断言。_ensure_lark_config 自身的用例会自行复位标志。"""
    import tools.lark_cli as lc
    lc._lark_config_ready = True
    yield
    lc._lark_config_ready = False

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


def test_runtime_identity_config_exposes_open_id():
    from tools.runtime_identity import actor_open_id_from_config, identity_config

    config = identity_config("ou_test_user")

    assert actor_open_id_from_config(config) == "ou_test_user"


def test_runtime_identity_missing_identity_returns_none():
    from tools.runtime_identity import actor_open_id_from_config

    class _Config:
        server_info = object()

    assert actor_open_id_from_config(_Config()) is None


def test_runtime_identity_trusts_langgraph_auth_user_in_dict_config():
    """server 模式工具收 RunnableConfig(dict):身份取 configurable.langgraph_auth_user(可信)。"""
    from tools.runtime_identity import actor_open_id_from_config

    cfg = {"configurable": {"langgraph_auth_user": {"identity": "ou_trusted"}}}
    assert actor_open_id_from_config(cfg) == "ou_trusted"


def test_runtime_identity_ignores_client_supplied_user_id():
    """安全回归:configurable.user_id/open_id 是客户端 run 请求可伪造字段,必须忽略 ——
    否则可注入他人 open_id 经 get_uat 冒用其飞书令牌(越权)。"""
    from tools.runtime_identity import actor_open_id_from_config

    cfg = {"configurable": {"user_id": "ou_victim", "open_id": "ou_victim"}}
    assert actor_open_id_from_config(cfg) is None


@patch("tools.lark_cli.get_uat")
@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_uses_runtime_identity_for_user_token(mock_run, mock_get_uat):
    from tools.runtime_identity import identity_config

    mock_get_uat.return_value = "uat-user-token"
    mock_resp = MagicMock()
    mock_resp.stdout = "{\"ok\": true}"
    mock_resp.stderr = ""
    mock_resp.returncode = 0
    mock_run.return_value = mock_resp

    res = lark_cli.func("im +chat-list", config=identity_config("ou_user_1"))

    assert "{\"ok\": true}" in res
    mock_get_uat.assert_called_once_with("ou_user_1")
    env = mock_run.call_args.kwargs["env"]
    # v1.0.58:用户令牌走 LARKSUITE_CLI_ 前缀,且需同时带 app 凭证上下文
    assert env["LARKSUITE_CLI_USER_ACCESS_TOKEN"] == "uat-user-token"
    assert env["LARKSUITE_CLI_APP_ID"] == "cli_mock_app"
    assert env["LARKSUITE_CLI_APP_SECRET"] == "cli_mock_secret"
    # LARK_ 前缀被 v1.0.58 忽略,不再注入
    assert "LARK_USER_ACCESS_TOKEN" not in env
    # 命令追加 --as user
    cmd = mock_run.call_args.args[0]
    assert "--as" in cmd and cmd[cmd.index("--as") + 1] == "user"


@patch("tools.lark_cli.get_uat")
@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_bot_mode_uses_config_not_app_env(mock_run, mock_get_uat):
    """CLI 降级/无用户身份 → bot 分支:追加 --as bot,且不注入 LARK_APP_* 凭证 env。"""
    mock_resp = MagicMock()
    mock_resp.stdout = "{\"ok\": true, \"identity\": \"bot\"}"
    mock_resp.stderr = ""
    mock_resp.returncode = 0
    mock_run.return_value = mock_resp

    res = lark_cli.func("base +table-list --base-token V8xxx", config=None)

    assert "\"identity\": \"bot\"" in res
    mock_get_uat.assert_not_called()
    cmd = mock_run.call_args.args[0]
    assert "--as" in cmd and cmd[cmd.index("--as") + 1] == "bot"
    env = mock_run.call_args.kwargs["env"]
    assert "LARK_APP_ID" not in env
    assert "LARK_APP_SECRET" not in env


@patch("tools.lark_cli.subprocess.run")
def test_ensure_lark_config_runs_init_when_missing(mock_run):
    import tools.lark_cli as lc
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    lc._lark_config_ready = False
    try:
        with patch("tools.lark_cli.os.path.exists", return_value=False):
            lc._ensure_lark_config()
        assert mock_run.called
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[1:3] == ["config", "init"]
        assert "--app-secret-stdin" in cmd
        assert kwargs["input"] == "cli_mock_secret"  # secret 走 stdin,不进 argv
    finally:
        lc._lark_config_ready = False


@patch("tools.lark_cli.subprocess.run")
def test_ensure_lark_config_skips_when_present(mock_run):
    import tools.lark_cli as lc
    lc._lark_config_ready = False
    try:
        with patch("tools.lark_cli.os.path.exists", return_value=True):
            lc._ensure_lark_config()
        mock_run.assert_not_called()
    finally:
        lc._lark_config_ready = False


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
    
    # 校验调用参数：无用户身份 → bot fallback,追加 --as bot,再加 --format json,shell=False
    mock_run.assert_called_once_with(
        [expected_bin, "im", "status", "--as", "bot", "--format", "json"],
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
        [expected_bin, "im", "+messages-send", "--chat-id", "123", "--format", "json", "--as", "bot"],
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
        [expected_bin, "im", "+messages-send", "--chat-id", "1", "--as", "bot", "--yes", "--format", "json"],
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
