# agent 只读运营数据工具(operations 领域层解耦)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 xhs_agent 能只读访问 6 类运营数据(analytics/calendar/pipeline/accounts/recents/trends),与 UI 同源同鉴权,经 deepagents `tools=` 挂钩;同时把读写共用辅助与只读聚合逻辑解耦到中立领域层。

**Architecture:** 三层解耦——基础层 `studio_shared.py`(读写共用辅助 + `is_admin_open_id`)← 领域层 `operations.py`(6 个 `load_*` 只读聚合)← 消费者(`studio_api.py` BFF 读/写、`tools.py` agent 工具)。新工具 `get_operations_data` 经 `data_foundation_tools` 列表进 `create_deep_agent(tools=)`,与现有工具同路。纯搬家不改逻辑,迁移每步跑测试验证行为不变。

**Tech Stack:** Python 3.11 / Starlette(内部路由)/ LangChain `@tool` + `RunnableConfig` / deepagents `create_deep_agent` / Postgres(psycopg)/ pytest。

## Global Constraints

- **真实数据铁律**:只读真实数据,禁止 mock 业务数据;数据不足返回真实空集合(`[]`/`{}`/0),不编造。
- **安全**:日志/错误/响应不得含密钥、token、Authorization、DSN、异常细节;错误摘要用固定文案 + 只记 `type(exc).__name__`。
- **鉴权口径 A**:agent 能读的 == 用户在 UI 能读的。矩阵总览(analytics/calendar/pipeline 不带 account、accounts)需 admin;单账号视图 + recents/trends 任意登录用户;recents 只读本人 open_id。
- **职责边界**:运营**写**(schedule/backfill/pipeline-advance)仍由 UI 用户动作触发,本计划不动写路径的对外行为。
- **行为零变化**:第 1-4 号迁移任务纯搬家,`tests/data_foundation/test_studio_api.py` 全程必须照过。
- **无循环 import**:`studio_shared` / `operations` 只依赖 `db`/`permissions`/`performance_feedback`/`repositories`/`outbox_requests`(底层),不依赖 `studio_api`/`internal_api`/`tools`。
- **服务器命令绕代理**:本地 push 用 `git -c http.proxy= -c https.proxy= push origin master`(若失败改用默认代理 `git push`,见项目 memory)。

---

### Task 1: 基础层 `studio_shared.py` — 共用辅助 + 鉴权判定

**Files:**
- Create: `data_foundation/studio_shared.py`
- Test: `tests/data_foundation/test_studio_shared.py`

**Interfaces:**
- Consumes: `data_foundation.db.connect`、`data_foundation.repositories.resource.ResourceRepository`(现有)
- Produces(后续任务依赖这些精确签名):
  - `is_admin_open_id(open_id: str) -> bool`
  - `repository()` — `@contextmanager`,yield `ResourceRepository`
  - `derive_stage(content: dict) -> str | None` — 仅认显式 `content["stage"]` ∈ `{scheduled,published,measured}`,否则 None
  - `existing_metric_content(repo, *, tenant_id: str, actor_open_id: str, metric_id: str | None) -> dict`
  - `day_of_month(value) -> int | None`
  - `now_iso() -> str`
  - `_PIPELINE_STAGES: tuple[str, ...] = ("scheduled", "published", "measured")`

- [ ] **Step 1: 写失败测试**

创建 `tests/data_foundation/test_studio_shared.py`:

```python
from data_foundation import studio_shared as ss


def test_is_admin_open_id(monkeypatch):
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin, ou_two")
    assert ss.is_admin_open_id("ou_admin") is True
    assert ss.is_admin_open_id("ou_two") is True
    assert ss.is_admin_open_id("ou_nobody") is False
    assert ss.is_admin_open_id("") is False


def test_is_admin_open_id_unset(monkeypatch):
    monkeypatch.delenv("XHS_ADMIN_OPEN_IDS", raising=False)
    assert ss.is_admin_open_id("ou_admin") is False


def test_derive_stage_explicit_only():
    assert ss.derive_stage({"stage": "scheduled"}) == "scheduled"
    assert ss.derive_stage({"stage": "published"}) == "published"
    assert ss.derive_stage({"stage": "measured"}) == "measured"
    # 无显式 stage → None(不做启发式回退)
    assert ss.derive_stage({"metrics": {"likes": 1}, "note_url": "u"}) is None
    assert ss.derive_stage({}) is None
    assert ss.derive_stage({"stage": "bogus"}) is None


def test_day_of_month():
    assert ss.day_of_month("2026-06-12") == 12
    assert ss.day_of_month("2026-6-1") is None  # 长度<10
    assert ss.day_of_month("bad") is None
    assert ss.day_of_month(None) is None


def test_now_iso_is_utc_iso():
    v = ss.now_iso()
    assert "T" in v and ("+00:00" in v or v.endswith("Z"))
```

