# 小红书文案智能体 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 deepagents 搭建小红书文案智能体的阶段一 1a 最小闭环:读飞书多维表格爆款数据 → 分析子智能体拆解 → 两步式产出选题菜单与文案。

**Architecture:** 对齐 deepagents 官方 "agent = folder" 范式。`create_deep_agent` 组装主智能体,挂载一个"按方向产出选题+文案" Skill 与一个"爆款分析"子智能体;飞书多维表格通过一个自定义只读工具动态读取(不写死字段);1a 阶段用单会话 CLI 运行,文件走 FilesystemBackend(根目录为项目目录,使 skills 从磁盘加载、文件工具读写真实文件)。

**Tech Stack:** Python ≥3.11、deepagents、langchain、langchain-anthropic、httpx(飞书 API)、pytest、uv。

**范围边界(本计划只做 1a)**:不含多用户/CompositeBackend/Postgres/官方前端/真飞书登录——那些属于 1b 及以后,见设计文档第八节。1a 的目标是用 CLI 验证"读飞书→拆解→出文案"的核心价值链与文案质量。

参考设计文档:`docs/superpowers/specs/2026-06-15-xhs-content-agent-design.md`

---

## 执行进度(Subagent-Driven 执行,分支 feat/xhs-agent-1a)

- ✅ **Task 1-8 全部完成**,各任务均过两阶段审查(spec 合规 + 代码质量),并通过一次跨文件最终审查。13 个提交,5 个单测全绿。
- 关键修正(最终审查发现并经源码核实):默认 `StateBackend` 读不到磁盘上的 `skills/`,导致 topic-content skill 静默不加载——已切换 `FilesystemBackend(root_dir=cwd)`,一并修复 `/shared/xhs-style.md` 二次写回问题。
- ⏳ **Task 9(端到端联调)待执行** —— 需用户提供真实凭证(飞书 app_id/secret/app_token/table_id + ANTHROPIC_API_KEY)方可运行,验证文案质量并决定是否进入 1b。

---


## 文件结构

本阶段创建的文件及其单一职责:

| 文件 | 职责 |
|---|---|
| `pyproject.toml` | 项目元数据与依赖(uv 管理) |
| `.env.example` | 环境变量模板(飞书凭证、模型 key);真实 `.env` 不入库 |
| `.gitignore` | 已存在,追加 Python 忽略项 |
| `tools/__init__.py` | 标记 tools 为包 |
| `tools/feishu_bitable.py` | 飞书多维表格只读工具:鉴权取 token、拉取整表列名+数据行 |
| `skills/topic-content/SKILL.md` | 应用①工作流定义(两步式选题→文案) |
| `subagents.py` | 爆款分析子智能体定义(SubAgent 字典) |
| `prompts.py` | 主智能体 system_prompt 文本常量 |
| `agent.py` | `create_deep_agent` 组装入口,导出 `agent` 变量 |
| `langgraph.json` | LangGraph server 配置,指向 `agent.py:agent` |
| `cli.py` | 1a 阶段的命令行入口,流式跑 agent |
| `tests/test_feishu_bitable.py` | 飞书工具单元测试(mock HTTP) |
| `tests/test_agent_assembly.py` | agent 能正确组装的冒烟测试 |

每个文件聚焦一个职责;飞书工具与业务逻辑(SKILL/prompt)分离,换数据源不动业务。

---

## Task 1: 项目骨架与依赖

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Modify: `.gitignore`(已存在)

- [ ] **Step 1: 写 pyproject.toml**

```toml
[project]
name = "xhs-content-agent"
version = "0.1.0"
description = "小红书文案智能体 - 基于 deepagents"
requires-python = ">=3.11"
dependencies = [
    "deepagents>=0.6.8",
    "langchain>=1.3.9,<2.0.0",
    "langchain-anthropic>=1.4.6,<2.0.0",
    "httpx>=0.27.0",
    "python-dotenv>=1.0.1",
    "rich>=15.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "respx>=0.21.1",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]

[tool.ruff.lint.flake8-tidy-imports]
ban-relative-imports = "all"
```

- [ ] **Step 2: 写 .env.example**

```bash
# 模型
ANTHROPIC_API_KEY=sk-ant-xxx
# 可选:若主/子智能体要用 GPT
OPENAI_API_KEY=

# 飞书自建应用凭证(开放平台 → 企业自建应用)
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
# 飞书爆款多维表格定位(从表格 URL 取:base/{app_token}?table={table_id})
FEISHU_BITABLE_APP_TOKEN=xxx
FEISHU_BITABLE_TABLE_ID=tblxxx
```

