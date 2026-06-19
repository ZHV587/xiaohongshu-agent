# Phase 4 Native Tool Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛第四阶段前置边界：保留 MCP 官方工具接入能力，同时补齐用户身份透传、HITL/checkpointer、业务动作 Agent tool 化，并移除前端直连业务写操作。

**Architecture:** DeepAgents/LangGraph 继续是唯一 Agent runtime。Agent-facing 能力只能通过 `create_deep_agent(tools=...)` 接入的 LangChain tools 或 MCP tools 暴露；MCP tool 通过 `tool_interceptors` 注入当前用户身份；写飞书、发通知等高风险动作走 `interrupt_on + checkpointer`。Web 前端按钮不再直连 Python runner 执行业务写操作，而是把用户意图提交给 Agent 对话，由 Agent 调用受控工具。

**Tech Stack:** Python 3.12, DeepAgents 0.6.10, LangGraph, LangChain tools, langchain-mcp-adapters, FastMCP, pytest, Next.js/TypeScript, Vitest/tsc.

---

## Scope Check

第四阶段完整 spec 包含数据同步、outbox、embedding、图谱、创作记忆、效果反馈和运维闭环，范围过大，不应一次实施。这个计划只做 **Phase 4.0 官方扩展边界收敛**，为后续 Phase 4.1 同步闭环铺底。

本计划做：

1. MCP 保留为官方 tool 接入方式。
2. MCP tool 补用户身份透传路径。
3. `interrupt_on` 明确配合 checkpointer。
4. 飞书写草稿、群通知从前端直连 API 迁移为 Agent-facing tools。
5. 移除 `web_bridge_runner.py` 中的业务 action。
6. 加测试防止业务 CLI/runner 路径回潮。

本计划不做：

1. `sync_runs` 表。
2. scheduler/outbox worker。
3. embedding worker。
4. 图谱权重增强。
5. 创作记忆资源写入。
6. 效果反馈闭环。

## File Structure

- Modify: `agent.py`
  - 继续用 `create_deep_agent(...)` 装配。
  - MCP tools 仍可进入 `tools=[...]`。
  - 新增业务 tools。
  - 给写操作配置 `interrupt_on`。
  - 显式设置 `checkpointer=True`。

- Create: `tools/runtime_identity.py`
  - 提供测试友好的 runtime/config 身份读取与 mock config 构造。
  - 同时服务 LangChain tools、MCP interceptor、旧工具单测。

- Modify: `tools/lark_cli.py`
  - 保持 `@tool`。
  - 身份解析使用 `tools.runtime_identity.actor_open_id_from_config(...)`。
  - 继续禁止 `auth/config`。

- Modify: `lark_mcp_server.py`
  - `execute_lark_command` 增加 `user_id` 和 `yes` 参数。
  - MCP server 不自己读 LangGraph runtime，只接收 adapter/interceptor 注入的受控身份。

- Create: `tools/lark_mcp.py`
  - 构造 `MultiServerMCPClient`。
  - 定义 `tool_interceptors`，从 runtime/config/context 读取当前用户身份并注入 MCP tool args。
  - 封装 `load_lark_mcp_tools()`，替代 `agent.py` 内部线程函数。

- Create: `tools/feishu_actions.py`
  - 新增 Agent-facing LangChain tools：
    - `sync_copy_to_feishu`
    - `send_review_notification`
  - 底层复用 `lark_cli.func(...)` 和 `RunnableConfig`。

- Modify: `tools/web_bridge_runner.py`
  - 移除 `sync` 和 `notify` action。
  - 保留 `save-uat`、`uat-status`、`chats`、`config-status`、`config-set`、`wiki-space` 等平台桥接。

- Modify: `web/src/lib/server/internal-client.ts`
  - 移除 `/_internal/sync` 和 `/_internal/notify` 映射。

- Delete: `web/src/app/api/feishu/sync/route.ts`
  - 删除前端直连飞书写草稿 API。

- Delete: `web/src/app/api/feishu/notify/route.ts`
  - 删除前端直连飞书通知 API。