- [ ] **Step 2: 跑测试验证失败**

Run: `uv run pytest tests/data_foundation/test_studio_shared.py -q`
Expected: FAIL(`ModuleNotFoundError: No module named 'data_foundation.studio_shared'`)

- [ ] **Step 3: 创建 `studio_shared.py`**

把 `studio_api.py` 现有实现原样搬入(去下划线为公开 API),`is_admin_open_id` 从 `internal_api._admin_open_ids` 逻辑抽取:

```python
"""studio 读写共用的底层辅助 + 鉴权判定(领域基础层)。

处于依赖底部:只依赖 db / repositories / performance_feedback,不依赖 studio_api /
internal_api / tools —— 供 operations(只读聚合)与 studio_api 写路径(_persist_*)共用,
杜绝辅助逻辑复制或跨层耦合。
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timezone

from data_foundation.db import connect
from data_foundation.repositories.resource import ResourceRepository

# 发布管线单向状态机:scheduled→published→measured,仅相邻正向可推进。
_PIPELINE_STAGES: tuple[str, ...] = ("scheduled", "published", "measured")


def is_admin_open_id(open_id: str) -> bool:
    """open_id 是否在 XHS_ADMIN_OPEN_IDS 白名单内。空/未设一律 False。"""
    if not open_id:
        return False
    admins = {
        item.strip()
        for item in os.environ.get("XHS_ADMIN_OPEN_IDS", "").split(",")
        if item.strip()
    }
    return open_id in admins


@contextmanager
def repository():
    """资源仓储上下文(connect→ResourceRepository→close),读写共用。"""
    conn = connect()
    try:
        yield ResourceRepository(conn)
    finally:
        conn.close()


def derive_stage(content: dict) -> str | None:
    """发布管线 stage = content_json 的显式 stage 字段(单一事实源)。

    只认写路径落的显式 stage;不对无显式 stage 的历史/外部指标做启发式推断,返回 None。
    """
    stage = content.get("stage")
    return stage if stage in _PIPELINE_STAGES else None


def existing_metric_content(repo, *, tenant_id: str, actor_open_id: str, metric_id: str | None) -> dict:
    """读既有 performance_metric.content_json(幂等合并用);无则空 dict。"""
    if not metric_id:
        return {}
    resource = repo.get_resource(tenant_id, actor_open_id, metric_id)
    return dict(resource.content_json or {}) if resource is not None else {}


def now_iso() -> str:
    """当前 UTC 时间 ISO 串(发布时间戳缺省值)。"""
    return datetime.now(timezone.utc).isoformat()


def day_of_month(value) -> int | None:
    """'YYYY-MM-DD' → 当月第几天(int);非法 → None。供日历按天分组。"""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return int(value[8:10])
    except ValueError:
        return None
```

> 实现前先 `grep -n "def _day_of_month" data_foundation/studio_api.py` 读现有 `_day_of_month` 完整实现(Step 3 里的是等价重写;若原实现有额外校验,以原实现为准逐字搬入)。

- [ ] **Step 4: 跑测试验证通过**

