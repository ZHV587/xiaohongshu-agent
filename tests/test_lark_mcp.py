import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_mcp_adapters.interceptors import MCPToolCallRequest


def test_mcp_server_execute_lark_command_accepts_user_id():
    import lark_mcp_server

    with patch("lark_mcp_server.lark_cli") as mock_tool:
        mock_tool.func.return_value = "ok"

        result = lark_mcp_server.execute_lark_command(
            "im +chat-list", user_id="ou_mcp_user"
        )

    assert result == "ok"
    assert mock_tool.func.call_args.kwargs["yes"] is False
    config = mock_tool.func.call_args.kwargs["config"]
    assert config.server_info.user.identity == "ou_mcp_user"


def test_mcp_server_rejects_missing_user_id_without_bot_fallback():
    import lark_mcp_server

    with patch("lark_mcp_server.lark_cli") as mock_tool:
        result = lark_mcp_server.execute_lark_command("im +chat-list")

    assert "Current MCP tool request has no user identity" in result
    mock_tool.func.assert_not_called()


def test_lark_mcp_identity_interceptor_injects_user_id():
    from tools.lark_mcp import inject_lark_mcp_identity

    request = MCPToolCallRequest(
        name="execute_lark_command",
        args={"command": "im +chat-list"},
        server_name="lark-cli",
        runtime=SimpleNamespace(config={"configurable": {"user_id": "ou_runtime_user"}}),
    )
    handler = AsyncMock(return_value="handled")

    result = asyncio.run(inject_lark_mcp_identity(request, handler))

    assert result == "handled"
    handler.assert_awaited_once()
    modified = handler.await_args.args[0]
    assert modified is not request
    assert modified.args == {"command": "im +chat-list", "user_id": "ou_runtime_user"}
