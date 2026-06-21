# Meilisearch + FalkorDB 引擎接入 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 真实部署 Meilisearch(全文)+ FalkorDB(图谱)两引擎,实现对应 outbox processor 接入现有管线,作为检索/图谱唯一路径,删除 PG tsvector 全文与递归 SQL 图谱旧逻辑。

**Architecture:** 两个新 processor 复刻 `EmbeddingProcessor` 的 `Processor` 协议(`topic`/`state()`/`process()`),注册进 `default_processor_registry`,scheduler/outbox_worker 不改。检索 tool 查引擎得有序 resource_id → 回 Postgres 用 `readable_resource_where` 过权限并取元数据(引擎不存 ACL)。配置就绪即 active,无降级。

**Tech Stack:** Python 3.12、Meilisearch(getmeili/meilisearch + meilisearch-python)、FalkorDB(falkordb/falkordb + falkordb-py)、Postgres/pgvector、Docker、PM2、langgraph dev。

**部署铁律(CLAUDE.md):** 本地改代码 → commit → `git -c http.proxy= -c https.proxy= push origin master` → 服务器 `git pull --ff-only` → 重启/重建 → **在服务器真实环境验证**(不在本地跑功能验证)。根本性修复,不做兼容。服务器:`124.221.173.80`,项目 `/home/ubuntu/xiaohongshu-agent`,PM2 `xhs-backend`(2030)/`xhs-frontend`(9091)。

---

## 文件结构

**新建:**
- `data_foundation/engine_config.py` — Meili/Falkor 配置快照解析(对称 `config.py` 的 embedding snapshot)
- `data_foundation/meili_client.py` — Meilisearch 薄封装(索引 upsert、search)
- `data_foundation/falkor_client.py` — FalkorDB 薄封装(MERGE 节点/边、Cypher 扩展查询)
- `data_foundation/processors/meili.py` — `MeiliProcessor`(topic=meili_index)
- `data_foundation/processors/graph.py` — `GraphProcessor`(topic=graph_ingest)
- 对应测试:`tests/data_foundation/test_engine_config.py`、`test_meili_processor.py`、`test_graph_processor.py`、`test_meili_client.py`、`test_falkor_client.py`

**修改:**
- `data_foundation/processors/registry.py` — 注册 MeiliProcessor + GraphProcessor
- `data_foundation/repository.py` — 新增 `readable_rows_by_ids`;删除 `keyword_rows`、`graph_rows`
- `data_foundation/search.py` — `keyword_search` 删除,新增 Meili 路径(或移到 tools)
- `data_foundation/tools.py` — `search_resources` 改查 Meili、`graph_expand` 改查 Falkor
- `data_foundation/graph.py` — `expand_graph` 改查 FalkorDB
- `config_center.py` — DEPLOY_ONLY_KEYS/SECRET_KEYS 加 4 个引擎配置键
- `.env.example` — 文档化引擎配置
- `pyproject.toml` — 加 meilisearch、falkordb 依赖
- 删 `data_foundation/outbox_requests.py` 的 `default_resource_requests`(仅测试引用的冗余)

---

## 阶段 1:基础设施(Docker 服务 + 客户端库 + 配置)

### Task 1.1: 加 Python 依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: 在 dependencies 加两个库**

在 `pyproject.toml` 的 `[project] dependencies` 列表里加(紧跟现有依赖):
```toml
    "meilisearch>=0.31,<1.0",
    "falkordb>=1.0,<2.0",
```

- [ ] **Step 2: 本地同步并验证可导入**

Run: `cd "E:/小红书智能体" && uv sync 2>&1 | tail -5 && uv run python -c "import meilisearch, falkordb; print('imports OK')"`
Expected: 末尾打印 `imports OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add meilisearch + falkordb client deps"
```

### Task 1.2: 引擎配置快照模块

**Files:**
- Create: `data_foundation/engine_config.py`
- Test: `tests/data_foundation/test_engine_config.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/data_foundation/test_engine_config.py
from data_foundation.engine_config import meili_config, falkor_config


def test_meili_config_enabled_when_url_and_key_present():
    cfg = meili_config({"XHS_MEILI_URL": "http://127.0.0.1:7700", "XHS_MEILI_KEY": "k"})
    assert cfg.state == "enabled"
    assert cfg.url == "http://127.0.0.1:7700"
    assert cfg.api_key == "k"


def test_meili_config_disabled_when_missing():
    assert meili_config({"XHS_MEILI_URL": "", "XHS_MEILI_KEY": ""}).state == "disabled"
    assert meili_config({"XHS_MEILI_URL": "http://x", "XHS_MEILI_KEY": ""}).state == "disabled"


def test_falkor_config_enabled_when_url_present():
    cfg = falkor_config({"XHS_FALKOR_URL": "redis://127.0.0.1:6379", "XHS_FALKOR_GRAPH": "xhs"})
    assert cfg.state == "enabled"
    assert cfg.url == "redis://127.0.0.1:6379"
    assert cfg.graph_name == "xhs"


def test_falkor_config_defaults_graph_name():
    cfg = falkor_config({"XHS_FALKOR_URL": "redis://127.0.0.1:6379", "XHS_FALKOR_GRAPH": ""})
    assert cfg.state == "enabled"
    assert cfg.graph_name == "xhs"


def test_falkor_config_disabled_when_missing_url():
    assert falkor_config({"XHS_FALKOR_URL": "", "XHS_FALKOR_GRAPH": "xhs"}).state == "disabled"
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_engine_config.py -q`
Expected: FAIL(ModuleNotFoundError: data_foundation.engine_config)

- [ ] **Step 3: 写实现**

```python
# data_foundation/engine_config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, Mapping


@dataclass(frozen=True)
class MeiliConfig:
    state: Literal["enabled", "disabled"]
    url: str
    api_key: str


@dataclass(frozen=True)
class FalkorConfig:
    state: Literal["enabled", "disabled"]
    url: str
    graph_name: str


def meili_config(values: Mapping[str, str]) -> MeiliConfig:
    url = str(values.get("XHS_MEILI_URL", "") or "").strip()
    api_key = str(values.get("XHS_MEILI_KEY", "") or "").strip()
    state = "enabled" if url and api_key else "disabled"
    return MeiliConfig(state=state, url=url, api_key=api_key)


def falkor_config(values: Mapping[str, str]) -> FalkorConfig:
    url = str(values.get("XHS_FALKOR_URL", "") or "").strip()
    graph_name = str(values.get("XHS_FALKOR_GRAPH", "") or "").strip() or "xhs"
    state = "enabled" if url else "disabled"
    return FalkorConfig(state=state, url=url, graph_name=graph_name)


def meili_config_from_env() -> MeiliConfig:
    return meili_config({k: os.environ.get(k, "") for k in ("XHS_MEILI_URL", "XHS_MEILI_KEY")})


def falkor_config_from_env() -> FalkorConfig:
    return falkor_config({k: os.environ.get(k, "") for k in ("XHS_FALKOR_URL", "XHS_FALKOR_GRAPH")})
```