Run: `uv run pytest tests/data_foundation/test_studio_shared.py -q`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add data_foundation/studio_shared.py tests/data_foundation/test_studio_shared.py
git commit -m "feat(data_foundation): 新增 studio_shared 基础层(共用辅助+is_admin_open_id)"
```

<!-- PLAN_APPEND_MARKER_1 -->

---

### Task 2: 领域层 `operations.py` — 6 个只读聚合迁入

**Files:**
- Create: `data_foundation/operations.py`
- Modify: `data_foundation/studio_api.py`(删除迁走的 `_load_*` 及仅读路径用的私有辅助)
- Test: `tests/data_foundation/test_studio_api.py`(现有,验证迁移后行为不变)

**Interfaces:**
- Consumes: `data_foundation.studio_shared`(Task 1:`repository`、`derive_stage`、`existing_metric_content`、`day_of_month`、`now_iso`、`_PIPELINE_STAGES`)、`data_foundation.db.connect`、`data_foundation.permissions.default_tenant_id`
- Produces(后续任务依赖):
  - `load_analytics(*, tenant_id: str, account: str | None) -> dict`
  - `load_calendar(*, tenant_id: str, account: str | None) -> dict`
  - `load_pipeline(*, tenant_id: str, account: str | None) -> list[dict]`
  - `load_accounts(*, tenant_id: str) -> dict`
  - `load_recents(*, tenant_id: str, open_id: str) -> list[dict]`
  - `load_trends(*, tenant_id: str) -> list[dict]`

- [ ] **Step 1: 读取现有实现全文(不改逻辑,精确搬家)**

Run: `sed -n '82,540p' data_foundation/studio_api.py`
读出这些函数完整实现,准备逐字迁移(纯搬家,行为不变):
- 只读聚合:`_load_analytics`(279)、`_load_schedule_items`(320)、`_load_calendar`(369)、`_load_accounts`(378)、`_load_pipeline`(386)、`_load_recents`(450)、`_load_trends`(495)
- 仅读路径用的辅助:`_compact_number`(82)、`_as_datetime`(97)、`_format_dt`(112)、`_delta_pct`(118)、`_format_schedule_time`(140)、`_build_dashboard`(176)、`_build_library_and_teardown`(214)

- [ ] **Step 2: 创建 `operations.py`,迁入并公开 6 个聚合**

创建 `data_foundation/operations.py`,把上述实现搬入。6 个入口去下划线(`_load_analytics`→`load_analytics` 等),内部辅助保持下划线(私有于本模块)。共用辅助改从 `studio_shared` import,不再本地定义:

```python
"""studio 运营数据只读聚合(领域层,唯一真源)。

被 studio_api 的 BFF 读 handler 与 tools.py 的 agent 工具共同消费;不依赖二者(无横向耦合)。
纯读:只查真实数据,数据不足返回真实空集合,不 mock。
"""
from __future__ import annotations

import calendar as _calendar
from datetime import date, datetime, timedelta, timezone

from data_foundation.db import connect
from data_foundation.studio_shared import (
    _PIPELINE_STAGES,
    day_of_month,
    derive_stage,
)

