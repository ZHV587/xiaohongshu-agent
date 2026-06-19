import os
import sys

# 将项目根目录加进 sys.path，保证可以正确导入 tools.lark_cli
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from tools.lark_cli import lark_cli

mcp = FastMCP("Lark CLI Server")

@mcp.tool()
def execute_lark_command(command: str) -> str:
    """Execute a Lark/Feishu CLI command (e.g. 'im +messages-send', 'base +record-list')
    to read or write Lark/Feishu data.

    Args:
        command: The lark-cli command string to execute.
    """
    return lark_cli.func(command)

if __name__ == "__main__":
    mcp.run()
