"""1b-1 联调验证:连本地 langgraph dev server,验证跨轮记忆 / /shared 共享 / /drafts 隔离。

前置:另开一个终端先跑 `uv run langgraph dev`(默认 http://127.0.0.1:2024),
再在本终端跑 `uv run python verify_1b1.py`。
"""
import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from langgraph_sdk import get_client

load_dotenv(Path(__file__).resolve().parent / ".env")

URL = "http://127.0.0.1:2024"
GRAPH = "xhs_agent"  # 对应 langgraph.json 里的 graph 名
_JWT_SECRET = os.environ.get("XHS_JWT_SECRET", "")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _make_jwt(sub: str, name: str) -> str:
    """用 XHS_JWT_SECRET 签一个合法 HS256 JWT(对齐 auth.py 的验签)。"""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url(json.dumps({"sub": sub, "name": name, "exp": int(time.time()) + 3600}).encode())
    sig = _b64url(hmac.new(_JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def client_as(sub: str, name: str):
    """带身份头的客户端:配了密钥用真 JWT,否则退回 mock 头。"""
    token = _make_jwt(sub, name) if _JWT_SECRET else f"mock-user-{sub}"
    return get_client(url=URL, headers={"Authorization": f"Bearer {token}"})


def text_of(messages: list) -> str:
    """取最后一条 assistant 文本。"""
    for m in reversed(messages):
        if m.get("type") == "ai" or m.get("role") == "assistant":
            c = m.get("content", "")
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
            if c and c.strip():
                return c
    return ""


async def run_turn(client, thread_id: str, text: str) -> list:
    """在指定 thread 上跑一轮,返回完整 messages。"""
    final = None
    async for chunk in client.runs.stream(
        thread_id, GRAPH,
        input={"messages": [{"role": "user", "content": text}]},
        stream_mode="values",
    ):
        if chunk.event == "values" and isinstance(chunk.data, dict) and "messages" in chunk.data:
            final = chunk.data["messages"]
    return final or []


async def main():
    client = client_as("ou_alice_001", "Alice")

    print("=" * 60)
    print("验证 1:跨轮记忆(同一 thread 两轮)")
    t1 = (await client.threads.create())["thread_id"]
    await run_turn(client, t1, "请记住一个暗号:菠萝啤。只需回复『记住了』。")
    msgs = await run_turn(client, t1, "我刚才让你记的暗号是什么?")
    ans = text_of(msgs)
    print("第二轮回答:", ans[:120])
    print("跨轮记忆:", "✓ 通过" if "菠萝啤" in ans else "✗ 失败(没记住)")

    print("=" * 60)
    print("验证 2:/shared 共享(thread A 写,thread B 读)")
    tA = (await client.threads.create())["thread_id"]
    await run_turn(client, tA, "用 write_file 往 /shared/probe.md 写入一行内容:SHARED-OK-标记。写完回复『已写入』。")
    tB = (await client.threads.create())["thread_id"]
    msgs = await run_turn(client, tB, "用 read_file 读取 /shared/probe.md,把里面的内容原样告诉我。")
    ans = text_of(msgs)
    print("thread B 读到:", ans[:120])
    print("/shared 共享:", "✓ 通过" if "SHARED-OK" in ans else "✗ 失败(B 读不到 A 写的)")

    print("=" * 60)
    print("验证 3:/drafts 隔离(thread A 写,thread B 读不到)")
    tA2 = (await client.threads.create())["thread_id"]
    await run_turn(client, tA2, "用 write_file 往 /drafts/secret.md 写入:DRAFT-A-ONLY。写完回复『已写入』。")
    tB2 = (await client.threads.create())["thread_id"]
    msgs = await run_turn(client, tB2, "用 read_file 尝试读取 /drafts/secret.md,告诉我读到了什么或是否不存在。")
    ans = text_of(msgs)
    print("thread B 尝试读:", ans[:150])
    print("/drafts 隔离:", "✓ 通过" if "DRAFT-A-ONLY" not in ans else "✗ 失败(B 读到了 A 的草稿)")


if __name__ == "__main__":
    asyncio.run(main())
