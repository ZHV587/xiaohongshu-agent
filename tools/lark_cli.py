import os
import shlex
import subprocess
import logging
import threading
import platform
import json
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from tools.runtime_identity import actor_open_id_from_config
from tools.uat_store import get_uat

logger = logging.getLogger(__name__)

# lark skill 文件(lark-base/im/shared)与 lark-cli 二进制一同在**镜像构建期**从
# larksuite/cli 的 v1.0.58 tag 拉取并烘焙进镜像(见 langgraph.json dockerfile_lines),
# 与钉死的 CLI 同版,绝不运行时自更新。运行时改写烘焙路径既违反不可变镜像(容器重建即丢)、
# 又会让 skill 漂移到与钉死 CLI 不配套的上游版本。升级走"改 langgraph.json 的版本 pin
# → langgraph build → docker compose up -d --build",CLI 与 skill 原子同升、可审计可回滚。

_IS_WINDOWS = platform.system() == "Windows"

# BLACKLIST of subcommands to prevent security tampering
_BLACKLIST_COMMANDS = {"auth", "config"}
_cli_lock = threading.RLock()

# lark-cli v1.0.58 的 app 身份(bot/user 都需要)从 ~/.lark-cli/config.json 读取,
# **不读** LARK_APP_ID/SECRET 环境变量。注入这两个 env 反而让 CLI 切到"环境凭证模式"、
# 期待现成 access token 而忽略 config → bot 取不到 token。故:用 FEISHU_APP_ID/SECRET
# 非交互生成 config.json,运行时只靠它 + 显式 --as,绝不注入 LARK_APP_* 凭证 env。
_lark_config_ready = False
_lark_config_lock = threading.Lock()


