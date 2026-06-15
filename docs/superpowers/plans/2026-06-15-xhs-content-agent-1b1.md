# 小红书文案智能体 1b-1 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 1a 的 CLI 直连模式升级为 LangGraph server 模式,接入三路由 CompositeBackend,实现"共享爆款库/风格 + 各会话隔离草稿",并由 dev server 自带持久化提供多会话与跨轮记忆。

**Architecture:** `agent.py` 不再直接被 CLI import 跑,而是作为 `langgraph dev` server 的图入口(`langgraph.json` 已指向 `./agent.py:agent`)。backend 从单一 FilesystemBackend 改为 CompositeBackend 三路由:`/skills/`→FilesystemBackend(root 指向 skills/ 目录、virtual_mode)、`/shared/`→StoreBackend(跨会话共享)、`/drafts/` 及默认→StateBackend(随会话隔离)。持久化由 `langgraph dev` 注入(开发态),不在 agent.py 手写。Postgres 延到部署态。

**Tech Stack:** Python ≥3.11、deepagents、langgraph、langgraph-cli[inmem]、langgraph-sdk、langchain-anthropic、httpx、pytest、uv。

**范围边界(本计划只做 1b-1)**:不含前端(1b-2)、不含真飞书登录/多用户(1b-3)、不含 Postgres(部署态)。验证用 langgraph_sdk 脚本,不用浏览器。

**已实测验证的关键事实(写计划前已确认)**:
- CompositeBackend 路由会**剥掉前缀**:`/skills/topic-content/SKILL.md` 路由到 `/skills/` 后变成 `/topic-content/SKILL.md` 传给目标 backend。因此路由 `/skills/` 的 FilesystemBackend 的 `root_dir` 必须指向 `<项目>/skills/` 目录本身(而非项目根),否则 skills 读不到。已实测:这样配 `_list_skills` 能返回 topic-content 且能读内容。
- `create_deep_agent` 接受 `backend` 参数;`store` 在 backend 含 StoreBackend 时必需,但 server 模式下由 server 注入,agent.py 不传。

参考设计文档:`docs/superpowers/specs/2026-06-15-xhs-content-agent-design.md` 第八节。

---

## 文件结构

| 文件 | 变更 | 职责 |
|---|---|---|
| `pyproject.toml` | 改 | 加 `langgraph-cli[inmem]`、`langgraph-sdk` 依赖 |
| `backends.py` | 新建 | 构造三路由 CompositeBackend 的工厂函数,单一职责、可单测 |
| `agent.py` | 改 | 用 `backends.py` 的工厂替换原 FilesystemBackend |
| `tests/test_backends.py` | 新建 | 单测三路由:skills 经 composite 可加载、路径路由正确 |
| `verify_1b1.py` | 新建 | langgraph_sdk 联调脚本:跨轮记忆 / /shared 共享 / /drafts 隔离 |
| `README.md` | 新建 | 怎么起 server、怎么验证(给后续阶段留运行说明) |

把 backend 组装逻辑从 agent.py 抽到 backends.py,是因为它有了真实逻辑(三路由 + root_dir 计算)值得单测,且 agent.py 应保持薄组装。

---

## Task 1: 加依赖 langgraph-cli 与 sdk

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 pyproject.toml 的 dependencies 加两个依赖**

在 `dependencies = [...]` 列表里追加(放在 deepagents 相关项之后):

```toml
    "langgraph-cli[inmem]>=0.2.0",
    "langgraph-sdk>=0.1.0",
```

完整 dependencies 应为:
```toml
dependencies = [
    "deepagents>=0.6.8,<1.0.0",
    "langchain>=1.3.9,<2.0.0",
    "langchain-anthropic>=1.4.6,<2.0.0",
    "langgraph-cli[inmem]>=0.2.0",
    "langgraph-sdk>=0.1.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.1",
    "rich>=15.0.0",
]
```

- [ ] **Step 2: 同步依赖**

Run: `uv sync`
Expected: 成功解析安装,无冲突。`langgraph` CLI 可用。

- [ ] **Step 3: 验证 langgraph CLI 可用**