- Modify: `web/src/components/thread/index.tsx`
  - “同步至飞书多维表格”按钮改为提交 Agent 对话请求。
  - “群发通知”按钮改为提交 Agent 对话请求。

- Modify: `tests/test_lark_cli.py`
  - 使用 `runtime_identity` mock config。
  - 增加身份解析回归。

- Create: `tests/test_lark_mcp.py`
  - 测 MCP server tool 可接收 `user_id`。
  - 测 interceptor 会注入用户身份。

- Modify: `tests/test_agent_assembly.py`
  - 测新业务 tools 挂入 `create_deep_agent(tools=...)`。
  - 测 `interrupt_on` 覆盖写工具。
  - 测 checkpointer 已启用。

- Modify: `tests/test_web_only_runtime_entrypoint.py`
  - 测 web bridge 不再暴露 `sync/notify` business actions。
  - 测 internal-client 不再映射 `/_internal/sync`、`/_internal/notify`。

---

### Task 1: Add Shared Runtime Identity Helpers

**Files:**
- Create: `tools/runtime_identity.py`
- Test: `tests/test_lark_cli.py`

- [ ] **Step 1: Write failing tests for shared identity config**

Add these tests to `tests/test_lark_cli.py` near the existing mock config tests:

```python
def test_runtime_identity_config_exposes_open_id():
    from tools.runtime_identity import actor_open_id_from_config, identity_config

    config = identity_config("ou_test_user")

    assert actor_open_id_from_config(config) == "ou_test_user"


def test_runtime_identity_missing_identity_returns_none():
    from tools.runtime_identity import actor_open_id_from_config

    class _Config:
        server_info = object()

    assert actor_open_id_from_config(_Config()) is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_lark_cli.py::test_runtime_identity_config_exposes_open_id tests/test_lark_cli.py::test_runtime_identity_missing_identity_returns_none -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.runtime_identity'`.

- [ ] **Step 3: Create `tools/runtime_identity.py`**

Create the file with this content:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeUser:
    identity: str


@dataclass(frozen=True)
class RuntimeServerInfo:
    user: RuntimeUser


@dataclass(frozen=True)
class RuntimeIdentityConfig:
    server_info: RuntimeServerInfo


def identity_config(open_id: str) -> RuntimeIdentityConfig:
    return RuntimeIdentityConfig(server_info=RuntimeServerInfo(user=RuntimeUser(identity=open_id)))


def actor_open_id_from_config(config: Any | None) -> str | None:
    if config is None:
        return None

    server_info = getattr(config, "server_info", None)
    user = getattr(server_info, "user", None) if server_info is not None else None
    identity = getattr(user, "identity", None) if user is not None else None
    if isinstance(identity, str) and identity.strip():
        return identity.strip()

    if isinstance(config, dict):
        configurable = config.get("configurable") or {}
        identity = configurable.get("user_id") or configurable.get("open_id")
        if isinstance(identity, str) and identity.strip():
            return identity.strip()

    return None
```

- [ ] **Step 4: Run tests to verify pass**

Run:

```bash
uv run pytest tests/test_lark_cli.py::test_runtime_identity_config_exposes_open_id tests/test_lark_cli.py::test_runtime_identity_missing_identity_returns_none -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/runtime_identity.py tests/test_lark_cli.py
git commit -m "test: add runtime identity helper"
```

---

### Task 2: Make `lark_cli` Use Shared Identity Resolution

**Files:**
- Modify: `tools/lark_cli.py`
- Modify: `tools/web_bridge_runner.py`
- Test: `tests/test_lark_cli.py`

- [ ] **Step 1: Write failing test for user identity token injection**

Add this test to `tests/test_lark_cli.py`:

```python
@patch("tools.lark_cli.get_uat")
@patch("tools.lark_cli.subprocess.run")
def test_lark_cli_uses_runtime_identity_for_user_token(mock_run, mock_get_uat):
    from tools.runtime_identity import identity_config

    mock_get_uat.return_value = "uat-user-token"
    mock_resp = MagicMock()
    mock_resp.stdout = "{\"ok\": true}"
    mock_resp.stderr = ""
    mock_resp.returncode = 0
    mock_run.return_value = mock_resp

    res = lark_cli.func("im +chat-list", config=identity_config("ou_user_1"))

    assert "{\"ok\": true}" in res
    mock_get_uat.assert_called_once_with("ou_user_1")
    env = mock_run.call_args.kwargs["env"]
    assert env["LARK_USER_ACCESS_TOKEN"] == "uat-user-token"
    assert env["LARKSUITE_CLI_USER_ACCESS_TOKEN"] == "uat-user-token"
    assert env["LARK_DEFAULT_AS"] == "user"
    assert env["LARKSUITE_CLI_DEFAULT_AS"] == "user"