def _ensure_lark_config() -> None:
    """确保 ~/.lark-cli/config.json 存在(幂等)。无 app 凭证或已就绪则跳过。

    这是内部基础设施(非 agent 触发),直接调 lark-cli config init,绕过工具层黑名单。
    """
    global _lark_config_ready
    if _lark_config_ready:
        return
    with _lark_config_lock:
        if _lark_config_ready:
            return
        app_id = os.environ.get("FEISHU_APP_ID")
        app_secret = os.environ.get("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            return
        home = os.environ.get("HOME") or os.path.expanduser("~")
        config_path = os.path.join(home, ".lark-cli", "config.json")
        if os.path.exists(config_path):
            _lark_config_ready = True
            return
        executable = "lark-cli.cmd" if _IS_WINDOWS else "lark-cli"
        try:
            subprocess.run(
                [executable, "config", "init", "--app-id", app_id, "--app-secret-stdin", "--brand", "feishu"],
                input=app_secret,
                capture_output=True,
                text=True,
                timeout=30,
                shell=False,
            )
            _lark_config_ready = True
        except Exception as exc:  # noqa: BLE001 - 不阻断;后续命令会暴露真实错误
            logger.warning(f"lark-cli config init failed: {exc}")

_cached_brand = None

def get_lark_brand() -> str:
    """Detect whether lark-cli is configured to use 'feishu' or 'lark' brand.
    Prioritizes reading config file directly for speed, falls back to running lark-cli command.
    """
    import sys
    if "pytest" in sys.modules:
        return "feishu"

    global _cached_brand
    if _cached_brand is not None:
        return _cached_brand

    # Try reading the config file directly first
    config_paths = []
    userprofile = os.environ.get("USERPROFILE")
    if userprofile:
        config_paths.append(os.path.join(userprofile, ".lark-cli", "config.json"))
    home = os.environ.get("HOME")
    if home:
        config_paths.append(os.path.join(home, ".lark-cli", "config.json"))

    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    brand = data.get("brand")
                    if brand:
                        _cached_brand = brand.lower()
                        return _cached_brand
            except Exception:
                pass

    # Fallback to config show
    try:
        executable = "lark-cli.cmd" if platform.system() == "Windows" else "lark-cli"
        config_env = {}
        for k in ["PATH", "SystemRoot", "SystemDrive", "TEMP", "TMP", "USERPROFILE", "USERNAME", "HOME"]:
            if k in os.environ:
                config_env[k] = os.environ[k]
        result = subprocess.run(
            [executable, "config", "show"],
            env=config_env,
            capture_output=True,
            text=True,
            timeout=5,
            shell=False
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            brand = data.get("brand")
            if brand:
                _cached_brand = brand.lower()
                return _cached_brand
    except Exception:
        pass

    _cached_brand = "feishu"
    return _cached_brand


@tool
def lark_cli(command: str, yes: bool = False, config: RunnableConfig = None) -> str:
    """运行飞书官方命令行工具 (Lark Suite CLI) 的具体指令。

    你可以通过它操作飞书日历、即时通讯(发送消息)、云文档、多维表格等业务。
    注意：
    1. 传入参数 command 中不要包含 'lark-cli' 的前缀，只写具体服务 and 子命令。
    2. 对于写操作（例如发送消息、创建会议），需要用户二次确认。如果返回“需要确认”提示，
       你必须用自然语言向用户表述风险，在用户确认同意后，传入 `yes=True` 重新运行该指令。

    示例：
    - 发送消息: im +messages-send --chat-id "oc_xxx" --text "文案草稿已写好"
    """

    args = shlex.split(command.strip())
    if not args:
        return "Error: Command cannot be empty."

    if args[0] == "lark-cli":
        args = args[1:]

    if not args:
        return "Error: Command cannot be empty."

    # 1) Security block blacklist —— 位置无关的全 token 扫描。
    # 注意:不能只查 args[0]。lark_cli 在身份解析阶段会剥离 `--as <bot|user>`,
    # 攻击者可把命令写成 `--as bot auth logout`:此时 args[0]=="--as" 不在黑名单 → 放行,
    # 剥离后 clean_args==["auth","logout"] 却真的执行了 auth。任何 value-taking flag
    # (--as/--format/...)前缀都能这样把真正的服务子命令挤出 0 号位。故改为扫描所有 token:
    # 只要任一 token 命中黑名单即拒。合法飞书业务命令的服务名恒为 im/base/wiki/drive 等,
    # 绝不会是 auth/config;字段值经引号成单 token(如 --text "重新认证"),不会裸出 auth/config。
    for token in args:
        if token.lower() in _BLACKLIST_COMMANDS:
            return f"Error: Command service '{token.lower()}' is disallowed for security reasons."

    # 2) Identity resolution
    # Get user identity from runtime config
    server_info = getattr(config, "server_info", None) if config else None
    open_id = actor_open_id_from_config(config)
    server_mode = server_info is not None

    force_bot = False
    clean_args = []
    for arg in args:
        if arg == "--as" and "--as" in args:
            idx = args.index("--as")
            if idx + 1 < len(args) and args[idx + 1].lower() == "bot":
                force_bot = True
                continue
        if arg == "bot" and args[args.index(arg) - 1] == "--as":
            continue
        clean_args.append(arg)

    # Resolve token injection
    run_env = {
        "PATH": os.environ.get("PATH", ""),
        "LARKSUITE_CLI_CONTENT_SAFETY_MODE": "warn"
    }
    # Windows and Unix environment variables required by Node.js/lark-cli to locate home, temp, and system paths
    for k in ["SystemRoot", "SystemDrive", "TEMP", "TMP", "USERPROFILE", "USERNAME", "HOME"]:
        if k in os.environ:
            run_env[k] = os.environ[k]

    brand = get_lark_brand()

    if open_id and not force_bot:
        token = get_uat(open_id)
        if not token:
            return "Please authorize Feishu access first. Please log in again using the UI panel to grant permissions."

        # 用户身份(v1.0.58):经 env 注入用户令牌走 LARKSUITE_CLI_ 前缀(LARK_ 前缀被忽略),
        # 且 user-token 路径**要求**同时给 LARKSUITE_CLI_APP_ID/SECRET 提供 app 上下文
        # (缺则报 "blocked by env: ... APP_ID is missing")。与 bot 模式(纯 config.json、
        # 不带 app env)正好相反。
        app_id = os.environ.get("FEISHU_APP_ID")
        app_secret = os.environ.get("FEISHU_APP_SECRET")
        run_env["LARKSUITE_CLI_USER_ACCESS_TOKEN"] = token
        if app_id:
            run_env["LARKSUITE_CLI_APP_ID"] = app_id
        if app_secret:
            run_env["LARKSUITE_CLI_APP_SECRET"] = app_secret

        if "--as" not in clean_args:
            clean_args.extend(["--as", "user"])
    elif server_mode and not force_bot:
        return "Please authorize Feishu access first. Current server request has no Feishu user identity."
    else:
        # CLI 降级 / 强制 bot:app 身份完全由 config.json 提供(_ensure_lark_config 保证)。
        # **不注入任何 LARK_APP_* 凭证 env** —— 否则 v1.0.58 切到环境凭证模式、取不到 bot token。
        app_id = os.environ.get("FEISHU_APP_ID")
        app_secret = os.environ.get("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            return "Error: Bot credentials (FEISHU_APP_ID/SECRET) not configured."
        if "--as" not in clean_args:
            clean_args.extend(["--as", "bot"])


    # Append --yes parameter if approved by human
    if yes:
        clean_args.append("--yes")

    # Add output format options if metadata command is not run
    meta_cmds = {"--help", "schema", "--version", "-h"}
    has_meta = any(c in clean_args for c in meta_cmds)
    if not has_meta and "--format" not in clean_args:
        clean_args.extend(["--format", "json"])

    # 3) Execute process
    executable = "lark-cli"
    if _IS_WINDOWS:
        executable = "lark-cli.cmd"

    _ensure_lark_config()  # 保证 app 身份配置就绪(bot/user 共同前置)
    cmd = [executable] + clean_args

    with _cli_lock:

        try:
            result = subprocess.run(
                cmd,
                env=run_env,
                capture_output=True,
                text=True,
                timeout=45,
                shell=False
            )
        except subprocess.TimeoutExpired:
            return "Error: Command execution timed out after 45 seconds."
        except Exception as e:
            return f"Error executing Lark CLI command: {str(e)}"

    # 4) Handle exit codes
    if result.returncode == 10:
        # Safety confirmation required
        return (
            "⚠️ [Human-in-the-Loop Required]\n"
            "The requested command requires safety confirmation to execute. Details:\n"
            f"{result.stderr or result.stdout}\n"
            "Please explain the details and risks to the user. Once approved, call the lark_cli tool again with yes=True."
        )
    elif result.returncode == 3:
        # Insufficient scopes / permissions
        return f"Feishu authorization scope insufficient (Exit Code 3). Error message:\n{result.stderr or result.stdout}\nPlease log in to Feishu and grant permissions."
    elif result.returncode != 0:
        return f"Lark CLI command execution failed (Exit Code {result.returncode}):\n{result.stderr or result.stdout}"

    output = result.stdout
    if not output.strip():
        return "Command executed successfully."
    # Crop only if excessively large (e.g. > 10MB) to prevent context window blowup
    if len(output) > 10 * 1024 * 1024:
        return output[:10 * 1024 * 1024] + "\n... (truncated due to excessive size)"
    return output