# ↓↓↓ 从 studio_api.py 逐字搬入(仅把 _load_* 6 个入口去下划线为 load_*;
#     内部对 _day_of_month/_derive_stage 的调用改为 day_of_month/derive_stage):
#   _compact_number / _as_datetime / _format_dt / _delta_pct / _format_schedule_time /
#   _build_dashboard / _build_library_and_teardown /
#   load_analytics / _load_schedule_items / load_calendar / load_accounts /
#   load_pipeline / load_recents / load_trends
```

> 注意迁移时的引用改名:原 `_load_calendar` 内调 `_load_schedule_items` 保持(都在本模块);原调 `_day_of_month`→`day_of_month`、`_derive_stage`→`derive_stage`(来自 studio_shared)。`load_pipeline` 的 docstring 删掉过时的「兼容飞书同步历史指标的启发式回退」描述(该逻辑上一轮已删)。

- [ ] **Step 3: studio_api.py 删除迁走的实现,改为 import**

在 `data_foundation/studio_api.py`:
1. 删除 Step 1 列出的 7 个聚合 + 7 个只读辅助的定义。
2. 顶部加:`from data_foundation.operations import (load_analytics, load_calendar, load_pipeline, load_accounts, load_recents, load_trends)`
3. 各 `internal_studio_*` handler 里 `_load_analytics(...)`→`load_analytics(...)` 等改名(6 处)。
4. `studio_api` 自己的 `_repository`/`_derive_stage`/`_existing_metric_content`/`_day_of_month`/`_now_iso` 定义**暂不删**(Task 3 处理写路径时再切到 studio_shared)。

- [ ] **Step 4: 跑迁移回归(行为不变)**

Run: `uv run pytest tests/data_foundation/test_studio_api.py -q`
Expected: PASS(全部照过,行为零变化)

- [ ] **Step 5: 提交**

```bash
git add data_foundation/operations.py data_foundation/studio_api.py
git commit -m "refactor(data_foundation): 6 个只读运营聚合迁入 operations 领域层"
```

<!-- PLAN_APPEND_MARKER_2 -->

---

### Task 3: 写路径 `_persist_*` 切到 studio_shared 共用辅助

**Files:**
- Modify: `data_foundation/studio_api.py`(写路径改用 studio_shared;删除本地重复的共用辅助定义)
- Test: `tests/data_foundation/test_studio_api.py`(现有,写路径测试验证行为不变)

**Interfaces:**
- Consumes: `data_foundation.studio_shared`(`repository`、`derive_stage`、`existing_metric_content`、`day_of_month`、`now_iso`、`_PIPELINE_STAGES`)
- Produces: 无新增对外接口(内部重构)

- [ ] **Step 1: studio_api.py 顶部引入 studio_shared 共用辅助**

在 `data_foundation/studio_api.py` 顶部 import 区加:

```python
from data_foundation.studio_shared import (
    _PIPELINE_STAGES,
    day_of_month,
    derive_stage,
    existing_metric_content,
    is_admin_open_id,
    now_iso,
    repository as _repository,
)
```

(用 `as _repository` 保持写路径调用点 `with _repository() as repo:` 不必改。)

- [ ] **Step 2: 删除 studio_api.py 里被 studio_shared 取代的本地定义**

删除这些本地定义(现已由 studio_shared 提供,写路径 `_persist_*` 与 `_is_uuid`/handler 改用 import 的):
- `_repository`(64)、`_derive_stage`(148)、`_existing_metric_content`(158)、`_now_iso`(125)、`_day_of_month`(130)、模块顶部本地的 `_PIPELINE_STAGES` 常量定义。
- 写路径调用点:`_derive_stage(...)`→`derive_stage(...)`、`_existing_metric_content(...)`→`existing_metric_content(...)`、`_now_iso()`→`now_iso()`、`_day_of_month(...)`→`day_of_month(...)`(逐处改名;`_repository` 经 `as` 别名无需改)。

- [ ] **Step 3: 跑写路径回归**

Run: `uv run pytest tests/data_foundation/test_studio_api.py tests/data_foundation/test_performance_feedback_metrics_property.py -q`
Expected: PASS(schedule/backfill/pipeline-advance 写路径行为不变)

- [ ] **Step 4: 全量后端回归 + 导入 smoke**

Run: `uv run pytest tests/data_foundation -q`
Expected: PASS(全绿,迁移不破坏任何既有测试)

- [ ] **Step 5: 提交**

```bash
git add data_foundation/studio_api.py
git commit -m "refactor(data_foundation): studio_api 写路径改用 studio_shared 共用辅助(消重)"
```

<!-- PLAN_APPEND_MARKER_3 -->

---

### Task 4: internal_api 复用 `is_admin_open_id`(单一鉴权真源)

**Files:**
- Modify: `data_foundation/internal_api.py`(`_admin_open_ids`/`_actor_from_request` 改用 studio_shared)
- Test: `tests/data_foundation/test_internal_api.py`、`tests/data_foundation/test_studio_api.py`(现有,鉴权行为不变)

**Interfaces:**
- Consumes: `data_foundation.studio_shared.is_admin_open_id`
- Produces: 无新增(内部收敛)

- [ ] **Step 1: internal_api.py 用 studio_shared.is_admin_open_id 收敛 admin 判定**

在 `data_foundation/internal_api.py`:
1. 顶部加 `from data_foundation.studio_shared import is_admin_open_id`。
2. 删除本地 `_admin_open_ids()`(48-53)。
3. `_actor_from_request`(76)里 `is_admin = bool(open_id and open_id in _admin_open_ids())` 改为 `is_admin = is_admin_open_id(open_id)`。

- [ ] **Step 2: 跑鉴权回归**

Run: `uv run pytest tests/data_foundation/test_internal_api.py tests/data_foundation/test_studio_api.py -q`
Expected: PASS(admin/user 判定行为不变,含矩阵总览 require_admin 用例)

- [ ] **Step 3: 提交**

```bash
git add data_foundation/internal_api.py
git commit -m "refactor(data_foundation): internal_api 复用 studio_shared.is_admin_open_id"
```

---

### Task 5: agent 工具 `get_operations_data`(deepagents tools= 挂钩)

**Files:**
- Modify: `data_foundation/tools.py`(新增 `@tool get_operations_data` + 加进 `data_foundation_tools` 列表)
- Test: `tests/data_foundation/test_operations.py`(新建)

**Interfaces:**
- Consumes: `data_foundation.operations`(Task 2 的 6 个 `load_*`)、`data_foundation.studio_shared.is_admin_open_id`、`data_foundation.permissions`(`default_tenant_id`、`actor_from_config`)、`langchain_core.tools.tool`、`langchain_core.runnables.RunnableConfig`
- Produces:
  - `get_operations_data(view: str, account: str | None = None, config: RunnableConfig | None = None) -> dict`
  - 加入 `data_foundation_tools` 列表(agent 经 `create_deep_agent(tools=)` 自动获得)

- [ ] **Step 1: 写失败测试**

创建 `tests/data_foundation/test_operations.py`(直接测工具函数;monkeypatch `operations.load_*` 隔离 DB,聚合本身已由 test_studio_api 覆盖):

```python
import data_foundation.tools as tools
import data_foundation.operations as ops


