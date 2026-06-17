# lark-cli 自动更新设计

日期: 2026-06-17
状态: 待实现
作者: Antigravity

## 背景与目标

为了确保小红书文案智能体始终使用最新版飞书 CLI 命令行工具（npm 包 `@larksuite/cli`）和飞书 AI 技能包，避免因版本过期或接口变更导致飞书操作失败，我们需要在智能体启动时实现对 `lark-cli` 本身的自动更新机制。

---

## 方案设计

### 核心机制

在智能体服务 `agent.py` 或命令行调试入口 `cli.py` 启动时，开启一个**异步后台线程**静默执行更新动作：
1. **启动后台线程**：不阻塞主进程启动，避免拖慢 API 服务或 CLI 的加载速度。
2. **运行更新指令**：在子进程中执行 `lark-cli update`。该命令会自动检测远端 npm 版本，在有新版本时自动下载更新，同时更新本地官方技能。
3. **静默容错**：由于更新依赖网络，如果用户处于离线或弱网环境，更新会静默失败并记录警告日志，绝不抛出异常阻塞或崩溃主进程。

---

## 拟修改的文件

### 1. [tools/lark_cli.py](file:///e:/小红书智能体/tools/lark_cli.py)

- **新增** `auto_update_lark_cli()` 函数：
  - 启动一个守护线程（daemon thread）执行更新。
  - 在子进程中执行 `lark-cli update` 命令。
  - 设置超时时间（如 60 秒）防止卡死。
  - 捕获 `subprocess` 和 `Exception` 并写入日志。

```python
import threading

def _run_lark_cli_update():
    """在后台线程中执行 lark-cli update"""
    logger.info("Starting background check and update for lark-cli...")
    try:
        # 在 Windows 上使用 shell=True 保证能识别全局 npm 包装路径
        result = subprocess.run(
            ["lark-cli", "update"],
            capture_output=True,
            text=True,
            timeout=60,
            shell=True
        )
        if result.returncode == 0:
            logger.info(f"lark-cli background update completed: {result.stdout.strip()}")
        else:
            logger.warning(f"lark-cli background update returned non-zero code {result.returncode}: {result.stderr.strip()}")
    except subprocess.TimeoutExpired:
        logger.warning("lark-cli background update timed out after 60 seconds.")
    except Exception as e:
        logger.warning(f"Failed to auto-update lark-cli in background: {e}")

def auto_update_lark_cli():
    """启动后台守护线程自动更新 lark-cli"""
    thread = threading.Thread(target=_run_lark_cli_update, daemon=True)
    thread.start()
```

### 2. [agent.py](file:///e:/小红书智能体/agent.py)

- 在文件顶部导入 `auto_update_lark_cli` 并调用它：
  ```python
  from tools.lark_cli import lark_cli, auto_update_lark_skills, auto_update_lark_cli
  
  # 启动时自动从官方仓库同步最新的飞书技能和更新 CLI
  auto_update_lark_skills()
  auto_update_lark_cli()
  ```

### 3. [cli.py](file:///e:/小红书智能体/cli.py)

- 在文件顶部导入并调用 `auto_update_lark_cli`：
  ```python
  from tools.lark_cli import lark_cli, auto_update_lark_skills, auto_update_lark_cli
  
  # 启动时自动从官方仓库同步最新的飞书技能和更新 CLI
  auto_update_lark_skills()
  auto_update_lark_cli()
  ```

---

## 验证与测试方案

### 1. 单元测试 (`tests/test_lark_cli.py`)
- 编写测试用例 `test_auto_update_lark_cli_calls_subprocess`：
  - Mock `subprocess.run` 和 `threading.Thread`。
  - 验证调用 `auto_update_lark_cli()` 是否能正确启动线程并最终调用 `subprocess.run` 执行 `["lark-cli", "update"]`。

### 2. 手动联合验证
- 在终端运行 `uv run python cli.py`，观察控制台输出日志，确认自动更新线程被触发，且不会拖慢 CLI 的启动。