- [ ] **Step 4: 运行验证通过**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_engine_config.py -q`
Expected: PASS(5 passed)

- [ ] **Step 5: Commit**

```bash
git add data_foundation/engine_config.py tests/data_foundation/test_engine_config.py
git commit -m "feat(data-foundation): engine config snapshots for meili/falkor"
```

### Task 1.3: config_center 纳入引擎配置键(deploy-only)

**Files:**
- Modify: `config_center.py`
- Test: `tests/test_config_center.py`

- [ ] **Step 1: 写失败测试**

加到 `tests/test_config_center.py`:
```python
def test_engine_keys_are_deploy_only():
    from config_center import DEPLOY_ONLY_KEYS, SECRET_KEYS
    assert "XHS_MEILI_URL" in DEPLOY_ONLY_KEYS
    assert "XHS_MEILI_KEY" in DEPLOY_ONLY_KEYS
    assert "XHS_FALKOR_URL" in DEPLOY_ONLY_KEYS
    assert "XHS_FALKOR_GRAPH" in DEPLOY_ONLY_KEYS
    assert "XHS_MEILI_KEY" in SECRET_KEYS
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "E:/小红书智能体" && uv run pytest tests/test_config_center.py::test_engine_keys_are_deploy_only -q`
Expected: FAIL(AssertionError)

- [ ] **Step 3: 写实现**

`config_center.py` 的 `DEPLOY_ONLY_KEYS` 集合里加 4 项:
```python
    "XHS_MEILI_URL",
    "XHS_MEILI_KEY",
    "XHS_FALKOR_URL",
    "XHS_FALKOR_GRAPH",
```
`SECRET_KEYS` 集合里加:
```python
    "XHS_MEILI_KEY",
```

- [ ] **Step 4: 运行验证通过**

Run: `cd "E:/小红书智能体" && uv run pytest tests/test_config_center.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add config_center.py tests/test_config_center.py
git commit -m "feat(config): engine config keys are deploy-only secrets"
```

### Task 1.4: .env.example 文档化

**Files:**
- Modify: `.env.example`

- [ ] **Step 1: 在 .env.example 末尾加引擎配置段**

```bash
# 检索引擎(全文 Meilisearch + 图谱 FalkorDB)。Docker 本地服务,只绑 127.0.0.1。
# 配置就绪后对应 outbox processor 自动 active;留空则 disabled。
XHS_MEILI_URL=http://127.0.0.1:7700
XHS_MEILI_KEY=change-me-to-meili-master-key
XHS_FALKOR_URL=redis://127.0.0.1:6379
XHS_FALKOR_GRAPH=xhs
```

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "docs: document meili/falkor engine env in .env.example"
```

### Task 1.5: 服务器部署两个 Docker 服务 + 配 .env(服务器操作)

**Files:** 无代码改动(服务器运维 + 服务器 .env)

- [ ] **Step 1: 推送已完成的阶段1代码**

```bash
cd "E:/小红书智能体" && git -c http.proxy= -c https.proxy= push origin master
```

- [ ] **Step 2: 服务器拉取 + uv sync**

服务器执行(经 SSH paramiko 脚本):
```bash
cd /home/ubuntu/xiaohongshu-agent && git pull --ff-only origin master && uv sync 2>&1 | tail -3
```
Expected: pull 成功,uv sync 装上 meilisearch/falkordb

- [ ] **Step 3: 起 Meilisearch 容器**

服务器执行(master key 用 `python3 -c "import secrets;print(secrets.token_urlsafe(32))"` 生成):
```bash
docker run -d --name xhs-meili --restart unless-stopped \
  -p 127.0.0.1:7700:7700 \
  -e MEILI_MASTER_KEY=<生成的key> \
  -e MEILI_ENV=production \
  -v /home/ubuntu/meili-data:/meili_data \
  getmeili/meilisearch:v1.10
```
验证:`curl -s -H "Authorization: Bearer <key>" http://127.0.0.1:7700/health` → `{"status":"available"}`

- [ ] **Step 4: 起 FalkorDB 容器**

```bash
docker run -d --name xhs-falkor --restart unless-stopped \
  -p 127.0.0.1:6379:6379 \
  -v /home/ubuntu/falkor-data:/data \
  falkordb/falkordb:latest
```
验证:`docker exec xhs-falkor redis-cli ping` → `PONG`

- [ ] **Step 5: 写服务器 .env(备份后追加)**

服务器执行:
```bash
cd /home/ubuntu/xiaohongshu-agent && cp .env .env.bak.engines
# 追加 XHS_MEILI_URL / XHS_MEILI_KEY(=步骤3的key) / XHS_FALKOR_URL / XHS_FALKOR_GRAPH=xhs
```
不打印 key 值。验证:`grep -c '^XHS_MEILI_URL=' .env` == 1

- [ ] **Step 6: 重启后端使配置生效**

```bash
pm2 restart xhs-backend --update-env && sleep 12 && curl -s -m8 -o /dev/null -w 'ok=%{http_code}\n' http://127.0.0.1:2030/ok
```
Expected: `ok=200`

- [ ] **Step 7: 服务器验证两个 client 能连通**

服务器执行 Python(读 .env,连两个引擎):
```python
import os
from dotenv import load_dotenv; load_dotenv("/home/ubuntu/xiaohongshu-agent/.env")
import meilisearch, falkordb
m = meilisearch.Client(os.environ["XHS_MEILI_URL"], os.environ["XHS_MEILI_KEY"])
print("meili health:", m.health())
f = falkordb.FalkorDB.from_url(os.environ["XHS_FALKOR_URL"])
g = f.select_graph(os.environ["XHS_FALKOR_GRAPH"])
print("falkor query:", g.query("RETURN 1").result_set)
```
Expected: meili health available;falkor 返回 `[[1]]`


## 阶段 2:全文检索(Meili client + processor + search 切换 + 删 PG tsvector)

### Task 2.1: Meilisearch 薄封装 client

**Files:**
- Create: `data_foundation/meili_client.py`
- Test: `tests/data_foundation/test_meili_client.py`

- [ ] **Step 1: 写失败测试(mock meilisearch.Client)**

