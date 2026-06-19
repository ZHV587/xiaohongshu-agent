import os
import shlex
import subprocess
import urllib.request
import logging
import threading
import platform
import json
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from tools.uat_store import get_uat

logger = logging.getLogger(__name__)

def auto_update_lark_skills():
    """从飞书 CLI 官方仓库自动下载最新的 SKILL.md 文件并覆盖本地。
    支持超时和网络异常降级，不阻塞服务/命令行启动。
    """
    skills = ["lark-shared", "lark-im", "lark-base"]
    base_url = "https://raw.githubusercontent.com/larksuite/cli/main/skills/{}/SKILL.md"
    # tools/lark_cli.py 的父目录即项目根目录
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    for skill in skills:
        target_dir = os.path.join(project_root, ".agents", "skills", skill)
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, "SKILL.md")
        url = base_url.format(skill)
        try:
            # 使用 urllib 发起请求，设置 3 秒超时
            with urllib.request.urlopen(url, timeout=3.0) as response:
                content = response.read()
                if content:
                    existing_content = b""
                    if os.path.exists(target_file):
                        with open(target_file, "rb") as f:
                            existing_content = f.read()
                    if content != existing_content:
                        with open(target_file, "wb") as f:
                            f.write(content)
                        logger.info(f"Successfully auto-updated skill {skill} from GitHub.")
                    else:
                        logger.info(f"Skill {skill} is already up to date. Skipping write to prevent watchfiles reload.")
        except Exception as e:
            # 异常静默降级，使用本地缓存文件，不阻塞进程启动
            logger.warning(f"Failed to auto-update skill {skill} (using local cached file): {e}")

_IS_WINDOWS = platform.system() == "Windows"

# BLACKLIST of subcommands to prevent security tampering
_BLACKLIST_COMMANDS = {"auth", "config"}
_cli_lock = threading.RLock()

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

    # 1) Security block blacklist
    sub_cmd = args[0].lower()
    if sub_cmd in _BLACKLIST_COMMANDS:
        return f"Error: Command service '{sub_cmd}' is disallowed for security reasons."

    # 2) Identity resolution
    # Get user identity from runtime config
    server_info = getattr(config, "server_info", None) if config else None
    user = getattr(server_info, "user", None) if server_info else None
    open_id = getattr(user, "identity", None) if user else None
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
        if brand == "feishu":
            run_env["LARK_USER_ACCESS_TOKEN"] = token
            run_env["LARK_DEFAULT_AS"] = "user"
        else:
            run_env["LARKSUITE_CLI_USER_ACCESS_TOKEN"] = token
            run_env["LARKSUITE_CLI_DEFAULT_AS"] = "user"
        if "--as" not in clean_args:
            clean_args.extend(["--as", "user"])
    elif server_mode and not force_bot:
        return "Please authorize Feishu access first. Current server request has no Feishu user identity."
    else:
        # CLI fallback or forced bot
        app_id = os.environ.get("FEISHU_APP_ID")
        app_secret = os.environ.get("FEISHU_APP_SECRET")
        if not app_id or not app_secret:
            return "Error: Bot credentials (FEISHU_APP_ID/SECRET) not configured."
        if brand == "feishu":
            run_env["LARK_APP_ID"] = app_id
            run_env["LARK_APP_SECRET"] = app_secret
            run_env["LARK_DEFAULT_AS"] = "bot"
        else:
            run_env["LARKSUITE_CLI_APP_ID"] = app_id
            run_env["LARKSUITE_CLI_APP_SECRET"] = app_secret
            run_env["LARKSUITE_CLI_DEFAULT_AS"] = "bot"


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
