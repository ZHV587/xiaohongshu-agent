from __future__ import annotations

import asyncio
import os
import sys
import threading
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from tools.runtime_identity import actor_open_id_from_config


def _open_id_from_runtime(runtime: Any) -> str | None:
    """从 MCP 工具运行时取当前用户 open_id —— 只认 actor_open_id_from_config 的
    服务端可信来源(server_info / configurable.langgraph_auth_user)。

    绝不从 runtime.context 读 user_id/open_id/identity:context 来自 run 请求的
    context_schema,客户端可任意填写,信它等于让用户注入他人身份冒用其飞书 UAT(越权)。
    """
    return actor_open_id_from_config(getattr(runtime, "config", None))


async def inject_lark_mcp_identity(request: MCPToolCallRequest, handler):
    if request.name != "execute_lark_command":
        return await handler(request)

    # 先无条件剥掉客户端可能塞进 args 的 user_id(纵深防御:不依赖"无身份就原样转发"),
    # 再仅当解析到服务端可信身份时注入它。无可信身份则交由 server 端因缺 user_id 拒绝,
    # 绝不让客户端自带的 user_id 透传过去冒用他人飞书 UAT。
    safe_args = {k: v for k, v in request.args.items() if k != "user_id"}
    open_id = _open_id_from_runtime(request.runtime)
    if open_id:
        safe_args["user_id"] = open_id
    return await handler(request.override(args=safe_args))


def build_lark_mcp_client() -> MultiServerMCPClient:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_path = os.path.join(project_root, "lark_mcp_server.py")
    return MultiServerMCPClient(
        {
            "lark-cli": {
                "transport": "stdio",
                "command": sys.executable,
                "args": [server_path],
            }
        },
        tool_interceptors=[inject_lark_mcp_identity],
    )


def load_lark_mcp_tools():
    client = build_lark_mcp_client()
    result = []

    def run_in_thread():
        loop = asyncio.new_event_loop()
        try:
            result.append(loop.run_until_complete(client.get_tools()))
        finally:
            loop.close()

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()
    return result[0] if result else []