```python
# tests/data_foundation/test_meili_client.py
from unittest.mock import MagicMock
from data_foundation.meili_client import MeiliResourceIndex


def _index_with(mock_client):
    return MeiliResourceIndex(client=mock_client, index_uid="resources")


def test_ensure_index_sets_filterable_and_searchable():
    client = MagicMock()
    idx = _index_with(client)
    idx.ensure_index()
    client.index.assert_called_with("resources")
    index = client.index.return_value
    index.update_filterable_attributes.assert_called_once_with(["tenant_id", "type"])
    index.update_searchable_attributes.assert_called_once_with(["title", "summary", "content_text"])


def test_upsert_document_uses_resource_id_as_primary_key():
    client = MagicMock()
    idx = _index_with(client)
    idx.upsert({"resource_id": "r1", "tenant_id": "default", "type": "feishu_base_record",
                "title": "t", "summary": None, "content_text": "body"})
    index = client.index.return_value
    args, kwargs = index.add_documents.call_args
    assert args[0] == [{"resource_id": "r1", "tenant_id": "default", "type": "feishu_base_record",
                        "title": "t", "summary": None, "content_text": "body"}]
    assert kwargs.get("primary_key") == "resource_id"


def test_search_returns_ordered_ids_with_tenant_filter():
    client = MagicMock()
    index = client.index.return_value
    index.search.return_value = {"hits": [{"resource_id": "a"}, {"resource_id": "b"}]}
    idx = _index_with(client)
    ids = idx.search("减脂", tenant_id="default", limit=10)
    assert ids == ["a", "b"]
    args, kwargs = index.search.call_args
    assert args[0] == "减脂"
    assert kwargs["opt_params"]["filter"] == 'tenant_id = "default"'
    assert kwargs["opt_params"]["limit"] == 10
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_meili_client.py -q`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 写实现**

```python
# data_foundation/meili_client.py
from __future__ import annotations

from typing import Any

import meilisearch

from data_foundation.engine_config import MeiliConfig


class MeiliResourceIndex:
    SEARCHABLE = ["title", "summary", "content_text"]
    FILTERABLE = ["tenant_id", "type"]

    def __init__(self, *, client: Any, index_uid: str = "resources"):
        self.client = client
        self.index_uid = index_uid

    @classmethod
    def from_config(cls, config: MeiliConfig) -> "MeiliResourceIndex":
        client = meilisearch.Client(config.url, config.api_key)
        return cls(client=client)

    def ensure_index(self) -> None:
        index = self.client.index(self.index_uid)
        index.update_filterable_attributes(self.FILTERABLE)
        index.update_searchable_attributes(self.SEARCHABLE)

    def upsert(self, document: dict[str, Any]) -> None:
        self.client.index(self.index_uid).add_documents([document], primary_key="resource_id")

    def search(self, query: str, *, tenant_id: str, limit: int) -> list[str]:
        result = self.client.index(self.index_uid).search(
            query,
            opt_params={"filter": f'tenant_id = "{tenant_id}"', "limit": limit},
        )
        return [hit["resource_id"] for hit in result.get("hits", [])]
```

- [ ] **Step 4: 运行验证通过**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_meili_client.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add data_foundation/meili_client.py tests/data_foundation/test_meili_client.py
git commit -m "feat(data-foundation): meilisearch resource index client"
```

### Task 2.2: 新增 repository.readable_rows_by_ids(引擎结果回 PG 过权限+取元数据)

**Files:**
- Modify: `data_foundation/repository.py`
- Test: `tests/data_foundation/test_repository.py`

- [ ] **Step 1: 写失败测试(真实 PG,沿用 migrated_conn fixture)**

```python
# 加到 tests/data_foundation/test_repository.py
def test_readable_rows_by_ids_filters_and_preserves_order(migrated_conn):
    from data_foundation.repository import ResourceRepository
    repo = ResourceRepository(migrated_conn)
    a = repo.upsert_resource(tenant_id="default", actor_open_id="ou_x", resource_type="feishu_base_record",
        title="A", content_text="a", content_json={}, visibility="team", owner_open_id="ou_x")
    b = repo.upsert_resource(tenant_id="default", actor_open_id="ou_x", resource_type="feishu_base_record",
        title="B", content_text="b", content_json={}, visibility="team", owner_open_id="ou_x")
    # 引擎返回顺序 [b, a],权限过滤后保持该顺序
    rows = repo.readable_rows_by_ids(tenant_id="default", actor_open_id="ou_x", resource_ids=[b.id, a.id])
    assert [str(r["id"]) for r in rows] == [b.id, a.id]
    # 不可见资源被过滤
    c = repo.upsert_resource(tenant_id="default", actor_open_id="ou_other", resource_type="feishu_base_record",
        title="C", content_text="c", content_json={}, visibility="private", owner_open_id="ou_other")
    rows2 = repo.readable_rows_by_ids(tenant_id="default", actor_open_id="ou_x", resource_ids=[c.id, a.id])
    assert [str(r["id"]) for r in rows2] == [a.id]
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "E:/小红书智能体" && set -a && . ./.env && set +a && TEST_XHS_DATABASE_URL="$XHS_DATABASE_URL" uv run pytest tests/data_foundation/test_repository.py::test_readable_rows_by_ids_filters_and_preserves_order -q`
注:本地无 PG 会 skip;真实验证在服务器(见 Task 2.6)。本地至少确认不报 AttributeError 之外的收集错误。
Expected: FAIL 或 skip(方法不存在)

- [ ] **Step 3: 写实现(加到 ResourceRepository,放在 keyword_rows 原位置)**

```python
    def readable_rows_by_ids(self, *, tenant_id: str, actor_open_id: str, resource_ids: list[str]):
        if not resource_ids:
            return []
        ordering = {rid: i for i, rid in enumerate(resource_ids)}
        rows = self.conn.execute(
            f"""
            select r.*,
                   (
                     select max(rm.external_updated_at)
                     from resource_mappings rm
                     where rm.resource_id = r.id and rm.tenant_id = r.tenant_id
                   ) as source_updated_at,
                   1.0::real as score
            from resources r
            where r.id = any(%(ids)s::uuid[])
              and {readable_resource_where('r')}
            """,
            {"tenant_id": tenant_id, "actor_open_id": actor_open_id, "ids": resource_ids},
        ).fetchall()
        return sorted(rows, key=lambda row: ordering.get(str(row["id"]), len(ordering)))
```

- [ ] **Step 4: 提交(真实验证留待 Task 2.6 服务器)**

```bash
git add data_foundation/repository.py tests/data_foundation/test_repository.py
git commit -m "feat(data-foundation): readable_rows_by_ids preserves engine order with permission filter"
```

### Task 2.3: MeiliProcessor

**Files:**
- Create: `data_foundation/processors/meili.py`
- Test: `tests/data_foundation/test_meili_processor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/data_foundation/test_meili_processor.py
import asyncio
from unittest.mock import MagicMock
from data_foundation.processors.meili import MeiliProcessor
from data_foundation.processors.base import PermanentProcessingError
from data_foundation.models import OutboxItem
from datetime import datetime, timezone


