import base64
import hashlib
import hmac
import json
import os
import time

secret = os.environ["XHS_JWT_SECRET"]
admins = [a.strip() for a in os.environ.get("XHS_ADMIN_OPEN_IDS", "").split(",") if a.strip()]
sub = admins[0] if admins else "ou_probe"


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


h = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
p = b64(json.dumps({"sub": sub, "name": "probe", "exp": int(time.time()) + 900}).encode())
sig = b64(hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest())
jwt = f"{h}.{p}.{sig}"

from langgraph_sdk import get_sync_client

client = get_sync_client(url="http://localhost:8000", headers={"Authorization": f"Bearer {jwt}"})
th = client.threads.create()
tid = th["thread_id"]

prompt = "帮我按『职场穿搭』方向出 3 个选题，给出依据"
try:
    for _chunk in client.runs.stream(
        tid, "xhs_agent",
        input={"messages": [{"role": "user", "content": prompt}]},
        stream_mode="values",
    ):
        pass
except Exception as e:  # noqa: BLE001
    print("RUN_ERROR", type(e).__name__, str(e)[:300])

st = client.threads.get_state(tid)
msgs = st["values"].get("messages", []) if isinstance(st.get("values"), dict) else []
# 取最后一条 ai 消息
ai = [m for m in msgs if m.get("type") == "ai"]
if ai:
    last = ai[-1]
    content = last.get("content")
    print("CONTENT_IS_STR", isinstance(content, str))
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    print("=== RAW HEAD (first 1800) ===")
    print(text[:1800])
    print("=== RAW TAIL (last 600) ===")
    print(text[-600:])
    print("=== FENCE CHECK ===")
    print("has ```xhs_topics :", "```xhs_topics" in text)
    print("has ```json :", "```json" in text)
    print("count of ``` :", text.count("```"))
