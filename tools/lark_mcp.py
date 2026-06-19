from __future__ import annotations

import asyncio
import os
import sys
import threading
from collections.abc import Mapping
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest

from tools.runtime_identity import actor_open_id_from_config


def _open_id_from_runtime(runtime: Any) -> str | None:
    config = getattr(runtime, "config", None)
    open_id = actor_open_id_from_config(config)
    if open_id:
        return open_id

    context = getattr(runtime, "context", None)
    for attr in ("user_id", "open_id", "identity"):
        value = context.get(attr) if isinstance(context, Mapping) else getattr(context, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def inject_lark_mcp_identity(request: MCPToolCallRequest, handler):
    if request.name != "execute_lark_command":
        return await handler(request)

    open_id = _open_id_from_runtime(request.runtime)
    if not open_id:
        return await handler(request)

    modified = request.override(args={**request.args, "user_id": open_id})
    return await handler(modified)


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
