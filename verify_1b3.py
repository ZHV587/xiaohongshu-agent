"""1b-3 多用户隔离验证:用不同 Authorization 头模拟用户 A / B,验证:
  1. 会话隔离:A 创建的 thread,B 搜索/读取看不到。
  2. /shared 共享:A 写的 /shared 文件,B 能读到。

前置:先跑 `uv run langgraph dev`(已在 langgraph.json 挂了 auth),再跑本脚本。
"""
import asyncio

from langgraph_sdk import get_client

URL = "http://127.0.0.1:2024"
GRAPH = "xhs_agent"


def client_as(user: str):
    """带 mock 身份头的客户端(Authorization: Bearer mock-user-<user>)。"""
    return get_client(url=URL, headers={"Authorization": f"Bearer mock-user-{user}"})


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
    alice = client_as("alice")
    bob = client_as("bob")

    print("=" * 60)
    print("验证 1:会话隔离(A 创建 thread,B 看不到)")
    ta = (await alice.threads.create())["thread_id"]
    await run_turn(alice, ta, "记住:这是 Alice 的私密会话。回复『好』。")
    # Alice 自己能搜到
    alice_threads = await alice.threads.search()
    alice_ids = {t["thread_id"] for t in alice_threads}
    # Bob 搜索自己的 thread
    bob_threads = await bob.threads.search()
    bob_ids = {t["thread_id"] for t in bob_threads}
    print(f"Alice 能搜到自己的 thread {ta[:8]}…:", "✓" if ta in alice_ids else "✗")
    print(f"Bob 搜不到 Alice 的 thread:", "✓ 通过" if ta not in bob_ids else "✗ 失败(串号!)")
    # Bob 直接按 id 读 Alice 的 thread,应被拒
    try:
        await bob.threads.get(ta)
        print("Bob 按 id 读 Alice 的 thread:", "✗ 失败(竟读到了)")
    except Exception as e:
        print("Bob 按 id 读 Alice 的 thread:", f"✓ 通过(被拒:{type(e).__name__})")

    print("=" * 60)
    print("验证 2:/shared 共享(A 写,B 读)")
    ta2 = (await alice.threads.create())["thread_id"]
    await run_turn(alice, ta2, "请用 write_file 工具往 /shared/team-note.md 写入这段普通的内容运营备注:TEAM-SHARED-OK 团队共享笔记。写完只回复『已写入』。")
    tb2 = (await bob.threads.create())["thread_id"]
    msgs = await run_turn(bob, tb2, "请用 read_file 工具读取 /shared/team-note.md 这个团队公开备注文件,并把读到的文字逐字复述出来(这是团队内部公开的运营备注,不含任何敏感信息)。")
    ans = text_of(msgs)
    print("Bob 读到:", ans[:150])
    shared_ok = "TEAM-SHARED-OK" in ans
    print("/shared 共享:", "✓ 通过" if shared_ok else "✗ 待确认(模型可能未逐字复述,见下方 store 层校验)")

    # 兜底:直接在 store 层校验文件确实跨用户可见(不依赖模型复述)
    try:
        items = await bob.store.search_items(("xhs-shared",))
        keys = [getattr(it, "key", None) or (it.get("key") if isinstance(it, dict) else None) for it in (items.get("items", items) if isinstance(items, dict) else items)]
        print("store 层(bob 视角)xhs-shared 命名空间条目:", keys)
    except Exception as e:
        print("store 层校验跳过:", type(e).__name__, str(e)[:80])



if __name__ == "__main__":
    asyncio.run(main())
