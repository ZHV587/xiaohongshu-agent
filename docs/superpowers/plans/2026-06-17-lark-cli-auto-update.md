# lark-cli 自动更新 实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现飞书 CLI 命令行工具（lark-cli）在智能体启动时的后台异步自动更新。

**Architecture:** 在 `tools/lark_cli.py` 中提供一个名为 `auto_update_lark_cli()` 的接口。该接口启动一个独立的后台守护线程（daemon thread），并在该线程中通过子进程同步执行 `lark-cli update` 命令。捕获所有异常和超时（设置为 60 秒），以保证在弱网或离线环境下不拖慢或崩溃主程序。在 `agent.py` 与 `cli.py` 启动阶段调用该函数。

**Tech Stack:** Python standard libraries (`threading`, `subprocess`, `logging`), `pytest`.

---

### Task 1: 编写单元测试

**Files:**
- Modify: `tests/test_lark_cli.py`

- [x] **Step 1: 编写单元测试用例**
  
  在 [tests/test_lark_cli.py](file:///e:/小红书智能体/tests/test_lark_cli.py) 文件末尾添加以下测试，验证 `auto_update_lark_cli` 函数的行为：

  ```python
  from unittest.mock import patch, MagicMock
  from tools.lark_cli import auto_update_lark_cli

  def test_auto_update_lark_cli():
      with patch("threading.Thread") as mock_thread, \
           patch("subprocess.run") as mock_run:
          
          # Mock 线程启动
          mock_thread_instance = MagicMock()
          mock_thread.return_value = mock_thread_instance
          
          # 执行函数
          auto_update_lark_cli()
          
          # 验证 Thread 被实例化且 target 是 _run_lark_cli_update，且为守护线程
          mock_thread.assert_called_once()
          args, kwargs = mock_thread.call_args
          assert kwargs.get("daemon") is True
          
          # 验证线程被启动了
          mock_thread_instance.start.assert_called_once()

  def test_run_lark_cli_update_success():
      from tools.lark_cli import _run_lark_cli_update
      with patch("subprocess.run") as mock_run:
          mock_run.return_value = MagicMock(returncode=0, stdout="[OK] lark-cli is up to date\n", stderr="")
          
          # 执行后台更新逻辑本身
          _run_lark_cli_update()
          
          # 验证 subprocess 被正确调用
          mock_run.assert_called_once_with(
              ["lark-cli", "update"],
              capture_output=True,
              text=True,
              timeout=60,
              shell=True
          )
  ```

- [x] **Step 2: 运行测试以验证失败（TDD）**

  Run: `uv run pytest tests/test_lark_cli.py -k "auto_update_lark_cli" -v`
  Expected: FAIL (ImportError / NameError，因为 `auto_update_lark_cli` 和 `_run_lark_cli_update` 还没有在 `tools/lark_cli.py` 中定义)

---

### Task 2: 在 `tools/lark_cli.py` 中实现更新逻辑

**Files:**
- Modify: `tools/lark_cli.py`

- [x] **Step 1: 编写最小实现代码**

  在 [tools/lark_cli.py](file:///e:/小红书智能体/tools/lark_cli.py) 中添加后台自动更新相关的实现代码：

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

- [x] **Step 2: 运行测试并使其通过**

  Run: `uv run pytest tests/test_lark_cli.py -k "auto_update_lark" -v`
  Expected: PASS

- [x] **Step 3: 运行所有单元测试以确保无回归**

  Run: `uv run pytest`
  Expected: PASS (17 tests passed)

- [x] **Step 4: Commit**

  ```bash
  git add tests/test_lark_cli.py tools/lark_cli.py
  git commit -m "feat: add lark-cli auto update functionality and unit tests"
  ```

---

### Task 3: 在 `agent.py` 与 `cli.py` 中集成自动更新

**Files:**
- Modify: `agent.py`
- Modify: `cli.py`

- [x] **Step 1: 修改 `agent.py`**

  在 [agent.py](file:///e:/小红书智能体/agent.py) 中，将 `auto_update_lark_cli` 导入并在启动阶段调用：

  ```python
  # 修改导入
  from tools.lark_cli import lark_cli, auto_update_lark_skills, auto_update_lark_cli

  # 启动时自动从官方仓库同步最新的飞书技能和更新 CLI
  auto_update_lark_skills()
  auto_update_lark_cli()
  ```

- [x] **Step 2: 修改 `cli.py`**

  在 [cli.py](file:///e:/小红书智能体/cli.py) 中，将 `auto_update_lark_cli` 导入并在启动阶段调用：

  ```python
  # 修改导入
  from tools.lark_cli import lark_cli, auto_update_lark_skills, auto_update_lark_cli

  # 启动时自动从官方仓库同步最新的飞书技能和更新 CLI
  auto_update_lark_skills()
  auto_update_lark_cli()
  ```

- [x] **Step 3: 运行测试以确保启动逻辑未受影响**

  Run: `uv run pytest`
  Expected: PASS (17 tests passed)

- [x] **Step 4: Commit**

  ```bash
  git add agent.py cli.py
  git commit -m "feat: integrate auto_update_lark_cli in agent.py and cli.py startup"
  ```

---

### Task 4: 手动运行验证

**Files:**
- Verify: `cli.py`

- [x] **Step 1: 运行 CLI 交互终端**

  Run: `uv run python cli.py`
  Expected: 控制台正常启动且输出提示符 `你> `，控制台无报错。后台运行 `lark-cli update` 静默执行，可在一分钟内通过输入 `exit` 退出。
