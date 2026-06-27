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


def test_lark_mcp_identity_interceptor_injects_trusted_user():
    """只注入服务端可信身份(configurable.langgraph_auth_user)。"""
    from tools.lark_mcp import inject_lark_mcp_identity

    request = MCPToolCallRequest(
        name="execute_lark_command",
        args={"command": "im +chat-list"},
        server_name="lark-cli",
        runtime=SimpleNamespace(
            config={"configurable": {"langgraph_auth_user": {"identity": "ou_trusted"}}}
        ),
    )
    handler = AsyncMock(return_value="handled")

    result = asyncio.run(inject_lark_mcp_identity(request, handler))

    assert result == "handled"
    handler.assert_awaited_once()
    modified = handler.await_args.args[0]
    assert modified is not request
    assert modified.args == {"command": "im +chat-list", "user_id": "ou_trusted"}


def test_lark_mcp_identity_interceptor_ignores_client_supplied_user_id():
    """安全回归:客户端在 run 请求里塞 configurable.user_id 不得被当作身份 ——
    否则可注入他人 open_id 冒用其飞书 UAT。无可信身份时不注入 user_id,
    原样转发(由 MCP server 端因缺身份拒绝)。"""
    from tools.lark_mcp import inject_lark_mcp_identity

    request = MCPToolCallRequest(
        name="execute_lark_command",
        args={"command": "im +chat-list"},
        server_name="lark-cli",
        runtime=SimpleNamespace(
            config={"configurable": {"user_id": "ou_victim", "open_id": "ou_victim"}},
            context={"user_id": "ou_victim", "open_id": "ou_victim", "identity": "ou_victim"},
        ),
    )
    handler = AsyncMock(return_value="handled")

    result = asyncio.run(inject_lark_mcp_identity(request, handler))

    assert result == "handled"
    handler.assert_awaited_once()
    forwarded = handler.await_args.args[0]
    # 未注入任何 user_id,且绝不出现受害者 open_id
    assert "user_id" not in forwarded.args
    assert "ou_victim" not in str(forwarded.args)


def test_lark_mcp_identity_interceptor_strips_client_user_id_in_args():
    """P2 安全回归:客户端把 user_id 直接塞进 args 时,无可信身份则必须剥掉,
    绝不原样透传(纵深防御:不依赖下游 server 拒绝)。"""
    from tools.lark_mcp import inject_lark_mcp_identity

    request = MCPToolCallRequest(
        name="execute_lark_command",
        args={"command": "im +chat-list", "user_id": "ou_victim"},  # 客户端注入 args
        server_name="lark-cli",
        runtime=SimpleNamespace(config={}),  # 无可信身份
    )
    handler = AsyncMock(return_value="handled")

    asyncio.run(inject_lark_mcp_identity(request, handler))

    forwarded = handler.await_args.args[0]
    assert "user_id" not in forwarded.args
    assert "ou_victim" not in str(forwarded.args)


def test_lark_mcp_identity_interceptor_overrides_client_user_id_in_args():
    """有可信身份时:客户端注入的 args.user_id 被可信身份覆盖,而非取客户端值。"""
    from tools.lark_mcp import inject_lark_mcp_identity

    request = MCPToolCallRequest(
        name="execute_lark_command",
        args={"command": "im +chat-list", "user_id": "ou_victim"},
        server_name="lark-cli",
        runtime=SimpleNamespace(
            config={"configurable": {"langgraph_auth_user": {"identity": "ou_trusted"}}}
        ),
    )
    handler = AsyncMock(return_value="handled")

    asyncio.run(inject_lark_mcp_identity(request, handler))

    forwarded = handler.await_args.args[0]
    assert forwarded.args["user_id"] == "ou_trusted"
    assert "ou_victim" not in str(forwarded.args)