def _item(payload):
    now = datetime.now(timezone.utc)
    return OutboxItem(id="i1", tenant_id="default", resource_id=payload.get("resource_id"),
        resource_version=payload.get("version"), topic="meili_index", dedupe_key="d",
        payload=payload, status="processing", attempts=1, next_attempt_at=now,
        lease_owner="w", lease_expires_at=now, error_code=None, error_summary=None,
        dead_at=None, created_at=now, updated_at=now)


class _Lease:
    async def assert_owned(self): return None


def test_state_disabled_when_no_config():
    from data_foundation.engine_config import MeiliConfig
    p = MeiliProcessor(conn=MagicMock(), index=MagicMock(), config=MeiliConfig(state="disabled", url="", api_key=""))
    assert p.state().status == "disabled"
    assert p.state().reason_code == "MEILI_CONFIG_MISSING"


def test_process_upserts_resource_document():
    from data_foundation.engine_config import MeiliConfig
    conn = MagicMock()
    conn.execute.return_value.fetchone.return_value = {
        "id": "r1", "tenant_id": "default", "type": "feishu_base_record",
        "title": "减脂笔记", "summary": None, "content_text": "正文"}
    index = MagicMock()
    p = MeiliProcessor(conn=conn, index=index, config=MeiliConfig(state="enabled", url="u", api_key="k"))
    result = asyncio.run(p.process(_item({"resource_id": "r1", "version": 1}), _Lease()))
    assert result.status == "succeeded"
    doc = index.upsert.call_args[0][0]
    assert doc["resource_id"] == "r1"
    assert doc["title"] == "减脂笔记"
    assert doc["tenant_id"] == "default"


def test_process_missing_resource_id_is_permanent():
    from data_foundation.engine_config import MeiliConfig
    p = MeiliProcessor(conn=MagicMock(), index=MagicMock(), config=MeiliConfig(state="enabled", url="u", api_key="k"))
    try:
        asyncio.run(p.process(_item({"version": 1}), _Lease()))
        assert False, "should raise"
    except PermanentProcessingError:
        pass
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_meili_processor.py -q`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 写实现**

```python
# data_foundation/processors/meili.py
from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.engine_config import MeiliConfig
from data_foundation.meili_client import MeiliResourceIndex
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


class MeiliProcessor:
    topic = "meili_index"

    def __init__(self, conn: Connection, *, index: MeiliResourceIndex | None, config: MeiliConfig):
        self.conn = conn
        self.conn.row_factory = dict_row
        self.index = index
        self.config = config

    def state(self) -> ProcessorState:
        if self.config.state != "enabled" or self.index is None:
            return ProcessorState(topic=self.topic, status="disabled",
                                  config_version=None, reason_code="MEILI_CONFIG_MISSING")
        return ProcessorState(topic=self.topic, status="active", config_version=None, reason_code=None)

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        if self.config.state != "enabled" or self.index is None:
            raise PermanentProcessingError("Meili config is missing")
        resource_id = str(item.payload.get("resource_id") or item.resource_id or "")
        if not resource_id:
            raise PermanentProcessingError("Meili outbox payload missing resource_id")
        row = self.conn.execute(
            """
            select id::text as id, tenant_id, type, title, summary, content_text
            from resources where tenant_id = %s and id = %s
            """,
            (item.tenant_id, resource_id),
        ).fetchone()
        if row is None:
            return ProcessResult(status="superseded")
        await lease.assert_owned()
        self.index.upsert({
            "resource_id": row["id"],
            "tenant_id": row["tenant_id"],
            "type": row["type"],
            "title": row["title"],
            "summary": row["summary"],
            "content_text": row["content_text"],
        })
        return ProcessResult(status="succeeded")
```

- [ ] **Step 4: 运行验证通过**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_meili_processor.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add data_foundation/processors/meili.py tests/data_foundation/test_meili_processor.py
git commit -m "feat(data-foundation): MeiliProcessor indexes resources into meilisearch"
```

### Task 2.4: 注册 MeiliProcessor 进 registry

**Files:**
- Modify: `data_foundation/processors/registry.py`
- Test: `tests/data_foundation/test_*`(沿用现有 registry 测试若有)

- [ ] **Step 1: 改 default_processor_registry**

把 `default_processor_registry` 改为同时注册 Meili(读 `meili_config_from_env`,enabled 才建 index):
```python
def default_processor_registry(
    conn: Connection,
    *,
    embedding_config: EmbeddingProviderConfig | None | object = _UNSET,
) -> ProcessorRegistry:
    if embedding_config is _UNSET:
        embedding_config = embedding_config_from_runtime()
    from data_foundation.engine_config import meili_config_from_env
    from data_foundation.meili_client import MeiliResourceIndex
    from data_foundation.processors.meili import MeiliProcessor

    meili_cfg = meili_config_from_env()
    meili_index = MeiliResourceIndex.from_config(meili_cfg) if meili_cfg.state == "enabled" else None
    return ProcessorRegistry(
        {
            "embedding_generate": EmbeddingProcessor(conn, config=embedding_config),
            "meili_index": MeiliProcessor(conn, index=meili_index, config=meili_cfg),
        }
    )
```

- [ ] **Step 2: 写/跑测试验证 meili_index 进 registry**

加测试 `tests/data_foundation/test_registry_engines.py`:
```python
from unittest.mock import MagicMock, patch
from data_foundation.processors.registry import default_processor_registry


def test_registry_includes_meili_when_configured():
    with patch.dict("os.environ", {"XHS_MEILI_URL": "http://x", "XHS_MEILI_KEY": "k"}):
        with patch("data_foundation.meili_client.meilisearch.Client", MagicMock()):
            reg = default_processor_registry(MagicMock(), embedding_config=None)
    assert "meili_index" in reg.topics
    assert reg.processor_for("meili_index") is not None
```

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_registry_engines.py -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add data_foundation/processors/registry.py tests/data_foundation/test_registry_engines.py
git commit -m "feat(data-foundation): register MeiliProcessor in default registry"
```

### Task 2.5: search_resources 切 Meili + 删 keyword_rows/keyword_search

**Files:**
- Modify: `data_foundation/tools.py`、`data_foundation/repository.py`、`data_foundation/search.py`
- Test: `tests/data_foundation/test_tools.py`、`test_search_graph_tools.py`

- [ ] **Step 1: 删 PG 全文代码**

删除 `data_foundation/repository.py` 的 `keyword_rows` 方法(272-320 行整块)。删除 `data_foundation/search.py` 的 `keyword_search` 函数(41-58 行)及不再被引用的 `_result_from_row` 里 keyword 专属分支(保留给 semantic 用的部分)。

- [ ] **Step 2: 改 tools.py 的 search_resources 与 semantic 的 fallback**

`search_resources` 改为查 Meili:
```python
@tool
def search_resources(query: str, limit: int = 10, config: RunnableConfig | None = None) -> dict[str, Any]:
    """Search readable resources by full-text (Meilisearch) and return summaries only."""
    actor = actor_from_config(config)
    from data_foundation.engine_config import meili_config_from_env
    from data_foundation.meili_client import MeiliResourceIndex
    cfg = meili_config_from_env()
    if cfg.state != "enabled":
        return {"ok": False, "error": "MEILI_UNAVAILABLE"}
    try:
        index = MeiliResourceIndex.from_config(cfg)
        ids = index.search(query.strip(), tenant_id=default_tenant_id(), limit=min(max(int(limit), 1), 20))
    except Exception as exc:
        return {"ok": False, "error": f"MEILI_QUERY_FAILED: {exc}"}
    with _repository() as repo:
        rows = repo.readable_rows_by_ids(tenant_id=default_tenant_id(), actor_open_id=actor, resource_ids=ids)
    return {"ok": True, "results": _rows_to_payload(rows)}
