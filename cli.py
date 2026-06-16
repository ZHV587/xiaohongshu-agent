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
from langchain.chat_models import init_chat_model
from deepagents import create_deep_agent

from backends import build_cli_backend
from middlewares import build_retry_middleware
from prompts import MAIN_MODEL, MAIN_SYSTEM_PROMPT
from subagents import baokuan_analyst
from tools.feishu_bitable import read_xhs_data

load_dotenv()

agent = create_deep_agent(
    model=init_chat_model(model=MAIN_MODEL, temperature=0.7, timeout=60, max_retries=4),
    tools=[read_xhs_data],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
    backend=build_cli_backend(),
    middleware=[build_retry_middleware()],
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
