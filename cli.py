"""1a 阶段命令行入口:流式跑 agent,验证读飞书→拆解→出选题/文案闭环。

用法:
    uv run python cli.py
    然后在提示符里输入方向,如「帮我按露营装备方向出选题」
    选题出来后输入「写第 2 个」继续,输入 exit 退出。
"""
import uuid

from langchain_core.messages import AIMessage, ToolMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from dotenv import load_dotenv
import json
from deepagents import (
    FilesystemPermission,
    HarnessProfileConfig,
    RubricMiddleware,
    create_deep_agent,
    register_harness_profile,
)

from backends import build_cli_backend
from middlewares import build_retry_middleware
from models import build_pool, build_primary_model, build_router_middleware
from prompts import MAIN_SYSTEM_PROMPT
from subagents import baokuan_analyst
import sys
import threading
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
import os

from tools.feishu_bitable import read_xhs_data
from tools.lark_cli import auto_update_lark_skills, auto_update_lark_cli

def get_lark_mcp_tools():
    """通过 stdio 传输动态连接本地的 lark-cli MCP 服务并获取工具。"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(current_dir, "lark_mcp_server.py")
    
    client = MultiServerMCPClient({
        "lark-cli": {
            "transport": "stdio",
            "command": sys.executable,
            "args": [server_path]
        }
    })
    
    result = []
    def run_in_thread():
        new_loop = asyncio.new_event_loop()
        try:
            res = new_loop.run_until_complete(client.get_tools())
            result.append(res)
        finally:
            new_loop.close()
            
    t = threading.Thread(target=run_in_thread)
    t.start()
    t.join()
    return result[0] if result else []

# 启动时自动从官方仓库同步最新的飞书技能（下载失败时自动静默降级，不影响启动）
auto_update_lark_skills()
auto_update_lark_cli()


load_dotenv()

# ── 安全加固(与 agent.py 保持一致)──────────────────────────────────
# 采用官方推荐的外部声明式配置文件进行初始化，彻底移除 Python 代码级硬编码配置
with open("deepagents_harness.json", "r", encoding="utf-8") as f:
    register_harness_profile("openai", HarnessProfileConfig.from_dict(json.load(f)))

# ── 高质量模型自主调度:构造模型池(与 agent.py 保持一致)──────────────
pool = build_pool()

# ── 文案质量评分(与 agent.py 保持一致)──────────────────────────────
rubric_middleware = RubricMiddleware(
    model=build_primary_model(pool),
    system_prompt="""你是小红书文案质量检查员。评估文案是否满足以下标准:
1. 标题有钩子,不平淡,能引起点击欲望
2. 正文像真人写的小红书笔记,无 AI 腔(不要"首先/其次/总之"、不要"在…领域"等八股)
3. 有 emoji 点缀但不过度
4. 标签 5~10 个且与内容相关
5. 选题和文案有数据依据,不是凭空编的
6. 文案有记忆点,读完能记住一两个关键信息

如果文案不满足以上标准,请给出具体修改建议。""",
    max_iterations=2,
)

agent = create_deep_agent(
    model=build_primary_model(pool),
    tools=[read_xhs_data] + get_lark_mcp_tools(),
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    backend=build_cli_backend(),
    middleware=[build_retry_middleware(), rubric_middleware, build_router_middleware(pool)],
    # CLI 单机无 user 身份,只挂团队共享记忆(走磁盘 backend,文件落项目目录)。
    # 个人隔离记忆依赖 server 注入的用户身份,CLI 不适用。
    memory=["/memories/team/AGENTS.md"],
    permissions=[
        FilesystemPermission(operations=["read"], paths=["/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/drafts/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/analysis/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/shared/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/memories/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ],
    name="xhs-content-agent",
)

console = Console()


def render(msg) -> None:
    """渲染一条消息:AI 文本、工具调用、工具结果。"""
    if isinstance(msg, AIMessage):
        content = msg.content
        if isinstance(content, list):
            content = "\n".join(
                p.get("text", "") for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            )
        if content and content.strip():
            console.print(Panel(Markdown(content), title="智能体", border_style="green"))
        for tc in getattr(msg, "tool_calls", []) or []:
            name = tc.get("name", "")
            if name == "task":
                console.print(f"  [magenta]>> 委派子智能体:[/] {tc.get('args', {}).get('description', '')[:60]}")
            elif name == "read_xhs_data":
                console.print("  [blue]>> 读取飞书爆款数据[/]")
            elif name == "write_file":
                console.print(f"  [yellow]>> 写文件:[/] {tc.get('args', {}).get('file_path', '')}")
    elif isinstance(msg, ToolMessage):
        name = getattr(msg, "name", "")
        if name == "read_xhs_data":
            console.print("  [green]✓ 已读取数据[/]")
        elif name == "task":
            console.print("  [green]✓ 子智能体分析完成[/]")


def main() -> None:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    console.print("[bold blue]小红书文案智能体 (1a CLI)[/]  输入方向开始,exit 退出\n")
    while True:
        try:
            user_input = console.input("[bold cyan]你> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue
        printed = 0
        try:
            for chunk in agent.stream(
                {"messages": [("user", user_input)]},
                config=config,
                stream_mode="values",
            ):
                msgs = chunk.get("messages", [])
                for m in msgs[printed:]:
                    render(m)
                printed = len(msgs)
        except Exception as e:
            console.print(f"[red]出错:[/] {e}")
    console.print("\n[dim]已退出[/]")


if __name__ == "__main__":
    main()