```
`semantic_search_resources` 当前 `active_index is None` 时 fallback 到 `keyword_search` —— 改为 fallback 到上面的 Meili search(调 `search_resources.func(query, top_k, config)` 复用),保持"语义不可用降级全文"语义不变(全文现在是 Meili,非 PG)。

新增 `_rows_to_payload`(从 PG row 构造 results,带 source_updated_at/indexed_at):
```python
def _rows_to_payload(rows: list[Any]) -> list[dict[str, Any]]:
    payload = []
    for row in rows:
        meta = {"type": row["type"], "visibility": row["visibility"]}
        if row.get("source_updated_at"): meta["source_updated_at"] = row["source_updated_at"].isoformat()
        if row.get("updated_at"): meta["indexed_at"] = row["updated_at"].isoformat()
        payload.append({"resource_id": str(row["id"]), "title": row["title"],
                        "summary": row["summary"], "score": float(row.get("score") or 0), "metadata": meta})
    return payload
```

- [ ] **Step 3: 重写受影响测试**

`test_search_graph_tools.py` / `test_tools.py` 里依赖 `keyword_search`/`keyword_rows` 的用例改为 mock Meili index(patch `data_foundation.tools.MeiliResourceIndex`)。删除断言 PG tsvector 行为的用例。新增:Meili 返回 ids → readable_rows_by_ids 过滤 → payload 顺序与 Meili 一致。

- [ ] **Step 4: 本地跑单测(mock,不连真实引擎)**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_tools.py tests/data_foundation/test_search_graph_tools.py -q`
Expected: PASS(改写后的用例)

- [ ] **Step 5: Commit**

```bash
git add data_foundation/tools.py data_foundation/repository.py data_foundation/search.py tests/data_foundation/
git commit -m "feat(data-foundation): search_resources via Meilisearch; remove PG tsvector"
```

### Task 2.6: 部署阶段2 + 服务器真实验证

**Files:** 无代码(部署+验证)

- [ ] **Step 1: 推送 + 服务器拉取重启**

```bash
git -c http.proxy= -c https.proxy= push origin master
# 服务器:git pull --ff-only && pm2 restart xhs-backend --update-env && sleep 12 && curl ok
```

- [ ] **Step 2: 服务器真实库跑 repository + tools 测试**

```bash
cd /home/ubuntu/xiaohongshu-agent && set -a && . ./.env && set +a && \
TEST_XHS_DATABASE_URL="$XHS_DATABASE_URL" ./.venv/bin/python3 -m pytest \
  tests/data_foundation/test_repository.py tests/data_foundation/test_meili_processor.py -q
```
Expected: PASS(含 readable_rows_by_ids 真实库用例)

- [ ] **Step 3: 服务器确认 meili processor active + ensure_index**

服务器 Python:`default_processor_registry(conn).state_for("meili_index").status` == "active";调 `MeiliResourceIndex.from_config(meili_config_from_env()).ensure_index()` 不报错。

- [ ] **Step 4: 等 scheduler 处理存量 meili_index 任务**

存量 ~508 个 meili_index blocked 任务,scheduler `unblock_available` 后转 pending 处理。等几分钟,服务器查:
```python
# resource_outbox where topic='meili_index' 的 status 分布,应 succeeded 递增
```
Expected: succeeded 增长,failed=0

- [ ] **Step 5: 服务器实测 Meili 检索命中真实数据**

服务器 Python:`search_resources.func(query="减脂", config=identity_config(admin))` → results 非空,title 含真实笔记。


## 阶段 3:图谱(Falkor client + processor + graph_expand 切换 + 删递归 SQL)

### Task 3.1: FalkorDB 薄封装 client

**Files:**
- Create: `data_foundation/falkor_client.py`
- Test: `tests/data_foundation/test_falkor_client.py`

- [ ] **Step 1: 写失败测试(mock falkordb graph)**

```python
# tests/data_foundation/test_falkor_client.py
from unittest.mock import MagicMock
from data_foundation.falkor_client import FalkorResourceGraph


def _graph_with():
    g = MagicMock()
    return FalkorResourceGraph(graph=g), g


def test_merge_node_uses_merge_with_id():
    fg, g = _graph_with()
    fg.merge_node({"id": "r1", "tenant_id": "default", "type": "feishu_base_record", "title": "T"})
    cypher, params = g.query.call_args[0][0], g.query.call_args[0][1]
    assert "MERGE" in cypher and ":Resource" in cypher
    assert params["id"] == "r1" and params["title"] == "T"


def test_merge_edge_merges_both_endpoints_as_placeholder():
    fg, g = _graph_with()
    fg.merge_edge(source_id="a", target_id="b", edge_type="derived_from", weight=1.0, properties={})
    cypher, params = g.query.call_args[0][0], g.query.call_args[0][1]
    # 两端都 MERGE(target 占位)+ 边 MERGE,共 >=3 个 MERGE
    assert cypher.count("MERGE") >= 3
    # edge_type 作参数传入(变长路径查询用统一 :REL 标签 + edge_type 属性)
    assert params["etype"] == "derived_from"
    assert params["sid"] == "a" and params["tid"] == "b"


def test_expand_returns_nodes_and_edges():
    fg, g = _graph_with()
    g.query.return_value.result_set = [["a", "T-a", "feishu_base_record", "b", "T-b", "feishu_base_record", "derived_from", 1.0]]
    nodes, edges = fg.expand(resource_ids=["a"], hops=1, edge_types=None, tenant_id="default")
    assert any(n["id"] == "a" for n in nodes)
    assert any(e["source"] == "a" and e["target"] == "b" for e in edges)
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_falkor_client.py -q`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 写实现**

