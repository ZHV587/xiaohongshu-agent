import subprocess
from unittest.mock import patch, MagicMock
from tools.lark_cli import lark_cli

def test_lark_cli_empty_command():
    # 测试空命令的情况
    assert "Error" in lark_cli.func("")
    assert "Error" in lark_cli.func("   ")

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_successful_run(mock_run):
    # 直接配置默认的 return_value 属性（注意下划线）
    mock_run.return_value.stdout = "User identity: ready"
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    # 传入不带前缀的命令
    res = lark_cli.func("auth status")
    
    # 校验调用参数：会自动拼装为 ['lark-cli', 'auth', 'status'] 并执行
    mock_run.assert_called_once_with(
        ["lark-cli", "auth", "status"],
        capture_output=True,
        text=True,
        timeout=45,
        shell=True
    )
    assert "User identity: ready" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_strip_prefix(mock_run):
    # 直接配置默认的 return_value 属性（注意下划线）
    mock_run.return_value.stdout = "Command run"
    mock_run.return_value.stderr = ""
    mock_run.return_value.returncode = 0
    
    # 传入带 lark-cli 前缀的命令，应该被正确裁剪
    res = lark_cli.func("lark-cli im +messages-send --chat-id 123")
    
    mock_run.assert_called_once_with(
        ["lark-cli", "im", "+messages-send", "--chat-id", "123"],
        capture_output=True,
        text=True,
        timeout=45,
        shell=True
    )
    assert "Command run" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_timeout(mock_run):
    # 模拟超时异常
    mock_run.side_effect = subprocess.TimeoutExpired(["lark-cli", "auth"], timeout=45)
    
    res = lark_cli.func("auth")
    
    assert "timed out" in res

@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_generic_exception(mock_run):
    # 模拟其他未知运行时异常
    mock_run.side_effect = OSError("Binary not found")
    
    res = lark_cli.func("auth")
    
    assert "Error executing Lark CLI" in res
    assert "Binary not found" in res

def test_auto_update_lark_cli():
    # 测试异步后台线程更新启动逻辑
    with patch("threading.Thread") as mock_thread, \
         patch("tools.lark_cli.subprocess.run") as mock_run:
        
        # Mock 线程实例
        mock_thread_instance = MagicMock()
        mock_thread.return_value = mock_thread_instance
        
        # 此时需要从 tools.lark_cli 导入 auto_update_lark_cli
        # 如果尚未定义，这里在运行测试时会抛出异常，符合 TDD 预期
        from tools.lark_cli import auto_update_lark_cli
        
        # 执行函数
        auto_update_lark_cli()
        
        # 验证 Thread 被实例化且 target 是某个 callable，daemon=True
        mock_thread.assert_called_once()
        args, kwargs = mock_thread.call_args
        assert kwargs.get("daemon") is True
        
        # 验证 start() 被调用
        mock_thread_instance.start.assert_called_once()

def test_run_lark_cli_update_success():
    # 测试后台更新函数本身的成功执行逻辑
    from tools.lark_cli import _run_lark_cli_update
    with patch("tools.lark_cli.subprocess.run") as mock_run:
        # Mock 成功执行
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "[OK] lark-cli 1.0.55 is already up to date\n"
        mock_run.return_value.stderr = ""
        
        _run_lark_cli_update()
        
        mock_run.assert_called_once_with(
            ["lark-cli", "update"],
            capture_output=True,
            text=True,
            timeout=60,
            shell=True
        )