- [ ] **Step 3: 追加 .gitignore Python 项**

确认 `.gitignore` 含以下行(Task 0 已创建基础版,补全):

```
node_modules/
.env
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
```

- [ ] **Step 4: 安装依赖并验证**

Run: `uv sync`
Expected: 成功创建 `.venv`,无解析冲突报错。

若机器无 uv,先 `pip install uv` 或用 `python -m venv .venv && pip install -e ".[dev]"` 等价安装。

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env.example .gitignore
git commit -m "chore: 项目骨架与依赖"
```

---

## Task 2: 飞书多维表格只读工具

飞书 API 两步:① 用 app_id/app_secret 换 `tenant_access_token`;② 用该 token 调多维表格"列出记录"接口。工具返回"列名清单 + 数据行",不写死字段映射(对应设计做法 B)。

**Files:**
- Create: `tools/__init__.py`
- Create: `tools/feishu_bitable.py`
- Test: `tests/test_feishu_bitable.py`

- [ ] **Step 1: 写 tools/__init__.py(空包标记)**

```python
```

(空文件即可。)

- [ ] **Step 2: 写失败测试 tests/test_feishu_bitable.py**

```python
import respx
import httpx
import pytest

from tools.feishu_bitable import fetch_token, read_bitable_records


@respx.mock
def test_fetch_token_returns_tenant_access_token():
    respx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    ).mock(return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}))

    token = fetch_token("cli_x", "secret_x")
    assert token == "t-abc"


@respx.mock
def test_fetch_token_raises_on_error_code():
    respx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    ).mock(return_value=httpx.Response(200, json={"code": 99991663, "msg": "app not found"}))

    with pytest.raises(RuntimeError, match="飞书鉴权失败"):
        fetch_token("bad", "bad")


@respx.mock
def test_read_bitable_records_returns_columns_and_rows():
    respx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    ).mock(return_value=httpx.Response(200, json={"code": 0, "tenant_access_token": "t-abc", "expire": 7200}))
    respx.get(
        "https://open.feishu.cn/open-apis/bitable/v1/apps/APP/tables/TBL/records"
    ).mock(return_value=httpx.Response(200, json={
        "code": 0,
        "data": {
            "has_more": False,
            "items": [
                {"fields": {"标题": "露营好物", "点赞": 1200, "正文": "正文内容"}},
                {"fields": {"标题": "帐篷测评", "点赞": 980, "正文": "另一篇"}},
            ],
        },
    }))

    result = read_bitable_records("cli_x", "secret_x", "APP", "TBL")
    assert set(result["columns"]) == {"标题", "点赞", "正文"}
    assert len(result["rows"]) == 2
    assert result["rows"][0]["标题"] == "露营好物"
```

- [ ] **Step 3: 运行测试,确认失败**

Run: `uv run pytest tests/test_feishu_bitable.py -v`
Expected: FAIL,`ModuleNotFoundError` 或 `ImportError: cannot import name 'fetch_token'`。

- [ ] **Step 4: 实现 tools/feishu_bitable.py**

```python
"""飞书多维表格只读工具。

两步:① app_id/secret 换 tenant_access_token;② 拉取整表记录。
返回 {columns, rows},不写死字段映射(设计做法 B:由智能体自行理解表结构)。
"""
import os
from typing import Any

import httpx
from langchain_core.tools import tool

FEISHU_BASE = "https://open.feishu.cn/open-apis"


def fetch_token(app_id: str, app_secret: str) -> str:
    """用应用凭证换取 tenant_access_token。"""
    resp = httpx.post(
        f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=15.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"飞书鉴权失败: code={data.get('code')} msg={data.get('msg')}")
    return data["tenant_access_token"]