```python
# data_foundation/falkor_client.py
from __future__ import annotations

from typing import Any

import falkordb

from data_foundation.engine_config import FalkorConfig


class FalkorResourceGraph:
    def __init__(self, *, graph: Any):
        self.graph = graph

    @classmethod
    def from_config(cls, config: FalkorConfig) -> "FalkorResourceGraph":
        client = falkordb.FalkorDB.from_url(config.url)
        return cls(graph=client.select_graph(config.graph_name))

    def merge_node(self, node: dict[str, Any]) -> None:
        self.graph.query(
            "MERGE (r:Resource {id: $id}) SET r.tenant_id=$tenant_id, r.type=$type, r.title=$title",
            {"id": node["id"], "tenant_id": node.get("tenant_id"),
             "type": node.get("type"), "title": node.get("title")},
        )

    def merge_edge(self, *, source_id: str, target_id: str, edge_type: str,
                   weight: float, properties: dict[str, Any]) -> None:
        # source 节点应已 merge_node;target 仅占位 MERGE(后续其任务补属性)
        self.graph.query(
            f"""
            MERGE (s:Resource {{id: $sid}})
            MERGE (t:Resource {{id: $tid}})
            MERGE (s)-[e:REL {{edge_type: $etype}}]->(t)
            SET e.weight = $weight
            """,
            {"sid": source_id, "tid": target_id, "etype": edge_type, "weight": weight},
        )

    def expand(self, *, resource_ids: list[str], hops: int, edge_types: list[str] | None,
               tenant_id: str) -> tuple[list[dict], list[dict]]:
        et_filter = ""
        params: dict[str, Any] = {"ids": resource_ids, "tenant": tenant_id}
        if edge_types:
            et_filter = "AND e.edge_type IN $etypes"
            params["etypes"] = edge_types
        rows = self.graph.query(
            f"""
            MATCH (s:Resource)-[e:REL*1..{hops}]->(t:Resource)
            WHERE s.id IN $ids AND s.tenant_id = $tenant AND t.tenant_id = $tenant
            UNWIND e as rel
            RETURN startNode(rel).id, startNode(rel).title, startNode(rel).type,
                   endNode(rel).id, endNode(rel).title, endNode(rel).type,
                   rel.edge_type, rel.weight
            """,
            params,
        ).result_set
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        for r in rows:
            sid, stitle, stype, tid, ttitle, ttype, etype, weight = r
            nodes[sid] = {"id": sid, "title": stitle, "type": stype}
            nodes[tid] = {"id": tid, "title": ttitle, "type": ttype}
            edges.append({"source": sid, "target": tid, "edge_type": etype, "weight": float(weight or 1.0)})
        return list(nodes.values()), edges
```

注:`merge_edge` 用统一关系标签 `:REL` + `edge_type` 属性(便于变长路径 `[e:REL*1..N]` 查询;Cypher 变长匹配不支持动态关系类型,故用属性区分)。`weight` 写入边属性,`properties` 参数当前 spec 范围内不展开存储(YAGNI;现存边 properties 均为空)。

- [ ] **Step 4: 运行验证通过**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_falkor_client.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add data_foundation/falkor_client.py tests/data_foundation/test_falkor_client.py
git commit -m "feat(data-foundation): falkordb resource graph client (merge nodes/edges, expand)"
```

### Task 3.2: GraphProcessor

**Files:**
- Create: `data_foundation/processors/graph.py`
- Test: `tests/data_foundation/test_graph_processor.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/data_foundation/test_graph_processor.py
import asyncio
from unittest.mock import MagicMock
from datetime import datetime, timezone
from data_foundation.processors.graph import GraphProcessor
from data_foundation.processors.base import PermanentProcessingError
from data_foundation.models import OutboxItem


def _item(payload):
    now = datetime.now(timezone.utc)
    return OutboxItem(id="i1", tenant_id="default", resource_id=payload.get("resource_id"),
        resource_version=payload.get("version"), topic="graph_ingest", dedupe_key="d",
        payload=payload, status="processing", attempts=1, next_attempt_at=now, lease_owner="w",
        lease_expires_at=now, error_code=None, error_summary=None, dead_at=None,
        created_at=now, updated_at=now)


class _Lease:
    async def assert_owned(self): return None


def test_state_disabled_without_config():
    from data_foundation.engine_config import FalkorConfig
    p = GraphProcessor(conn=MagicMock(), graph=MagicMock(), config=FalkorConfig(state="disabled", url="", graph_name="xhs"))
    assert p.state().status == "disabled"
    assert p.state().reason_code == "FALKOR_CONFIG_MISSING"


def test_process_merges_node_and_its_edges():
    from data_foundation.engine_config import FalkorConfig
    conn = MagicMock()
    # 第一次 fetchone 取节点;fetchall 取出边
    conn.execute.return_value.fetchone.return_value = {
        "id": "r1", "tenant_id": "default", "type": "feishu_base_record", "title": "T"}
    conn.execute.return_value.fetchall.return_value = [
        {"source_resource_id": "r1", "target_resource_id": "r2", "edge_type": "derived_from",
         "weight": 1.0, "properties": {}}]
    graph = MagicMock()
    p = GraphProcessor(conn=conn, graph=graph, config=FalkorConfig(state="enabled", url="u", graph_name="xhs"))
    result = asyncio.run(p.process(_item({"resource_id": "r1", "version": 1}), _Lease()))
    assert result.status == "succeeded"
    graph.merge_node.assert_called_once()
    graph.merge_edge.assert_called_once()
    assert graph.merge_edge.call_args.kwargs["edge_type"] == "derived_from"


def test_process_missing_resource_id_is_permanent():
    from data_foundation.engine_config import FalkorConfig
    p = GraphProcessor(conn=MagicMock(), graph=MagicMock(), config=FalkorConfig(state="enabled", url="u", graph_name="xhs"))
    try:
        asyncio.run(p.process(_item({"version": 1}), _Lease()))
        assert False
    except PermanentProcessingError:
        pass
```

- [ ] **Step 2: 运行验证失败**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_graph_processor.py -q`
Expected: FAIL(ModuleNotFoundError)

- [ ] **Step 3: 写实现**