def _cfg(open_id: str):
    # 与现有工具一致:actor_from_config 从 configurable.langgraph_auth_user 解析可信身份。
    return {"configurable": {"langgraph_auth_user": {"identity": open_id}}}


def _patch_loads(monkeypatch):
    monkeypatch.setattr(ops, "load_analytics", lambda *, tenant_id, account: {"dashboard": [], "library": [], "teardown": {"title": "", "points": []}})
    monkeypatch.setattr(ops, "load_calendar", lambda *, tenant_id, account: {"month": {"label": "x", "days": 30, "firstOffset": 0}, "calendar": []})
    monkeypatch.setattr(ops, "load_pipeline", lambda *, tenant_id, account: [])
    monkeypatch.setattr(ops, "load_accounts", lambda *, tenant_id: {"accounts": [], "overview": {"totalFans": 0, "weekNewFans": 0, "weekPosts": 0, "avgHotRate": 0}})
    monkeypatch.setattr(ops, "load_recents", lambda *, tenant_id, open_id: [])
    monkeypatch.setattr(ops, "load_trends", lambda *, tenant_id: [])


def _invoke(view, account=None, open_id="ou_user"):
    # @tool 包装后用 .func 取原函数直测(不经 agent runtime)。
    return tools.get_operations_data.func(view=view, account=account, config=_cfg(open_id))