Run: `uv run langgraph --help`
Expected: 打印 langgraph CLI 帮助(含 `dev` 子命令),不再报 "program not found"。

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: 加 langgraph-cli 与 sdk 依赖"
```

---

## Task 2: 三路由 backend 工厂(TDD)

把 backend 组装抽成一个工厂函数,单测它能正确加载 skills 并路由路径。

**Files:**
- Create: `backends.py`
- Test: `tests/test_backends.py`

- [ ] **Step 1: 写失败测试 tests/test_backends.py**

```python
import os

from backends import build_backend


def test_build_backend_loads_skills_via_composite():
    """三路由 CompositeBackend 应能经 /skills/ 路由读到 topic-content skill。"""
    import deepagents.middleware.skills as sk

    backend = build_backend()
    skills = sk._list_skills(backend, "/skills/")
    names = [s["name"] for s in skills]
    assert "topic-content" in names


def test_build_backend_skills_path_is_virtual():
    """skill 路径应是虚拟路径(以 / 开头),非 Windows 绝对路径。"""
    import deepagents.middleware.skills as sk

    backend = build_backend()
    skills = sk._list_skills(backend, "/skills/")
    assert skills, "应至少加载到一个 skill"
    assert skills[0]["path"].startswith("/skills/")


def test_build_backend_routes_shared_to_store():
    """/shared/ 前缀应路由到 StoreBackend,而非默认 StateBackend。"""
    from deepagents.backends.store import StoreBackend

    backend = build_backend()
    target, _key = backend._get_backend_and_key("/shared/xhs-style.md")
    assert isinstance(target, StoreBackend)


def test_build_backend_routes_drafts_to_default_state():
    """/drafts/ 未单独路由,应落到默认 StateBackend。"""
    from deepagents.backends.state import StateBackend

    backend = build_backend()
    target, _key = backend._get_backend_and_key("/drafts/x.md")
    assert isinstance(target, StateBackend)
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `uv run pytest tests/test_backends.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'backends'`。

- [ ] **Step 3: 实现 backends.py**

```python
"""三路由文件后端工厂。

CompositeBackend 按路径前缀路由(已实测:路由会剥掉前缀):
- /skills/ → FilesystemBackend,root_dir 指向项目下的 skills/ 目录本身
  (因为前缀 /skills/ 被剥掉后,/topic-content/SKILL.md 需对应 skills/topic-content/SKILL.md)。
  共享只读,virtual_mode=True 避免 Windows 绝对路径问题。
- /shared/ → StoreBackend,跨会话/用户共享(风格沉淀)。server 注入 store。
- /drafts/ 及其他 → 默认 StateBackend,随会话隔离。
"""
import os

from deepagents.backends.composite import CompositeBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.state import StateBackend
from deepagents.backends.store import StoreBackend


def build_backend() -> CompositeBackend:
    """构造三路由 CompositeBackend。"""
    skills_root = os.path.join(os.getcwd(), "skills")
    skills_backend = FilesystemBackend(root_dir=skills_root, virtual_mode=True)
    return CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": skills_backend,
            "/shared/": StoreBackend(),
        },
    )
```

- [ ] **Step 4: 运行测试,确认通过**

Run: `uv run pytest tests/test_backends.py -v`
Expected: 4 个测试 PASS。

> 注意:`StoreBackend()` 的构造不需要立即连 store(store 在运行时由 server 注入)。若 `test_build_backend_routes_shared_to_store` 因 StoreBackend 构造需要参数而失败,检查 StoreBackend 的构造签名并按需调整(它应支持无参构造,运行时再绑定 store)。若构造确实需要参数,报告为 BLOCKED 并附错误,不要乱传参数。

- [ ] **Step 5: Commit**

```bash
git add backends.py tests/test_backends.py
git commit -m "feat: 三路由 CompositeBackend 工厂"
```

---

## Task 3: agent.py 改用三路由 backend

**Files:**
- Modify: `agent.py`
- Test: `tests/test_agent_assembly.py`(已存在,确认仍通过)

- [ ] **Step 1: 修改 agent.py 的 backend 构造**

当前 agent.py 里是:
```python
# FilesystemBackend 让 skills 从磁盘加载、文件工具读写真实文件。
# virtual_mode=True:...
backend = FilesystemBackend(root_dir=os.getcwd(), virtual_mode=True)
```

改为用工厂(删掉原 FilesystemBackend 那两三行注释 + 构造,替换为):
```python
# 三路由 CompositeBackend:/skills/(磁盘共享只读)、/shared/(Store 共享)、
# /drafts/ 及默认(State 随会话隔离)。详见 backends.py。
backend = build_backend()
```