```python
# data_foundation/processors/graph.py
from __future__ import annotations

from psycopg import Connection
from psycopg.rows import dict_row

from data_foundation.engine_config import FalkorConfig
from data_foundation.falkor_client import FalkorResourceGraph
from data_foundation.models import OutboxItem, ProcessorState
from data_foundation.processors.base import LeaseGuard, PermanentProcessingError, ProcessResult


class GraphProcessor:
    topic = "graph_ingest"

    def __init__(self, conn: Connection, *, graph: FalkorResourceGraph | None, config: FalkorConfig):
        self.conn = conn
        self.conn.row_factory = dict_row
        self.graph = graph
        self.config = config

    def state(self) -> ProcessorState:
        if self.config.state != "enabled" or self.graph is None:
            return ProcessorState(topic=self.topic, status="disabled",
                                  config_version=None, reason_code="FALKOR_CONFIG_MISSING")
        return ProcessorState(topic=self.topic, status="active", config_version=None, reason_code=None)

    async def process(self, item: OutboxItem, lease: LeaseGuard) -> ProcessResult:
        if self.config.state != "enabled" or self.graph is None:
            raise PermanentProcessingError("Falkor config is missing")
        resource_id = str(item.payload.get("resource_id") or item.resource_id or "")
        if not resource_id:
            raise PermanentProcessingError("Graph outbox payload missing resource_id")
        node = self.conn.execute(
            "select id::text as id, tenant_id, type, title from resources where tenant_id=%s and id=%s",
            (item.tenant_id, resource_id),
        ).fetchone()
        if node is None:
            return ProcessResult(status="superseded")
        edges = self.conn.execute(
            """
            select source_resource_id::text as source_resource_id,
                   target_resource_id::text as target_resource_id,
                   edge_type, weight, properties
            from resource_edges
            where tenant_id = %s and source_resource_id = %s
            """,
            (item.tenant_id, resource_id),
        ).fetchall()
        await lease.assert_owned()
        self.graph.merge_node({"id": node["id"], "tenant_id": node["tenant_id"],
                               "type": node["type"], "title": node["title"]})
        for e in edges:
            self.graph.merge_edge(source_id=e["source_resource_id"], target_id=e["target_resource_id"],
                                  edge_type=e["edge_type"], weight=float(e["weight"] or 1.0),
                                  properties=dict(e["properties"] or {}))
        return ProcessResult(status="succeeded")
```

- [ ] **Step 4: 运行验证通过**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_graph_processor.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add data_foundation/processors/graph.py tests/data_foundation/test_graph_processor.py
git commit -m "feat(data-foundation): GraphProcessor merges resource nodes/edges into falkordb"
```

### Task 3.3: 注册 GraphProcessor 进 registry

**Files:**
- Modify: `data_foundation/processors/registry.py`
- Test: `tests/data_foundation/test_registry_engines.py`

- [ ] **Step 1: 在 default_processor_registry 加 graph_ingest**

在 Task 2.4 改好的 registry 基础上,加 Falkor:
```python
    from data_foundation.engine_config import falkor_config_from_env
    from data_foundation.falkor_client import FalkorResourceGraph
    from data_foundation.processors.graph import GraphProcessor

    falkor_cfg = falkor_config_from_env()
    falkor_graph = FalkorResourceGraph.from_config(falkor_cfg) if falkor_cfg.state == "enabled" else None
```
并在返回的 dict 加:
```python
            "graph_ingest": GraphProcessor(conn, graph=falkor_graph, config=falkor_cfg),
```

- [ ] **Step 2: 加测试**

```python
# 加到 tests/data_foundation/test_registry_engines.py
def test_registry_includes_graph_when_configured():
    from unittest.mock import MagicMock, patch
    from data_foundation.processors.registry import default_processor_registry
    with patch.dict("os.environ", {"XHS_FALKOR_URL": "redis://x:6379", "XHS_FALKOR_GRAPH": "xhs"}):
        with patch("data_foundation.falkor_client.falkordb.FalkorDB", MagicMock()):
            reg = default_processor_registry(MagicMock(), embedding_config=None)
    assert "graph_ingest" in reg.topics
    assert reg.processor_for("graph_ingest") is not None
```

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_registry_engines.py -q`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add data_foundation/processors/registry.py tests/data_foundation/test_registry_engines.py
git commit -m "feat(data-foundation): register GraphProcessor in default registry"
```

### Task 3.4: graph_expand 切 Falkor + 删 graph_rows 递归 SQL

**Files:**
- Modify: `data_foundation/graph.py`、`data_foundation/repository.py`、`data_foundation/tools.py`
- Test: `tests/data_foundation/test_search_graph_tools.py`

- [ ] **Step 1: 删 repository.graph_rows**

删除 `data_foundation/repository.py` 的 `graph_rows` 方法整块(递归 SQL,约 449-521 行)。

- [ ] **Step 2: 改 graph.py expand_graph 查 Falkor + 回 PG 过权限**

```python
# data_foundation/graph.py
from __future__ import annotations

from data_foundation.models import GraphEdge, GraphExpansion, GraphNode


def expand_graph(
    repo,
    *,
    tenant_id: str,
    actor_open_id: str,
    resource_ids: list[str],
    hops: int = 1,
    edge_types: list[str] | None = None,
) -> GraphExpansion:
    safe_ids = [r.strip() for r in resource_ids if r.strip()]
    if not safe_ids:
        return GraphExpansion(nodes=[], edges=[])
    safe_edge_types = [e.strip() for e in edge_types if e.strip()] if edge_types else None
    from data_foundation.engine_config import falkor_config_from_env
    from data_foundation.falkor_client import FalkorResourceGraph
    cfg = falkor_config_from_env()
    if cfg.state != "enabled":
        raise RuntimeError("FALKOR_UNAVAILABLE")
    graph = FalkorResourceGraph.from_config(cfg)
    raw_nodes, raw_edges = graph.expand(
        resource_ids=safe_ids, hops=min(max(int(hops), 1), 3),
        edge_types=safe_edge_types, tenant_id=tenant_id,
    )
    # 回 PG 过权限:只保留 actor 可见的节点
    node_ids = [n["id"] for n in raw_nodes]
    visible = {str(row["id"]) for row in repo.readable_rows_by_ids(
        tenant_id=tenant_id, actor_open_id=actor_open_id, resource_ids=node_ids)}
    nodes = [GraphNode(resource_id=n["id"], title=n["title"], type=n["type"], depth=0)
             for n in raw_nodes if n["id"] in visible]
    edges = [GraphEdge(source_resource_id=e["source"], target_resource_id=e["target"],
                       edge_type=e["edge_type"], weight=e["weight"])
             for e in raw_edges if e["source"] in visible and e["target"] in visible]
    return GraphExpansion(nodes=nodes, edges=edges)
