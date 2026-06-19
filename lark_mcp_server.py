import os
import sys

# 将项目根目录加进 sys.path，保证可以正确导入 tools.lark_cli
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from tools.lark_cli import lark_cli
from tools.runtime_identity import identity_config

mcp = FastMCP("Lark CLI Server")

@mcp.tool()
def execute_lark_command(
    command: str, yes: bool = False, user_id: str | None = None
) -> str:
    """Execute a Lark/Feishu CLI command through the internal lark-cli adapter.

    Args:
        command: The lark-cli command string to execute.
        yes: Whether a previously approved write action should pass --yes.
        user_id: Current Feishu/LangGraph user identity injected by the MCP adapter.
    """
    if not user_id:
        return "Error: Current MCP tool request has no user identity."
    config = identity_config(user_id)
    return lark_cli.func(command, yes=yes, config=config)

if __name__ == "__main__":
    mcp.run()