```

- [ ] **Step 2: Run test to verify current behavior**

Run:

```bash
uv run pytest tests/test_lark_cli.py::test_lark_cli_uses_runtime_identity_for_user_token -q
```

Expected: It may PASS with the current custom mock classes. If it passes, keep the test as a regression and continue; this task still removes duplicate mock identity code.

- [ ] **Step 3: Refactor `tools/lark_cli.py` identity parsing**

In `tools/lark_cli.py`, add this import:

```python
from tools.runtime_identity import actor_open_id_from_config
```

Replace the existing identity resolution block:

```python
    server_info = getattr(config, "server_info", None) if config else None
    user = getattr(server_info, "user", None) if server_info else None
    open_id = getattr(user, "identity", None) if user else None
    server_mode = server_info is not None
```

with:

```python
    server_info = getattr(config, "server_info", None) if config else None
    open_id = actor_open_id_from_config(config)
    server_mode = server_info is not None
```

- [ ] **Step 4: Refactor `tools/web_bridge_runner.py` mock identity**

In `tools/web_bridge_runner.py`, remove these classes:

```python
class MockUser:
    def __init__(self, identity):
        self.identity = identity

class MockServerInfo:
    def __init__(self, open_id):
        self.user = MockUser(open_id)

class MockConfig:
    def __init__(self, open_id):
        self.server_info = MockServerInfo(open_id)
```

Add this import:

```python
from tools.runtime_identity import identity_config
```

Replace each `MockConfig(open_id)` with:

```python
identity_config(open_id)
```

- [ ] **Step 5: Run focused tests**

Run:

```bash
uv run pytest tests/test_lark_cli.py tests/test_web_bridge_runner.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/lark_cli.py tools/web_bridge_runner.py tests/test_lark_cli.py
git commit -m "refactor: centralize runtime identity parsing"
```

---

### Task 3: Preserve MCP And Add Identity Injection Contract

**Files:**
- Create: `tools/lark_mcp.py`
- Modify: `lark_mcp_server.py`
- Modify: `agent.py`
- Test: `tests/test_lark_mcp.py`

- [ ] **Step 1: Write failing tests for MCP identity handling**

Create `tests/test_lark_mcp.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch


def test_mcp_server_execute_lark_command_accepts_user_id():
    import lark_mcp_server

    with patch("lark_mcp_server.lark_cli") as mock_tool:
        mock_tool.func.return_value = "ok"

        result = lark_mcp_server.execute_lark_command("im +chat-list", user_id="ou_mcp_user")

    assert result == "ok"
    config = mock_tool.func.call_args.kwargs["config"]
    assert config.server_info.user.identity == "ou_mcp_user"


def test_lark_mcp_identity_interceptor_injects_user_id():
    from tools.lark_mcp import inject_lark_mcp_identity

    request = MagicMock()
    request.name = "execute_lark_command"
    request.args = {"command": "im +chat-list"}
    request.runtime.config = {"configurable": {"user_id": "ou_runtime_user"}}
    modified = MagicMock()
    request.override.return_value = modified
    handler = AsyncMock(return_value="handled")

    import asyncio

    result = asyncio.run(inject_lark_mcp_identity(request, handler))

    assert result == "handled"
    request.override.assert_called_once_with(
        args={"command": "im +chat-list", "user_id": "ou_runtime_user"}
    )
    handler.assert_awaited_once_with(modified)
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_lark_mcp.py -q
```

Expected: FAIL because `tools.lark_mcp` does not exist and `execute_lark_command` does not accept `user_id`.

- [ ] **Step 3: Modify `lark_mcp_server.py`**

Replace the tool function with:

```python
@mcp.tool()
def execute_lark_command(command: str, yes: bool = False, user_id: str | None = None) -> str:
    """Execute a Lark/Feishu CLI command through the internal lark-cli adapter.

    Args:
        command: The lark-cli command string to execute.
        yes: Whether a previously approved write action should pass --yes.
        user_id: Current Feishu/LangGraph user identity injected by the MCP adapter.
    """
    config = identity_config(user_id) if user_id else None
    return lark_cli.func(command, yes=yes, config=config)
