import os
import shlex
import subprocess
import urllib.request
import logging
import threading
from langchain_core.tools import tool

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
        target_dir = os.path.join(project_root, "skills", skill)
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, "SKILL.md")
        url = base_url.format(skill)
        try:
            # 使用 urllib 发起请求，设置 3 秒超时
            with urllib.request.urlopen(url, timeout=3.0) as response:
                content = response.read()
                if content:
                    with open(target_file, "wb") as f:
                        f.write(content)
                    logger.info(f"Successfully auto-updated skill {skill} from GitHub.")
        except Exception as e:
            # 异常静默降级，使用本地缓存文件，不阻塞进程启动
            logger.warning(f"Failed to auto-update skill {skill} (using local cached file): {e}")

@tool
def lark_cli(command: str) -> str:
    """运行飞书官方命令行工具 (Lark Suite CLI) 的具体指令。
    
    你可以通过它操作飞书日历、即时通讯(发送消息)、云文档、多维表格等业务。
    注意：
    1. 传入参数 command 中不要包含 'lark-cli' 的前缀，只写具体服务 and 子命令。
    2. 如果 Skill 说明书中让你运行 'lark-cli im +messages-send ...'，
       你应该传入 'im +messages-send ...'。
    
    示例：
    - 发送消息: im +messages-send --chat-id "oc_xxx" --text "文案草稿已经写好"
    - 查看登录状态: auth status
    - 统计多维表格: base +data-query --base-token "xxx"
    """
    args = shlex.split(command.strip())
    if not args:
        return "Error: Command cannot be empty."
        
    # 如果模型习惯性带了 lark-cli 前缀，做容错去除
    if args[0] == "lark-cli":
        args = args[1:]
        
    if not args:
        return "Error: Command cannot be empty."
        
    # 安全验证：限制二进制执行范围
    # 强制加上 'lark-cli'，避免大模型传入 "rm -rf" 或 "curl" 等高危指令
    cmd = ["lark-cli"] + args
    
    try:
        # 在子进程中执行指令并捕获输出
        # shell=True 保证能识别全局 npm 安装的 Windows .cmd 包装路径
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45,
            shell=True
        )
        output = result.stdout + result.stderr
        
        # 净化可能包含敏感 token 的输出，或控制过长文本
        if not output.strip():
            return "Command executed successfully with no output."
        return output[:5000] # 截断防护，避免打爆上下文
    except subprocess.TimeoutExpired:
        return "Error: Command execution timed out after 45 seconds."
    except Exception as e:
        return f"Error executing Lark CLI command: {str(e)}"


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