同时调整 import:
- 删除 `from deepagents.backends import FilesystemBackend`(若不再使用)
- 删除不再需要的 `import os`(若 agent.py 其他地方没用到 os——检查一下;build_backend 内部用 os,agent.py 可能不再需要)
- 新增 `from backends import build_backend`(放在第一方 import 组:prompts/subagents/tools 那一组)

注意保持 import 分组与排序(stdlib / 第三方 / 第一方)。

- [ ] **Step 2: 运行已有组装测试,确认仍通过**

Run: `ANTHROPIC_API_KEY=sk-ant-test uv run pytest tests/test_agent_assembly.py -v`
Expected: PASS(agent 仍能用新 backend 编译)。

- [ ] **Step 3: 运行全部单测**

Run: `ANTHROPIC_API_KEY=sk-ant-test uv run pytest -v`
Expected: 全绿(原 5 个 + Task 2 的 4 个 = 9 个)。

- [ ] **Step 4: 确认 agent 仍能导入且 skills 经新 backend 加载**

Run: `ANTHROPIC_API_KEY=sk-ant-test uv run python -c "import agent; print('agent ok')"`
Expected: `agent ok`。

- [ ] **Step 5: Commit**

```bash
git add agent.py
git commit -m "feat: agent 改用三路由 backend"
```

---

## Task 4: SDK 联调验证脚本

写一个脚本,起 server 后用 langgraph_sdk 连本地 server,验证 1b-1 的三个核心成果。这是 1b-1 的验收手段(无前端)。

**Files:**
- Create: `verify_1b1.py`

- [ ] **Step 1: 写 verify_1b1.py**

```python
"""1b-1 联调验证:连本地 langgraph dev server,验证跨轮记忆 / /shared 共享 / /drafts 隔离。

前置:另开一个终端先跑 `uv run langgraph dev`(默认 http://127.0.0.1:2024),
再在本终端跑 `uv run python verify_1b1.py`。
"""
import asyncio
import uuid

from langgraph_sdk import get_client

URL = "http://127.0.0.1:2024"
GRAPH = "xhs_agent"  # 对应 langgraph.json 里的 graph 名


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
    client = get_client(url=URL)

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
```

- [ ] **Step 2: 语法/导入检查(不连 server)**

Run: `uv run python -c "import ast; ast.parse(open('verify_1b1.py',encoding='utf-8').read()); print('verify_1b1 语法 ok')"`
Expected: `verify_1b1 语法 ok`。

- [ ] **Step 3: Commit**

```bash
git add verify_1b1.py
git commit -m "feat: 1b-1 SDK 联调验证脚本"
```

> 注意:实际跑 verify_1b1.py 需要先起 server(Task 6),这一步只提交脚本。`text_of`/stream 事件结构若与 sdk 实际返回不符,会在 Task 6 联调时按真实返回调整。

---

## Task 5: README 运行说明

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写 README.md**

```markdown
# 小红书文案智能体

基于 [deepagents](https://github.com/langchain-ai/deepagents) 的小红书文案创作智能体。
从飞书多维表格读取爆款数据,分析套路,产出小红书选题与文案。

## 环境准备

1. 安装依赖(需 [uv](https://docs.astral.sh/uv/)):
   ```bash
   uv sync
   ```
2. 复制 `.env.example` 为 `.env`,填入:
   - `ANTHROPIC_API_KEY` 与(如用中转)`ANTHROPIC_BASE_URL`
   - 飞书自建应用:`FEISHU_APP_ID` / `FEISHU_APP_SECRET`
   - 爆款表定位:`FEISHU_BITABLE_APP_TOKEN` / `FEISHU_BITABLE_TABLE_ID`

## 运行方式

### CLI(1a,单会话)
```bash
uv run python cli.py
```

### LangGraph server(1b-1,多会话 + 共享/隔离)
```bash
uv run langgraph dev
```
默认起在 `http://127.0.0.1:2024`。

联调验证(另开终端,server 起好后):
```bash
uv run python verify_1b1.py
```
验证:跨轮记忆、`/shared` 跨会话共享、`/drafts` 按会话隔离。

## 文件后端路由(1b-1)