```

Add this import:

```python
from tools.runtime_identity import identity_config
```

- [ ] **Step 4: Create `tools/lark_mcp.py`**

Create the file with this content:

```python
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
    config = getattr(runtime, "config", None)
    open_id = actor_open_id_from_config(config)
    if open_id:
        return open_id

    context = getattr(runtime, "context", None)
    for attr in ("user_id", "open_id", "identity"):
        value = getattr(context, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def inject_lark_mcp_identity(request: MCPToolCallRequest, handler):
    if getattr(request, "name", "") != "execute_lark_command":
        return await handler(request)

    open_id = _open_id_from_runtime(getattr(request, "runtime", None))
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
```

- [ ] **Step 5: Modify `agent.py` to use the MCP loader**

Remove these imports from `agent.py`:

```python
import sys
import threading
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
```

Remove the `get_lark_mcp_tools()` function.

Add this import:

```python
from tools.lark_mcp import load_lark_mcp_tools
```

Replace:

```python
tools=[read_xhs_data, read_feishu_wiki] + phase3_tools + get_lark_mcp_tools(),
```

with:

```python
tools=[read_xhs_data, read_feishu_wiki] + phase3_tools + load_lark_mcp_tools(),
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_lark_mcp.py tests/test_agent_assembly.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add lark_mcp_server.py tools/lark_mcp.py agent.py tests/test_lark_mcp.py
git commit -m "feat: inject identity into lark mcp tools"
```

---

### Task 4: Add Agent-Facing Feishu Business Tools

**Files:**
- Create: `tools/feishu_actions.py`
- Modify: `agent.py`
- Test: `tests/test_feishu_actions.py`
- Modify: `tests/test_agent_assembly.py`

- [ ] **Step 1: Write failing tests for Feishu action tools**

Create `tests/test_feishu_actions.py`:

```python
import json
import os
from unittest.mock import patch

from tools.runtime_identity import identity_config


def test_sync_copy_to_feishu_requires_content(monkeypatch):
    from tools.feishu_actions import sync_copy_to_feishu

    result = sync_copy_to_feishu.func(title="", content="", config=identity_config("ou_user"))

    assert result["ok"] is False
    assert "title and content are required" in result["error"]


@patch("tools.feishu_actions.lark_cli")
def test_sync_copy_to_feishu_calls_lark_cli(mock_lark_cli, monkeypatch):
    from tools.feishu_actions import sync_copy_to_feishu

    monkeypatch.setenv("FEISHU_BITABLE_APP_TOKEN", "base_token")
    monkeypatch.setenv("FEISHU_BITABLE_TABLE_ID", "tbl_id")
    mock_lark_cli.func.return_value = json.dumps(
        {"code": 0, "data": {"record": {"record_id": "rec_1"}}},
        ensure_ascii=False,
    )

    result = sync_copy_to_feishu.func(
        title="标题",
        content="正文",
        tags="标签1,标签2",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    assert result["record_id"] == "rec_1"
    called_command = mock_lark_cli.func.call_args.args[0]
    assert "base +record-create" in called_command
    assert "--base-token base_token" in called_command
    assert "--table-id tbl_id" in called_command


@patch("tools.feishu_actions.lark_cli")
def test_send_review_notification_calls_lark_cli(mock_lark_cli):
    from tools.feishu_actions import send_review_notification

    mock_lark_cli.func.return_value = json.dumps({"code": 0}, ensure_ascii=False)

    result = send_review_notification.func(
        chat_id="oc_chat",
        title="标题",
        content="正文",
        config=identity_config("ou_user"),
    )

    assert result["ok"] is True
    called_command = mock_lark_cli.func.call_args.args[0]
    assert "im +messages-send" in called_command
    assert "--chat-id oc_chat" in called_command
    assert "--msg-type interactive" in called_command
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_feishu_actions.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.feishu_actions'`.

- [ ] **Step 3: Create `tools/feishu_actions.py`**

Create the file with this content:

```python
from __future__ import annotations

import json
import os
import shlex
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from tools.lark_cli import lark_cli


def _parse_lark_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": True, "raw": raw}
    if isinstance(data, dict) and data.get("code") not in (None, 0):
        return {"ok": False, "error": data.get("msg") or data.get("message") or "Lark API failed"}
    return {"ok": True, "data": data}


@tool
def sync_copy_to_feishu(
    title: str,
    content: str,
    tags: str | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Create a Feishu Base draft record for the generated Xiaohongshu copy."""
    if not title.strip() or not content.strip():
        return {"ok": False, "error": "title and content are required"}

    app_token = os.environ.get("FEISHU_BITABLE_APP_TOKEN")
    table_id = os.environ.get("FEISHU_BITABLE_TABLE_ID")
    if not app_token or not table_id:
        return {"ok": False, "error": "FEISHU_BITABLE_APP_TOKEN and FEISHU_BITABLE_TABLE_ID are required"}

    title_field = os.environ.get("XHS_BITABLE_FIELD_TITLE", "标题")
    body_field = os.environ.get("XHS_BITABLE_FIELD_BODY", "正文内容")
    tags_field = os.environ.get("XHS_BITABLE_FIELD_TAGS", "标签")
    author_field = os.environ.get("XHS_BITABLE_FIELD_AUTHOR", "创建人")
    status_field = os.environ.get("XHS_BITABLE_FIELD_STATUS", "状态")

    fields_payload: dict[str, Any] = {
        title_field: title,
        body_field: content,
        author_field: "agent",
        status_field: "草稿",
    }
    if tags:
        fields_payload[tags_field] = tags

    command = shlex.join(
        [
            "base",
            "+record-create",
            "--base-token",
            app_token,
            "--table-id",
            table_id,
            "--json",
            json.dumps({"fields": fields_payload}, ensure_ascii=False),
        ]
    )
    raw = lark_cli.func(command, config=config)
    parsed = _parse_lark_json(raw)
    if not parsed["ok"]:
        return parsed

    data = parsed.get("data") or {}
    record_id = (
        data.get("data", {}).get("record", {}).get("record_id")
        or data.get("data", {}).get("record_id")
        or ""
    )
    return {
        "ok": True,
        "record_id": record_id,
        "redirect_url": f"https://feishu.cn/base/{app_token}?table={table_id}",
    }


@tool
def send_review_notification(
    chat_id: str,
    title: str,
    content: str,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """Send a Feishu group card asking reviewers to check a generated draft."""
    if not chat_id.strip() or not title.strip() or not content.strip():
        return {"ok": False, "error": "chat_id, title and content are required"}

    card_content = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "小红书笔记待审核"},
            "template": "red",
        },
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**选题标题**：\\n{title}\\n\\n**笔记正文草稿**：\\n{content}",
                },
            },
            {
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": "请前往小红书智能体文案工作台确认发布。"}],
            },
        ],
    }

    command = shlex.join(
        [
            "im",
            "+messages-send",
            "--chat-id",
            chat_id,
            "--msg-type",
            "interactive",
            "--content",
            json.dumps(card_content, ensure_ascii=False),
        ]
    )
    parsed = _parse_lark_json(lark_cli.func(command, config=config))
    if not parsed["ok"]:
        return parsed
    return {"ok": True}


feishu_action_tools = [sync_copy_to_feishu, send_review_notification]
```

- [ ] **Step 4: Register tools in `agent.py`**

Add:

```python
from tools.feishu_actions import feishu_action_tools
```

Replace:

```python
tools=[read_xhs_data, read_feishu_wiki] + phase3_tools + load_lark_mcp_tools(),
```

with:

```python
tools=[read_xhs_data, read_feishu_wiki] + phase3_tools + feishu_action_tools + load_lark_mcp_tools(),
```

- [ ] **Step 5: Add assembly regression**

Append to `tests/test_agent_assembly.py`:

```python
def test_agent_registers_feishu_action_tools(monkeypatch):
    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")

    import importlib
    import agent as agent_module

    agent_module = importlib.reload(agent_module)
    tool_names = {getattr(tool, "name", "") for tool in agent_module.feishu_action_tools}

    assert {"sync_copy_to_feishu", "send_review_notification"} <= tool_names
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_feishu_actions.py tests/test_agent_assembly.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tools/feishu_actions.py agent.py tests/test_feishu_actions.py tests/test_agent_assembly.py
git commit -m "feat: add agent-facing feishu action tools"
```

---

### Task 5: Enforce HITL Checkpointer For Write Tools

**Files:**
- Modify: `agent.py`
- Modify: `tests/test_agent_assembly.py`

- [ ] **Step 1: Write failing assembly test for checkpointer and interrupts**

Append to `tests/test_agent_assembly.py`:

```python
def test_agent_write_tools_have_interrupts_and_checkpointer(monkeypatch):
    import importlib
    import deepagents

    captured = {}
    real_create = deepagents.create_deep_agent

    def _capturing_create_deep_agent(*args, **kwargs):
        captured.update(kwargs)
        return real_create(*args, **kwargs)

    _set_assembly_env(monkeypatch)
    monkeypatch.setenv("DISABLE_AUTO_UPDATE", "true")
    deepagents.create_deep_agent = _capturing_create_deep_agent
    try:
        import agent as agent_module
        importlib.reload(agent_module)
    finally:
        deepagents.create_deep_agent = real_create

    interrupts = captured["interrupt_on"]
    assert captured["checkpointer"] is True
    assert interrupts["execute_lark_command"] is True
    assert interrupts["sync_copy_to_feishu"] is True
    assert interrupts["send_review_notification"] is True
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_agent_assembly.py::test_agent_write_tools_have_interrupts_and_checkpointer -q
```

Expected: FAIL because `checkpointer` is not yet passed and new tools are not in `interrupt_on`.

- [ ] **Step 3: Modify `agent.py`**

Replace:

```python
interrupt_on={"execute_lark_command": True},
```

with:

```python
interrupt_on={
    "execute_lark_command": True,
    "sync_copy_to_feishu": True,
    "send_review_notification": True,
},
checkpointer=True,
```

- [ ] **Step 4: Run tests**

Run:

```bash
uv run pytest tests/test_agent_assembly.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent_assembly.py
git commit -m "feat: require hitl for feishu write tools"
```

---

### Task 6: Remove Direct Web Business Write Routes

**Files:**
- Delete: `web/src/app/api/feishu/sync/route.ts`
- Delete: `web/src/app/api/feishu/notify/route.ts`
- Modify: `web/src/lib/server/internal-client.ts`
- Modify: `tools/web_bridge_runner.py`
- Modify: `tests/test_web_only_runtime_entrypoint.py`

- [ ] **Step 1: Write failing regression tests**

Append to `tests/test_web_only_runtime_entrypoint.py`:

```python
def test_web_bridge_runner_no_business_write_actions():
    runner = (ROOT / "tools" / "web_bridge_runner.py").read_text(encoding="utf-8")

    assert '"sync"' not in runner
    assert '"notify"' not in runner
    assert "handle_sync" not in runner
    assert "handle_notify" not in runner


def test_internal_client_no_business_write_paths():
    internal_client = (ROOT / "web" / "src" / "lib" / "server" / "internal-client.ts").read_text(
        encoding="utf-8"
    )

    assert "/_internal/sync" not in internal_client
    assert "/_internal/notify" not in internal_client


def test_web_api_business_write_routes_removed():
    assert not (ROOT / "web" / "src" / "app" / "api" / "feishu" / "sync" / "route.ts").exists()
    assert not (ROOT / "web" / "src" / "app" / "api" / "feishu" / "notify" / "route.ts").exists()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
uv run pytest tests/test_web_only_runtime_entrypoint.py -q
```

Expected: FAIL because the direct routes and runner actions still exist.

- [ ] **Step 3: Delete direct route files**

Delete:

```text
web/src/app/api/feishu/sync/route.ts
web/src/app/api/feishu/notify/route.ts
```

- [ ] **Step 4: Remove mappings from `web/src/lib/server/internal-client.ts`**

Remove these branches:

```typescript
  if (pathName === "/_internal/sync") {
    action = "sync";
    const { title, content, tags, threadId } = extraBody || {};
    runnerArgs.push("--action", "sync", "--title", String(title), "--content", String(content));
    if (tags) runnerArgs.push("--tags", String(tags));
    if (threadId) runnerArgs.push("--thread-id", String(threadId));
  } else if (pathName === "/_internal/notify") {
    action = "notify";
    const { chatId, title, content } = extraBody || {};
    runnerArgs.push("--action", "notify", "--chat-id", String(chatId), "--title", String(title), "--content", String(content));
  } else if (pathName === "/_internal/chats") {
```

Replace the beginning of the chain with:

```typescript
  if (pathName === "/_internal/chats") {
```

- [ ] **Step 5: Remove business actions from `tools/web_bridge_runner.py`**

Delete the full `handle_sync` and `handle_notify` functions.

Change the parser choices from:

```python
choices=["save-uat", "uat-status", "chats", "sync", "notify", "config-status", "config-set", "wiki-space"],
```

to:

```python
choices=["save-uat", "uat-status", "chats", "config-status", "config-set", "wiki-space"],
```

Remove these dispatch branches:

```python
elif args.action == "sync":
    handle_sync(args)
elif args.action == "notify":
    handle_notify(args)
```

- [ ] **Step 6: Run tests**

Run:

```bash
uv run pytest tests/test_web_only_runtime_entrypoint.py tests/test_web_bridge_runner.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add tests/test_web_only_runtime_entrypoint.py web/src/lib/server/internal-client.ts tools/web_bridge_runner.py
git rm web/src/app/api/feishu/sync/route.ts web/src/app/api/feishu/notify/route.ts
git commit -m "refactor: remove direct feishu business write routes"
```

---

### Task 7: Route Frontend Buttons Through Agent Conversation

**Files:**
- Modify: `web/src/components/thread/index.tsx`
- Test: `web/src/components/thread/index.tsx` static check through pytest
- Modify: `tests/test_web_only_runtime_entrypoint.py`

- [ ] **Step 1: Add static regression test**

Append to `tests/test_web_only_runtime_entrypoint.py`:

```python
def test_thread_ui_submits_feishu_write_intent_to_agent():
    thread = (ROOT / "web" / "src" / "components" / "thread" / "index.tsx").read_text(
        encoding="utf-8"
    )

    assert 'fetch("/api/feishu/sync"' not in thread
    assert 'fetch("/api/feishu/notify"' not in thread
    assert "sync_copy_to_feishu" in thread
    assert "send_review_notification" in thread
```

- [ ] **Step 2: Run test to verify failure**

Run:

```bash
uv run pytest tests/test_web_only_runtime_entrypoint.py::test_thread_ui_submits_feishu_write_intent_to_agent -q
```

Expected: FAIL because the UI still fetches the direct API routes.

- [ ] **Step 3: Modify `handleSyncToFeishu`**

In `web/src/components/thread/index.tsx`, replace the `fetch("/api/feishu/sync", ...)` block inside `handleSyncToFeishu` with:

```typescript
          submitText(
            [
              "请调用 sync_copy_to_feishu 工具，把当前右侧文案保存为飞书多维表格草稿。",
              "这是一个写入动作，请先向我确认写入风险和目标表，再继续。",
              "",
              `标题：${draftTitle}`,
              "",
              `正文：${draftContent}`,
            ].join("\n")
          );
          setSyncStep(4);
          setLastSavedContent(draftContent);
          setLastSavedTitle(draftTitle);
          setIsDirty(false);
          toast.success("已发送给智能体处理，确认后将写入飞书多维表格。");
          setIsSyncing(false);
          setTimeout(() => {
            setSyncStepsVisible(false);
            setSyncStep(0);
          }, 4000);
```

Remove the old `.then(...)`, `.catch(...)`, and `.finally(...)` chain for `/api/feishu/sync`.

- [ ] **Step 4: Modify `handleSendNotification`**

Replace the `fetch("/api/feishu/notify", ...)` block with:

```typescript
    submitText(
      [
        "请调用 send_review_notification 工具，把当前文案发送到我选择的飞书群用于审核。",
        "这是一个外部发送动作，请先向我确认群聊、标题和正文摘要，再继续。",
        "",
        `chat_id：${selectedChatId}`,
        `标题：${draftTitle}`,
        "",
        `正文：${draftContent}`,
      ].join("\n")
    );
    toast.success("已发送给智能体处理，确认后将推送到飞书群聊。");
    setIsSendingNotification(false);
```

Remove the old `.then(...)`, `.catch(...)`, and `.finally(...)` chain for `/api/feishu/notify`.

- [ ] **Step 5: Run tests and typecheck**

Run:

```bash
uv run pytest tests/test_web_only_runtime_entrypoint.py -q
cd web && npm run lint -- src/components/thread/index.tsx && npx tsc --noEmit
```

Expected: pytest PASS; lint has no new errors; tsc PASS.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/thread/index.tsx tests/test_web_only_runtime_entrypoint.py
git commit -m "feat: route feishu write buttons through agent"
```

---

### Task 8: Full Regression And Documentation Update

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`

- [ ] **Step 1: Update README runtime boundary**

In `README.md`, update the runtime boundary bullets to include:

```markdown
- Feishu write actions are no longer called through frontend business APIs. The UI submits the user's intent to the LangGraph conversation, and the Agent executes write actions through registered LangChain tools or MCP tools with HITL.
- MCP is a supported official tool path. MCP tools that need user-specific credentials must receive identity through `tool_interceptors` or an equivalent adapter path.
```

- [ ] **Step 2: Update phase four spec status note**

In `docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md`, under the status block, change:

```markdown
- 状态：设计稿，等待用户 review
```

to:

```markdown
- 状态：设计稿，Phase 4.0 官方扩展边界收敛计划已完成
```

- [ ] **Step 3: Run full backend tests**

Run:

```bash
uv run pytest -q
```

Expected: all non-integration tests PASS; Postgres tests may skip if `TEST_XHS_DATABASE_URL` is absent.

- [ ] **Step 4: Run frontend checks**

Run:

```bash
cd web && npx tsc --noEmit && npm run lint -- src
```

Expected: tsc PASS; lint has no new errors. Existing warnings may remain.

- [ ] **Step 5: Run diff checks**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended files modified.

- [ ] **Step 6: Commit**

```bash
git add README.md docs/superpowers/specs/2026-06-19-phase-4-production-data-loop-design.md
git commit -m "docs: document native tool boundary runtime"
```

---

## Self-Review

**Spec coverage:**

- Official tools boundary: Tasks 3, 4, 5.
- MCP support: Task 3 keeps MCP and adds `tool_interceptors`.
- HITL/checkpointer: Task 5.
- Direct Web business writes removed: Tasks 6 and 7.
- No management backend: unchanged; tests prevent business API routes returning.
- No business CLI: Task 6 removes business actions from `web_bridge_runner.py`.

**Placeholder scan:**

- No unresolved placeholder markers.
- Each code-changing step includes concrete replacement code or exact deletion scope.

**Type consistency:**

- `identity_config(open_id)` returns an object compatible with current `lark_cli.func(..., config=...)`.
- MCP server accepts `user_id`; interceptor injects `user_id`.
- Write tools are named `sync_copy_to_feishu` and `send_review_notification` consistently across tests, agent assembly, UI prompts, and `interrupt_on`.

**Execution order:**

- Runtime identity helper first.
- MCP identity second.
- Business tools third.
- HITL/checkpointer after tool names exist.
- Direct route removal after replacement tools exist.
- UI reroute after direct API removal.