```
注:depth 简化为 0(原递归 SQL 算 depth;FalkorDB 变长路径可后续加,YAGNI 先不做)。`graph_expand` tool 错误处理:expand_graph 抛 RuntimeError 时 tool 返回 `{"ok": false, "error": ...}`。

- [ ] **Step 3: tools.py graph_expand 包错误处理**

`tools.py` 的 `graph_expand` 用 try/except 包 `expand_graph_query`,引擎不可用返回 `{"ok": False, "error": str(exc)}`。

- [ ] **Step 4: 重写图谱测试**

`test_search_graph_tools.py` 里图谱用例改为 mock `FalkorResourceGraph`(patch `data_foundation.graph.FalkorResourceGraph`),验证:expand 返回 nodes/edges → 回 PG 过权限 → 不可见节点/相关边被剔除。删递归 SQL 断言。

- [ ] **Step 5: 本地跑单测**

Run: `cd "E:/小红书智能体" && uv run pytest tests/data_foundation/test_search_graph_tools.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add data_foundation/graph.py data_foundation/repository.py data_foundation/tools.py tests/data_foundation/
git commit -m "feat(data-foundation): graph_expand via FalkorDB; remove recursive SQL"
```

### Task 3.5: 部署阶段3 + 服务器真实验证

**Files:** 无代码(部署+验证)

- [ ] **Step 1: 推送 + 服务器拉取重启**

```bash
git -c http.proxy= -c https.proxy= push origin master
# 服务器:git pull --ff-only && pm2 restart xhs-backend --update-env && sleep 12 && curl ok
```

- [ ] **Step 2: 服务器确认 graph processor active**

服务器 Python:`default_processor_registry(conn).state_for("graph_ingest").status` == "active"

- [ ] **Step 3: 等 scheduler 处理 graph_ingest 存量任务**

服务器查 `resource_outbox where topic='graph_ingest'` status 分布,succeeded 递增、failed=0。FalkorDB 里有节点:
```python
g.query("MATCH (r:Resource) RETURN count(r)").result_set  # 应接近 508
g.query("MATCH ()-[e:REL]->() RETURN count(e)").result_set  # 应 >= 7(derived_from)
```

- [ ] **Step 4: 服务器实测 graph_expand**

服务器 Python:取一个有 derived_from 边的 resource_id,`graph_expand.func(resource_ids=[rid], hops=1, config=identity_config(admin))` → nodes/edges 非空,权限过滤生效。


## 阶段 4:收尾(死代码清除 + 全链路端到端验证)

### Task 4.1: 删除 default_resource_requests 冗余 + 残留死代码

**Files:**
- Modify: `data_foundation/outbox_requests.py`、`tests/data_foundation/test_outbox_requests.py`
- Modify: `data_foundation/search.py`(清不再被引用的 helper)

- [ ] **Step 1: 删 default_resource_requests**

删除 `data_foundation/outbox_requests.py` 的 `default_resource_requests` 函数(仅测试引用)。保留 `default_write_requests`(被 6 处生产路径调用)、`search_index_request`、`graph_ingest_request`、`embedding_request`。

- [ ] **Step 2: 删对应测试**

`tests/data_foundation/test_outbox_requests.py` 删除 `test_default_resource_requests_*` 用例。

- [ ] **Step 3: 清 search.py 死 helper**

确认 `data_foundation/search.py` 中 `keyword_search` 已删(Task 2.5);若 `_result_from_row` / `validate_embedding` 仍被 `semantic_search` 引用则保留,否则删。`semantic_search` 函数保留(语义检索仍用)。

- [ ] **Step 4: 全量本地单测**

Run: `cd "E:/小红书智能体" && uv run pytest -q 2>&1 | tail -6`
Expected: 全 PASS(需 PG 的 skip),无 import 错误、无引用已删函数

- [ ] **Step 5: Commit**

```bash
git add data_foundation/outbox_requests.py data_foundation/search.py tests/data_foundation/test_outbox_requests.py
git commit -m "refactor(data-foundation): remove dead default_resource_requests and unused search helpers"
```

### Task 4.2: 清理早期缺 index_id 的 embedding 僵尸任务(服务器)

**Files:** 无代码(服务器受控数据清理)

- [ ] **Step 1: 服务器查是否仍有缺 index_id 的 embedding 任务**

服务器 Python(读 .env 连库):
```python
# select count(*) from resource_outbox where topic='embedding_generate'
#   and (payload->>'embedding_index_id') is null
```
若为 0,跳过此 Task。

- [ ] **Step 2: 定向 delete(仅当存在)**

```python
# delete from resource_outbox where topic='embedding_generate'
#   and (payload->>'embedding_index_id') is null
```
不裸 drop 表。删除前打印将删数量,确认后执行。

- [ ] **Step 3: 验证 embedding 索引仍 active**

服务器查 `embedding_indexes` status=active、completed=expected、failed=0(不受影响)。

### Task 4.3: 全链路端到端验证(服务器,浏览器)

**Files:** 无代码(端到端验证)

- [ ] **Step 1: 确认三个 processor 全 active**

服务器:`default_processor_registry(conn)` 的 `state_for` 对 embedding_generate / meili_index / graph_ingest 均 == "active"。

- [ ] **Step 2: 确认存量全部处理完**

服务器查 resource_outbox 三个 topic 的 status:succeeded 为主,无 blocked,failed=0。Meili 文档数 ≈ 508,FalkorDB 节点数 ≈ 508。

- [ ] **Step 3: 浏览器端到端(直接操作,CLAUDE.md 授权)**

浏览器 `http://124.221.173.80:9091`,发"帮我选两个健身减脂方向的选题":
- 思考轨迹:search_resources(走 Meili)✓、graph_expand(走 Falkor,若 agent 调用)✓
- 无 Blocking 错误、无 PermissionError
- agent 基于真实数据产出选题(带收藏/点赞依据)

- [ ] **Step 4: 引擎不可用降级验证(可选,确认无降级行为符合设计)**

服务器临时停 Meili 容器 → `search_resources` 返回 `{"ok": false, "error": "MEILI_UNAVAILABLE"}`(不回落 PG)。验证后重启容器:`docker start xhs-meili`。

- [ ] **Step 5: 更新 README/runbook 记录引擎已启用**

`README.md` 把"Meilisearch、Graphiti、Neo4j/FalkorDB 均 disabled/未启用"一句更新为:Meilisearch(全文)+ FalkorDB(图谱)已启用为检索/图谱唯一路径;PG tsvector/递归 SQL 已移除。`docs/deployment/server-deployment-rules.md` 第 2 节拓扑加两个容器(xhs-meili:7700、xhs-falkor:6379)。

- [ ] **Step 6: Commit + 推送**

```bash
git add README.md docs/deployment/server-deployment-rules.md
git commit -m "docs: mark Meilisearch + FalkorDB engines enabled; update topology"
git -c http.proxy= -c https.proxy= push origin master
```

---

## 验证清单(全部完成后)
- [ ] Meili + FalkorDB Docker 容器 running(--restart unless-stopped)
- [ ] 三 processor 全 active,存量 508 资源全部进 Meili + Falkor,failed=0
- [ ] search_resources 走 Meili、graph_expand 走 Falkor,均回 PG 过权限
- [ ] PG keyword_rows / graph_rows / keyword_search 已物理删除
- [ ] 引擎不可用时 tool 返回 ok:false(无 PG 降级)
- [ ] 浏览器端到端:agent 基于真实数据产出选题
- [ ] README/runbook 已更新