def read_bitable_records(
    app_id: str,
    app_secret: str,
    bitable_app_token: str,
    table_id: str,
    page_size: int = 200,
) -> dict[str, Any]:
    """读取整张多维表的记录,返回列名清单与数据行。

    Returns:
        {"columns": [列名...], "rows": [{列名: 值, ...}, ...]}
    """
    token = fetch_token(app_id, app_secret)
    headers = {"Authorization": f"Bearer {token}"}
    rows: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        params: dict[str, Any] = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token
        resp = httpx.get(
            f"{FEISHU_BASE}/bitable/v1/apps/{bitable_app_token}/tables/{table_id}/records",
            headers=headers,
            params=params,
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书读表失败: code={data.get('code')} msg={data.get('msg')}")
        block = data.get("data", {})
        for item in block.get("items", []):
            rows.append(item.get("fields", {}))
        if block.get("has_more") and block.get("page_token"):
            page_token = block["page_token"]
            continue
        break

    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return {"columns": columns, "rows": rows}


@tool
def read_xhs_data() -> dict[str, Any]:
    """读取飞书多维表格里的小红书爆款/对标数据。

    返回整表的列名清单与所有数据行,供你分析爆款规律、提炼选题与文案套路。
    你需要自行理解每一列的含义(如标题、正文、点赞、收藏、话题标签等)。

    Returns:
        {"columns": [列名...], "rows": [{列名: 值, ...}, ...]}
    """
    return read_bitable_records(
        os.environ["FEISHU_APP_ID"],
        os.environ["FEISHU_APP_SECRET"],
        os.environ["FEISHU_BITABLE_APP_TOKEN"],
        os.environ["FEISHU_BITABLE_TABLE_ID"],
    )
```

- [ ] **Step 5: 运行测试,确认通过**

Run: `uv run pytest tests/test_feishu_bitable.py -v`
Expected: 3 个测试 PASS。

- [ ] **Step 6: Commit**

```bash
git add tools/__init__.py tools/feishu_bitable.py tests/test_feishu_bitable.py
git commit -m "feat: 飞书多维表格只读工具"
```

---

## Task 3: 主智能体提示词

主智能体的角色设定:小红书文案专家,两步式工作流,何时调子智能体与工具。纯文本常量,与组装代码分离便于迭代。

**Files:**
- Create: `prompts.py`

- [ ] **Step 1: 写 prompts.py**

```python
"""主智能体 system_prompt 文本。与组装逻辑分离,便于单独迭代措辞。"""

MAIN_SYSTEM_PROMPT = """你是一个小红书文案创作专家,服务于一个内容运营团队。

你的全部素材来源是飞书多维表格里的爆款/对标数据(通过 read_xhs_data 工具获取),
不联网搜索。你的工作是从这些私有数据里提炼规律,产出贴合小红书风格的新文案。

## 工作流(两步式,务必遵守)

当用户给你一个内容方向(如"露营装备""亲子出游"):

1. 调用 read_xhs_data 工具读取爆款数据。
2. 用 task 工具委派 "baokuan-analyst" 子智能体,让它拆解与该方向相关的爆款:
   选题角度、标题套路、正文结构、情绪触发点、话题标签习惯。
   告诉它把分析结论写到 /analysis/<方向>.md。
3. 读取子智能体写出的分析文件。
4. 基于分析,产出 3~5 个【选题方向】,以清晰列表呈现(每个选题:一句话角度 + 预期爆点)。
   **停在这里,等用户选择,不要直接写完整文案。**
5. 用户选定某个选题后,写完整文案:
   - 标题(小红书标题党风格,可带 emoji)
   - 正文(分段、口语化、带 emoji、有记忆点)
   - 话题标签(#xxx 形式,5~10 个)
   以可直接复制的分块格式输出在对话里,同时用 write_file 存一份到 /drafts/<slug>.md。
6. 用户提修改意见时,迭代打磨当前文案。

## 风格沉淀

每当你从爆款里提炼出有价值的通用套路,用 read_file 读 /shared/xhs-style.md
(若不存在则视为空),把新套路【追加】进去后用 write_file 写回。不要覆盖既有内容。
这个文件是团队共享的小红书方法论,会越用越准。

## 原则
- 文案要像真人写的小红书笔记,不要 AI 腔、不要营销八股。
- 选题和文案都要有依据,依据来自数据里的爆款规律,不要凭空编。
- 输出中文。
"""
```

- [ ] **Step 2: 验证可导入**

Run: `uv run python -c "from prompts import MAIN_SYSTEM_PROMPT; print(len(MAIN_SYSTEM_PROMPT))"`
Expected: 打印一个正整数(字符串长度),无报错。

- [ ] **Step 3: Commit**

```bash
git add prompts.py
git commit -m "feat: 主智能体提示词"
```

---

## Task 4: 爆款分析子智能体

子智能体在独立上下文里拆解爆款,结论写入文件,不污染主对话。用 deepagents 的 `SubAgent` 字典定义(字段:name/description/system_prompt,可选 tools/model)。

**Files:**
- Create: `subagents.py`

- [ ] **Step 1: 写 subagents.py**

```python
"""子智能体定义。爆款分析子智能体在独立上下文拆解数据,结论落盘。"""
from tools.feishu_bitable import read_xhs_data

# 子智能体默认用便宜快的模型(设计:子智能体用便宜快模型)
ANALYST_MODEL = "anthropic:claude-haiku-4-5-20251001"

ANALYST_SYSTEM_PROMPT = """你是小红书爆款分析助手。你的任务是拆解给定方向的爆款笔记,
提炼可复用的创作规律,并把结论写入指定文件。

## 你的工具
- read_xhs_data():读取飞书表里的爆款数据(列名 + 数据行)
- write_file(file_path, content):保存你的分析结论

## 流程
1. 调 read_xhs_data 获取数据。你需自行判断哪列是标题、正文、互动数据(点赞/收藏)、
   话题标签等——列名可能不规范,按语义理解。
2. 筛选与任务给定方向相关的笔记。
3. 拆解并总结这些维度:
   - 选题角度:这些爆款都从什么角度切入
   - 标题套路:标题的结构、关键词、情绪词、数字/emoji 用法
   - 正文结构:开头怎么钩人、中间怎么展开、结尾怎么收
   - 情绪触发点:激发了读者什么情绪(种草/焦虑/共鸣/好奇)
   - 话题标签习惯:常用哪些标签、几个
4. 用 write_file 把结论写到任务里指定的文件路径(如 /analysis/<方向>.md)。

## 要求
- 结论要具体、可操作,引用数据里的真实例子,不要空泛。
- 如果某方向相关数据很少,如实说明,不要硬编。
- 输出中文。
"""

baokuan_analyst = {
    "name": "baokuan-analyst",
    "description": (
        "拆解飞书数据里某个方向的小红书爆款,提炼选题角度、标题套路、正文结构、"
        "情绪点与标签习惯。委派时请说明:分析哪个方向,以及把结论写到哪个文件路径"
        "(如 '分析露营装备方向,结论写到 /analysis/露营装备.md')。"
    ),
    "system_prompt": ANALYST_SYSTEM_PROMPT,
    "model": ANALYST_MODEL,
    "tools": [read_xhs_data],
}
```

- [ ] **Step 2: 验证可导入**

Run: `uv run python -c "from subagents import baokuan_analyst; print(baokuan_analyst['name'])"`
Expected: 打印 `baokuan-analyst`,无报错。

- [ ] **Step 3: Commit**

```bash
git add subagents.py
git commit -m "feat: 爆款分析子智能体"
```

---

## Task 5: 应用①的 Skill 定义

Skill 用 `SKILL.md` + frontmatter(`name`/`description`),描述"按方向产出选题+文案"的工作流。`description` 决定主智能体何时自动选用该 skill。

**Files:**
- Create: `skills/topic-content/SKILL.md`

- [ ] **Step 1: 写 skills/topic-content/SKILL.md**

```markdown
---
name: topic-content
description: 根据一个内容方向(如露营装备、亲子出游、护肤),从飞书爆款数据中提炼选题并产出小红书文案。当用户给出一个主题/方向、或要求"出选题""写小红书文案""按某方向创作"时使用。
---

# 按方向产出选题 + 文案

这是一个两步式工作流:先给选题菜单,用户选定后再写完整文案。

## 第一步:出选题(用户给方向后)

1. 调 `read_xhs_data` 读取飞书爆款数据。
2. 用 `task` 委派 `baokuan-analyst` 子智能体拆解该方向爆款,
   要求把结论写到 `/analysis/<方向>.md`。
3. 用 `read_file` 读取该分析文件。
4. 基于分析,产出 **3~5 个选题方向**,列表呈现。每个选题包含:
   - 一句话角度(切入点)
   - 预期爆点(为什么可能火,依据来自分析)
5. **停下,请用户选择一个选题。不要在这一步直接写完整文案。**

## 第二步:写文案(用户选定选题后)

为选定选题写完整小红书文案,分三块、可直接复制:

```
【标题】
<标题党风格,可含 emoji>

【正文】
<分段、口语化、带 emoji、有记忆点>

【话题标签】
#标签1 #标签2 ...(5~10 个)
```

同时用 `write_file` 把这篇文案存到 `/drafts/<slug>.md`(slug 用方向+序号,如 `露营装备-1`)。

## 第三步:打磨

用户提意见时迭代修改当前文案,保持分块可复制格式。

## 风格沉淀(贯穿)

提炼到通用套路时,`read_file` 读 `/shared/xhs-style.md`(不存在视为空),
追加新套路后 `write_file` 写回,不覆盖旧内容。

## 质量检查(交付文案前)
- [ ] 标题有钩子,不平淡
- [ ] 正文像真人小红书笔记,无 AI 腔、无营销八股
- [ ] 标签 5~10 个且相关
- [ ] 选题与文案均有数据依据,非凭空
- [ ] 文案已存入 /drafts/
```

- [ ] **Step 2: 验证文件存在且 frontmatter 完整**

Run: `uv run python -c "import pathlib,re; t=pathlib.Path('skills/topic-content/SKILL.md').read_text(encoding='utf-8'); assert t.startswith('---'); assert 'name: topic-content' in t; assert 'description:' in t; print('SKILL ok')"`
Expected: 打印 `SKILL ok`。

- [ ] **Step 3: Commit**

```bash
git add skills/topic-content/SKILL.md
git commit -m "feat: topic-content skill 定义"
```

---

## Task 6: agent 组装入口

用 `create_deep_agent` 把模型、飞书工具、system_prompt、子智能体、skill 路径组装成 agent,导出 `agent` 变量供 langgraph.json 引用。1a 阶段用默认 StateBackend(文件随会话,无需 CompositeBackend/Postgres)。

**Files:**
- Create: `agent.py`
- Test: `tests/test_agent_assembly.py`

- [ ] **Step 1: 写失败测试 tests/test_agent_assembly.py**

```python
import os


def test_agent_importable_and_compiled(monkeypatch):
    # 组装阶段会初始化 Anthropic 模型,需要 key 存在(不真实调用)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    import importlib
    import agent as agent_module
    importlib.reload(agent_module)
    # create_deep_agent 返回一个 CompiledStateGraph,应有 invoke 方法
    assert hasattr(agent_module.agent, "invoke")
    assert hasattr(agent_module.agent, "astream")
```

- [ ] **Step 2: 运行测试,确认失败**

Run: `uv run pytest tests/test_agent_assembly.py -v`
Expected: FAIL,`ModuleNotFoundError: No module named 'agent'`。

- [ ] **Step 3: 实现 agent.py**

```python
"""agent 组装入口。create_deep_agent 装配主智能体 + 飞书工具 + 子智能体 + skill。"""
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from deepagents import create_deep_agent

from prompts import MAIN_SYSTEM_PROMPT
from subagents import baokuan_analyst
from tools.feishu_bitable import read_xhs_data

load_dotenv()

# 主智能体默认 Claude(中文文案强);如需 GPT 改这里或用环境变量切换。
MAIN_MODEL = "anthropic:claude-sonnet-4-6"

model = init_chat_model(model=MAIN_MODEL, temperature=0.7)

agent = create_deep_agent(
    model=model,
    tools=[read_xhs_data],
    system_prompt=MAIN_SYSTEM_PROMPT,
    subagents=[baokuan_analyst],
    skills=["./skills/"],
)
```

- [ ] **Step 4: 运行测试,确认通过**

Run: `uv run pytest tests/test_agent_assembly.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add agent.py tests/test_agent_assembly.py
git commit -m "feat: agent 组装入口"
```

---

## Task 7: CLI 入口(1a 验证用)

1a 阶段用 CLI 跑通核心闭环(前端留到 1b)。流式输出对话、工具调用、子智能体进度,单会话内存运行。

**Files:**
- Create: `cli.py`

- [ ] **Step 1: 写 cli.py**

```python
"""1a 阶段命令行入口:流式跑 agent,验证读飞书→拆解→出选题/文案闭环。

用法:
    uv run python cli.py
    然后在提示符里输入方向,如「帮我按露营装备方向出选题」
    选题出来后输入「写第 2 个」继续,输入 exit 退出。
"""
import uuid

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent import agent

console = Console()


def render(msg) -> None:
    """渲染一条消息:AI 文本、工具调用、工具结果。"""
    mtype = msg.__class__.__name__
    if mtype == "AIMessage":
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
    elif mtype == "ToolMessage":
        name = getattr(msg, "name", "")
        if name == "read_xhs_data":
            console.print("  [green]✓ 已读取数据[/]")
        elif name == "task":
            console.print("  [green]✓ 子智能体分析完成[/]")


def main() -> None:
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    console.print("[bold blue]小红书文案智能体 (1a CLI)[/]  输入方向开始,exit 退出\n")
    printed = 0
    while True:
        try:
            user_input = console.input("[bold cyan]你> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue
        for chunk in agent.stream(
            {"messages": [("user", user_input)]},
            config=config,
            stream_mode="values",
        ):
            msgs = chunk.get("messages", [])
            for m in msgs[printed:]:
                render(m)
            printed = len(msgs)
    console.print("\n[dim]已退出[/]")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证可导入(不真实运行,需 key 才能跑通对话)**

Run: `uv run python -c "import cli; print('cli ok')"`
Expected: 打印 `cli ok`(`agent` 组装需 `ANTHROPIC_API_KEY` 在 `.env` 中;若仅验证导入可临时 `export ANTHROPIC_API_KEY=x`)。

- [ ] **Step 3: Commit**

```bash
git add cli.py
git commit -m "feat: 1a CLI 入口"
```

---

## Task 8: langgraph.json(为 1b/server 预留)

定义 LangGraph server 配置,指向 `agent.py:agent`。1a 用 CLI 即可,但配置文件现在建好,1b 启 server 与前端时直接用。

**Files:**
- Create: `langgraph.json`

- [ ] **Step 1: 写 langgraph.json**

```json
{
  "dependencies": ["."],
  "graphs": {
    "xhs_agent": "./agent.py:agent"
  },
  "env": ".env"
}
```

- [ ] **Step 2: 验证 JSON 合法且指向存在的变量**

Run: `uv run python -c "import json; c=json.load(open('langgraph.json',encoding='utf-8')); assert c['graphs']['xhs_agent']=='./agent.py:agent'; print('langgraph.json ok')"`
Expected: 打印 `langgraph.json ok`。

- [ ] **Step 3: Commit**

```bash
git add langgraph.json
git commit -m "chore: langgraph.json server 配置"
```

---

## Task 9: 端到端联调验证(需真实凭证)

非 TDD 任务,是人工冒烟:确认整条价值链在真实飞书数据 + 真实模型下跑通。这一步验证 1a 是否达成目标(文案质量可用)。

**前置:** 把真实凭证填入 `.env`(从 `.env.example` 复制)。

- [ ] **Step 1: 准备 .env**

```bash
cp .env.example .env
# 编辑 .env,填入真实 ANTHROPIC_API_KEY、FEISHU_APP_ID/SECRET/APP_TOKEN/TABLE_ID
```

- [ ] **Step 2: 单测飞书工具连真实表(临时脚本)**

Run: `uv run python -c "from dotenv import load_dotenv; load_dotenv(); import os; from tools.feishu_bitable import read_xhs_data; d=read_xhs_data.invoke({}); print('列:', d['columns']); print('行数:', len(d['rows']))"`
Expected: 打印出真实表的列名与行数,无鉴权/读表报错。
若报「飞书鉴权失败」→ 检查 app_id/secret 与应用是否已发布、是否开通多维表格读权限。
若读表 code 非 0 → 检查 app_token/table_id 是否正确、应用是否被加为该表格的协作者。

- [ ] **Step 3: 跑 CLI 走完两步式流程**

Run: `uv run python cli.py`
操作:
1. 输入一个真实方向(如「按露营装备方向出选题」)。
2. 确认:智能体调用了 read_xhs_data、委派了 baokuan-analyst、产出 3~5 个选题且停下等待。
3. 输入「写第 1 个」。
4. 确认:产出标题/正文/标签三块可复制文案,并写入 /drafts/。

Expected: 全程无异常;选题与文案有数据依据、像真人小红书笔记。

- [ ] **Step 4: 记录验证结论**

在本计划末尾"验证记录"勾选结果。若文案质量不达标,记录问题点 —— 这决定是否进入 1b(设计文档第八节:1a 不达标则不做 1b)。

- [ ] **Step 5: Commit(若联调中调整了 prompt/skill)**

```bash
git add -A
git commit -m "fix: 端到端联调调整"
```

---

## 验证记录(Task 9 完成后填写)

- [ ] 飞书工具能读到真实表数据
- [ ] 两步式流程正常(先选题、停顿、再文案)
- [ ] 子智能体分析落盘且被主智能体读取
- [ ] 文案以可复制分块格式输出并存入 /drafts/
- [ ] 文案质量评估:________(可用 / 需调 prompt / 需调数据)
- [ ] 是否进入 1b:________

---

## 1b 及以后(本计划不实现,仅备忘)

1a 验证通过后,1b 增量做:CompositeBackend(`/drafts/`→StateBackend 隔离、`/shared/`→StoreBackend 共享)+ Postgres checkpointer/store + 多会话 + 可切换模拟用户 + 官方 Agent Chat UI 前端。届时为 1b 另写一份计划。详见设计文档第八节。