def test_single_account_views_allow_any_user(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    for view in ("analytics", "calendar", "pipeline"):
        out = _invoke(view, account="acc_1", open_id="ou_user")
        assert out["ok"] is True and out["view"] == view


def test_recents_and_trends_allow_any_user(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    assert _invoke("recents", open_id="ou_user")["ok"] is True
    assert _invoke("trends", open_id="ou_user")["ok"] is True


def test_matrix_overview_requires_admin(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    # 普通用户读矩阵总览(不带 account)/accounts → 被拒,返回权限提示(非报错、不含数据)
    for view in ("analytics", "calendar", "pipeline", "accounts"):
        out = _invoke(view, account=None, open_id="ou_user")
        assert out["ok"] is False
        assert "admin" in out["error"].lower() or "管理员" in out["error"]
        assert "dashboard" not in out and "accounts" not in out and "queue" not in out


def test_matrix_overview_allows_admin(monkeypatch):
    _patch_loads(monkeypatch)
    monkeypatch.setenv("XHS_ADMIN_OPEN_IDS", "ou_admin")
    for view in ("analytics", "calendar", "pipeline", "accounts"):
        out = _invoke(view, account=None, open_id="ou_admin")
        assert out["ok"] is True


def test_unknown_view_rejected(monkeypatch):
    _patch_loads(monkeypatch)
    out = _invoke("bogus", open_id="ou_user")
    assert out["ok"] is False and "view" in out["error"].lower()
```

> 实现前先 `grep -n "def actor_from_config\|langgraph_auth_user\|identity" data_foundation/permissions.py` 确认 `_cfg` 里 configurable 的确切结构;若现有测试用别的构造(如直接 `configurable.open_id`),以现有 tools 测试的构造为准对齐 `_cfg`。

- [ ] **Step 2: 跑测试验证失败**

Run: `uv run pytest tests/data_foundation/test_operations.py -q`
Expected: FAIL(`AttributeError: module 'data_foundation.tools' has no attribute 'get_operations_data'`)

- [ ] **Step 3: 实现 `get_operations_data` 工具**

在 `data_foundation/tools.py` 加(import 区补 `from data_foundation import operations as ops` 与 `from data_foundation.studio_shared import is_admin_open_id`):

```python
@tool
def get_operations_data(
    view: str,
    account: str | None = None,
    config: RunnableConfig | None = None,
) -> dict[str, Any]:
    """读取账号运营数据(只读,与运营看板 UI 同源、同鉴权)。

    view: analytics(数据看板/选题库/爆款拆解) | calendar(内容日历/排期) |
          pipeline(发布管线) | accounts(账号矩阵) | recents(我的最近创作) | trends(热点趋势)。
    account: 单账号过滤;不传=矩阵总览(analytics/calendar/pipeline/accounts 的矩阵总览需管理员)。
    数据为空即真实无数据,不编造。
    """
    actor = actor_from_config(config)
    tenant = default_tenant_id()
    admin = is_admin_open_id(actor)
    account = account.strip() if isinstance(account, str) and account.strip() else None

    # 鉴权口径 A:矩阵总览(不带 account)与 accounts 需 admin;单账号/recents/trends 任意用户。
    needs_admin = (account is None and view in ("analytics", "calendar", "pipeline")) or view == "accounts"
    if needs_admin and not admin:
        return {"ok": False, "error": "该视图为跨账号矩阵总览,需管理员权限;请指定 account 查看单账号,或联系管理员。"}

    if view == "analytics":
        return {"ok": True, "view": view, "account": account, **ops.load_analytics(tenant_id=tenant, account=account)}
    if view == "calendar":
        return {"ok": True, "view": view, "account": account, **ops.load_calendar(tenant_id=tenant, account=account)}
    if view == "pipeline":
        return {"ok": True, "view": view, "account": account, "queue": ops.load_pipeline(tenant_id=tenant, account=account)}
    if view == "accounts":
        return {"ok": True, "view": view, **ops.load_accounts(tenant_id=tenant)}
    if view == "recents":
        return {"ok": True, "view": view, "recents": ops.load_recents(tenant_id=tenant, open_id=actor)}
    if view == "trends":
        return {"ok": True, "view": view, "trends": ops.load_trends(tenant_id=tenant)}
    return {"ok": False, "error": f"unknown view '{view}';合法值:analytics/calendar/pipeline/accounts/recents/trends。"}
```

然后把 `get_operations_data` 加进 `data_foundation_tools` 列表(在 `get_resource_performance` 之后一行)。

- [ ] **Step 4: 跑测试验证通过**

Run: `uv run pytest tests/data_foundation/test_operations.py -q`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add data_foundation/tools.py tests/data_foundation/test_operations.py
git commit -m "feat(agent): 新增 get_operations_data 只读工具(经 data_foundation_tools 挂钩 deepagents)"
```

<!-- PLAN_APPEND_MARKER_4 -->

---

### Task 6: prompts.py 指引 + agent 装配 smoke

**Files:**
- Modify: `prompts.py`(§4 存储路由与权威性 附近,补运营数据读取指引)
- Test: 装配 smoke(import agent,确认工具入列、无 harness/装配报错)

**Interfaces:**
- Consumes: Task 5 的 `get_operations_data`(已进 `data_foundation_tools`)
- Produces: 无(文档 + 验证)

- [ ] **Step 1: prompts.py 补运营数据读取指引**

在 `prompts.py` 的 §4(存储路由与权威性,约 45 行)后补一句(工具名仅内部可见,不对用户暴露——遵守 §0 表达规约):

```
运营数据只读:用户问及数据表现/看板/排期/发布状态/账号矩阵/最近创作/热点趋势时,用 `get_operations_data(view, account?)` 取**真实**数据再回答(view: analytics/calendar/pipeline/accounts/recents/trends)。矩阵总览(不带 account)与 accounts 需管理员权限,普通用户被拒时如实转告"需管理员权限",不要伪造数据;数据为空即如实说"当前暂无数据"。此工具只读,不做排期/回填等写操作——写操作由用户在运营看板界面自行完成。
```

- [ ] **Step 2: agent 装配 smoke — 工具入列且装配无错**

Run:
```bash
uv run python -c "import agent; names=[getattr(t,'name',getattr(t,'__name__','')) for t in agent.assembled_tools]; print('get_operations_data in tools:', 'get_operations_data' in names); print('tool count:', len(names))"
```
Expected: 打印 `get_operations_data in tools: True`,tool count 比原来多 1(14);无 `No harness profile matched`、无 traceback。

- [ ] **Step 3: 运行时导入 smoke(容器口径一致性)**

Run: `uv run python scripts/runtime_import_smoke.py`
Expected: `agent=OK`、`data_foundation.http_app=OK` 等全 OK(operations/studio_shared 新模块可导入,无循环 import)。

- [ ] **Step 4: 全量后端回归收尾**

Run: `uv run pytest tests/data_foundation -q`
Expected: PASS(全绿)

- [ ] **Step 5: 提交**

```bash
git add prompts.py
git commit -m "feat(agent): prompts 补运营数据只读指引(get_operations_data)"
```

---

## 部署与验证(全部任务完成后)

- [ ] **本地发布前门**:`cd web`(本任务未动 web,可跳 web 门);后端 `uv run pytest tests/data_foundation -q` + `git diff --check`。
- [ ] **推送**:`git -c http.proxy= -c https.proxy= push origin master`(失败改默认代理 `git push`)。
- [ ] **部署**:`uv run python scripts/deploy.py`(pull → langgraph build → compose up → 健康检查 + smoke)。
- [ ] **生产验证**:登录后在对话里问「我最近创作了哪些」→ agent 应调 `get_operations_data(view=recents)` 返回真实最近创作;普通用户问「所有账号的矩阵总览」→ agent 转告需管理员权限(不编造)。

---

## Self-Review(写完计划后自查)

**1. Spec 覆盖**:
- §1 studio_shared → Task 1 ✅
- §2 operations 6 聚合 → Task 2 ✅
- §3 写路径切共用辅助 → Task 3 ✅
- §4 BFF 读 handler 改 import → Task 2 Step 3 ✅
- §5 工具 + §5.1 tools= 挂钩 → Task 5 ✅
- §6 鉴权口径 A → Task 5 Step 3(needs_admin 判定)+ Task 5 测试 ✅
- §7 prompts → Task 6 ✅
- 测试(test_operations + test_studio_api 照过)→ Task 5 + 各任务回归 ✅
- 风险(迁移行为不变、无循环 import)→ 每迁移任务跑 test_studio_api + Task 6 runtime smoke ✅

**2. 占位符扫描**:无 TBD/TODO;每个 code step 有完整代码;测试有真实断言。两处 `>` 注解要求实现者先读现有代码对齐(day_of_month 原实现、actor_from_config 的 config 结构)——这是**降低风险的核对指令**,非占位。

**3. 类型一致性**:
- `is_admin_open_id(open_id: str) -> bool`:Task 1 定义,Task 4/5 调用一致 ✅
- `load_*` 签名:Task 2 Produces 与 Task 5 调用一致(`load_analytics(tenant_id=, account=)`、`load_recents(tenant_id=, open_id=)`、`load_trends(tenant_id=)`)✅
- `repository`/`derive_stage`/`existing_metric_content`/`day_of_month`/`now_iso`:Task 1 定义,Task 3 写路径 import 名一致 ✅
- `get_operations_data(view, account?, config?) -> dict`:Task 5 定义与测试 `.func(...)` 调用一致 ✅




