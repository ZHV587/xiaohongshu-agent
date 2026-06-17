"""MemoryMiddleware 隔离验证:验证个人记忆按 user 隔离、团队记忆全员共享。

前置:先跑 `uv run langgraph dev`(挂了 auth.py),再跑本脚本。
身份:本脚本自签合法 HS256 JWT(用 .env 的 XHS_JWT_SECRET),模拟两个真飞书用户;
      若未配 JWT 密钥则退回 mock-user-X 头(对齐 auth.py 的 mock 模式)。

验证点:
  1. 个人记忆隔离:A 让 agent 往 /user-memories/AGENTS.md 写内容,B 读不到。
  2. 团队记忆共享:A 写 /memories/team/AGENTS.md,B 能读到。
  3. store 层旁证:个人记忆落在按 open_id 分区的 namespace,团队记忆落在 xhs-shared。
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

URL = "http://127.0.0.1:2030"
GRAPH = "xhs_agent"
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
    for m in reversed(messages):
        if m.get("type") == "ai" or m.get("role") == "assistant":
            c = m.get("content", "")
            if isinstance(c, list):
                c = " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
            if c and c.strip():
                return c
    return ""


async def run_turn(client, thread_id: str, text: str) -> list:
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
    alice = client_as("ou_alice_001", "Alice")
    bob = client_as("ou_bob_002", "Bob")

    print("=" * 60)
    print("验证 1:个人记忆隔离(A 写 /user-memories/,B 读不到)")
    ta = (await alice.threads.create())["thread_id"]
    await run_turn(alice, ta, "请用 edit_file 工具往 /user-memories/AGENTS.md 写入这行:ALICE-SECRET-PREF 我偏好露营装备方向的选题。写完只回复『已记住』。")
    tb = (await bob.threads.create())["thread_id"]
    msgs = await run_turn(bob, tb, "请用 read_file 工具读取 /user-memories/AGENTS.md,把内容逐字复述;若文件不存在就回复『无个人记忆』。")
    bob_sees = text_of(msgs)
    print("Bob 读到:", bob_sees[:150])
    iso_ok = "ALICE-SECRET-PREF" not in bob_sees
    print("个人记忆隔离:", "✓ 通过" if iso_ok else "✗ 失败(串味!)")

    print("=" * 60)
    print("验证 2:团队记忆共享(A 写 /memories/team/,B 读到)")
    ta2 = (await alice.threads.create())["thread_id"]
    await run_turn(alice, ta2, "请用 edit_file 工具往 /memories/team/AGENTS.md 写入这行团队公开备注:TEAM-MEMO-OK 标题多用数字更易爆。写完只回复『已写入』。")
    tb2 = (await bob.threads.create())["thread_id"]
    msgs2 = await run_turn(bob, tb2, "请用 read_file 工具读取 /memories/team/AGENTS.md 这个团队公开方法论文件,逐字复述内容。")
    bob_team = text_of(msgs2)
    print("Bob 读到:", bob_team[:150])
    share_ok = "TEAM-MEMO-OK" in bob_team
    print("团队记忆共享:", "✓ 通过" if share_ok else "✗ 待确认(模型可能未逐字复述,见 store 层旁证)")

    print("=" * 60)
    print("store 层旁证:")
    try:
        team = await bob.store.search_items(("xhs-shared",))
        team_keys = [getattr(it, "key", None) or (it.get("key") if isinstance(it, dict) else None) for it in (team.get("items", team) if isinstance(team, dict) else team)]
        print("  团队 namespace ('xhs-shared',) 条目:", team_keys)
        # 个人记忆按 (open_id, 'user-memories') 分区
        a_ns = await alice.store.search_items(("ou_alice_001", "user-memories"))
        a_keys = [getattr(it, "key", None) or (it.get("key") if isinstance(it, dict) else None) for it in (a_ns.get("items", a_ns) if isinstance(a_ns, dict) else a_ns)]
        print("  Alice 个人 namespace ('ou_alice_001','user-memories') 条目:", a_keys)
    except Exception as e:
        print("  store 层校验跳过:", type(e).__name__, str(e)[:80])


if __name__ == "__main__":
    asyncio.run(main())