- `/skills/` → 磁盘 `skills/` 目录(共享只读)
- `/shared/` → Store(跨会话/用户共享,如风格沉淀)
- `/drafts/` 及其他 → State(随会话隔离)

## 测试
```bash
uv run pytest
```

## 文档
- 设计:`docs/superpowers/specs/2026-06-15-xhs-content-agent-design.md`
- 计划:`docs/superpowers/plans/`
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README 运行说明"
```

---

## Task 6: 端到端联调(起 server 实跑)

非 TDD,人工/脚本验收。验证 server 模式下中转可用 + 三个核心成果。

- [ ] **Step 1: 起 server(后台或独立终端)**

Run: `uv run langgraph dev`
Expected: server 起在 `http://127.0.0.1:2024`,日志无致命错误。注意观察启动日志里是否成功加载 graph `xhs_agent`。

若 server 启动报错(如端口占用),换端口:`uv run langgraph dev --port 2025`,并相应改 verify_1b1.py 的 URL。

- [ ] **Step 2: 跑验证脚本**

Run(server 起好后,另开终端):`uv run python verify_1b1.py`
Expected: 三项均 `✓ 通过`:
1. 跨轮记忆:第二轮能说出暗号"菠萝啤"。
2. /shared 共享:thread B 读到 thread A 写的 `SHARED-OK` 标记。
3. /drafts 隔离:thread B 读不到 thread A 的 `DRAFT-A-ONLY` 草稿。

- [ ] **Step 3: 排障(若某项失败)**

- **中转不通**(模型调用报错):确认 server 进程继承了 `.env` 的 `ANTHROPIC_BASE_URL`。langgraph.json 已配 `"env": ".env"`。若仍不通,检查 langgraph dev 是否加载该 env 文件。
- **/shared 共享失败**(B 读不到 A):说明 dev server 未注入跨线程 store,或 StoreBackend 未拿到 store。这是设计风险点——若 dev server 默认不提供持久 store,记录现象并报告,可能需要在 langgraph.json 配置 store 或显式提供 InMemoryStore(届时按真实情况决定,不要硬塞)。
- **/drafts 隔离失败**(B 读到 A):StateBackend 应随 thread 隔离,若串了说明路由或 thread 配置有误,检查 verify 脚本是否每次用了新 thread_id。
- **跨轮记忆失败**:确认两轮用的是同一个 thread_id,且 dev server 的 checkpointer 生效。

- [ ] **Step 4: 记录验证结论**

把结果填到本计划末尾"验证记录"。三项全过则 1b-1 完成。

- [ ] **Step 5: Commit(若联调中调整了脚本/配置)**

```bash
git add -A
git commit -m "fix: 1b-1 联调调整"
```

---

## 验证记录(Task 6 完成后填写)

- [x] server 起得来,graph xhs_agent 加载成功(langgraph_runtime_inmem,http://127.0.0.1:2024)
- [x] server 模式下中转模型可调用(三项验证均成功调用模型)
- [x] 跨轮记忆:✓ 通过(第二轮答出暗号"菠萝啤")—— 修复 1a 无记忆痛点
- [x] /shared 跨会话共享:✓ 通过(thread B 读到 thread A 写的 SHARED-OK 标记;dev server 确实注入了 store)
- [x] /drafts 按会话隔离:✓ 通过(thread B 读不到 thread A 的 DRAFT-A-ONLY 草稿)
- [x] 1b-1 是否完成:**是**,三路由共享/隔离模型 + 多会话 + 跨轮记忆全部验证有效

### 设计风险点结论
1b-1 计划中标注的风险"dev server 是否提供跨会话 store"——**已验证成立**:`langgraph dev` 的 inmem runtime 自动注入了 store,/shared 跨 thread 共享开箱即用,无需手写 InMemoryStore。Postgres 仍按 A 方案留到部署态。

---

## 1b-2 / 1b-3(本计划不实现,备忘)

- 1b-2:克隆官方 Agent Chat UI(Next.js),配 `NEXT_PUBLIC_API_URL` 指向本 server + graph 名 `xhs_agent`,浏览器多会话聊天。
- 1b-3:飞书 OAuth 登录(本地先用可切换模拟用户占位,通过请求头传 user_id),按用户隔离会话与 /drafts,共享 /skills 与 /shared。
- 全部完成后做整体复查(跨 1b 全量代码审查 + 完整回归)。


