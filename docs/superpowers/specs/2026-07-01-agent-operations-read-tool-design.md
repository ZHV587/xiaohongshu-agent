# 设计:agent 只读运营数据工具(operations 领域层解耦)

日期:2026-07-01
状态:已批准,待实现

## 背景与问题

studio 有两条数据平面:

- **平面 A(创作对话)**:前端 `stream.submit` → `xhs_agent`(deepagents `create_deep_agent`)→ 工具
  (search/save_generated_*)→ agent 用 `xhs_topics`/`xhs_copy` 代码块输出 → 前端解析卡片。
  **基于 deepagents 框架,对接正确,不动。**
- **平面 B(运营数据)**:前端 `useBackendResource` → BFF `/api/backend/{analytics,calendar,pipeline,
  accounts,recents,trends,schedule,backfill,pipeline}` → `data_foundation/studio_api.py` 的 `_load_*`
  聚合直查 Postgres。

问题:**agent 读不到运营数据**。它的读工具只有 `get_resource_performance(resource_id)`(单条),
没有聚合看板/日历/管线/账号矩阵/最近创作/趋势的能力。用户问「上周哪篇数据最好」「排期有没有冲突」
时,agent 无从访问。

## 目标与非目标

**目标**:让 agent 能**只读**访问 6 类运营数据,与 UI **同源、同鉴权口径**,辅助创作决策。

**非目标(YAGNI)**:
- 不给 agent 运营**写**能力。排期/回填/推进 stage 仍由**用户在 UI 上直接操作**(BFF 写路径不动)。
  职责边界:**写 = UI 用户动作;读 = UI + agent 共享同源。**
- 不为恒空的 accounts/trends 造假数据。
- 不动创作对话平面 A。

## 核心原则:职责分清、解耦清楚

当前 `_load_*` 聚合逻辑私有于 `studio_api.py`(BFF 路由层)。若 agent 工具层直接 import 它,
则「agent 工具」耦合到「BFF 路由模块」,且跨层引用私有下划线函数,是坏味道。

**解耦方案**:新建中立领域层 `data_foundation/operations.py`,把聚合逻辑 + 鉴权判定下沉。
BFF 路由与 agent 工具都作为它的**消费者**,互不依赖:

```
        data_foundation/operations.py   ← 领域层(聚合 + 鉴权判定,唯一真源)
          ↑                    ↑
  studio_api.py(BFF 路由)   tools.py(agent 工具 get_operations_data)
          ↑                    ↑
  /api/backend/*(UI 用户)   xhs_agent(对话内只读)
```

三层清晰、无横向耦合;UI 和 agent 看到完全同一份数据,杜绝两套逻辑漂移。

## 详细设计

### 1. 领域层 `data_foundation/operations.py`(新建)

从 `studio_api.py` 迁入(行为不变,仅搬家 + 改引用):

- `load_analytics(*, tenant_id, account)` — 数据看板 + 选题库 + 爆款拆解
- `load_calendar(*, tenant_id, account)` — 月份 + 排期项
- `load_pipeline(*, tenant_id, account)` — 发布管线队列(单向状态机 stage)
- `load_accounts(*, tenant_id)` — 账号矩阵 + 聚合(当前恒空,数据底座无账号实体)
- `load_recents(*, tenant_id, open_id)` — 登录用户最近创作(倒序)
- `load_trends(*, tenant_id)` — 热点趋势(当前恒空,无外部源)
- 连带迁入其私有辅助:`_derive_stage`、`_load_schedule_items`、`_build_dashboard` 等(只被这些用到的)。

新增鉴权 helper(领域层中立,不依赖 HTTP request):
- `is_admin_open_id(open_id: str) -> bool` — 读 `XHS_ADMIN_OPEN_IDS` 判定(供 UI 与 agent 共用,
  取代 internal_api 里内联的 `_admin_open_ids()` 判定,internal_api 改为复用它)。

命名:迁出后去掉下划线(`load_*` 公开),因为现在是领域层的公开 API。

### 2. BFF 路由 `studio_api.py`(改为消费者)

- 删除迁走的 `_load_*` 实现,改为 `from data_foundation.operations import load_analytics, ...`。
- 各 `internal_studio_*` handler 调用点改名(`_load_analytics` → `load_analytics`)。
- **HTTP 鉴权逻辑不变**(仍 require_admin/require_user,底层复用 `is_admin_open_id`)。
- 行为零变化,现有 `test_studio_api.py` 全部照过。

### 3. agent 工具 `data_foundation/tools.py`(新增消费者)

新增工具:

```python
@tool
def get_operations_data(view: str, account: str | None = None,
                        config: RunnableConfig | None = None) -> dict:
    """读取账号运营数据(只读,与运营看板 UI 同源)。
    view: analytics(数据看板) | calendar(内容日历/排期) | pipeline(发布管线) |
          accounts(账号矩阵) | recents(最近创作) | trends(热点趋势)。
    account: 单账号过滤;不传=矩阵总览(需管理员)。"""
```

- 身份:`actor_from_config(config)` 拿可信 open_id。
- 分发:按 `view` 调对应 `operations.load_*`。
- 加进 `data_foundation_tools` 列表,agent 自动获得。

### 4. 鉴权口径(A:agent 能读 == 用户 UI 能读)

工具内部复用与 UI 完全相同的判定:

| view / 条件 | 鉴权 | 非法时 |
|---|---|---|
| analytics/calendar/pipeline 不带 account(矩阵总览) | 需 admin | 返回明确「需管理员权限」提示(非空、非报错,让 agent 转告用户) |
| accounts(总览) | 需 admin | 同上 |
| analytics/calendar/pipeline 带 account(单账号) | 任意登录用户 | — |
| recents | 任意用户,只读自己(open_id) | — |
| trends | 任意用户 | — |

杜绝借 agent 越权:普通用户让 agent 读矩阵总览 → agent 收到「需管理员权限」→ 转告用户,
不返回他人数据。

### 5. prompts.py

给主 agent 补充:用户问及运营/数据表现/排期/发布状态/账号矩阵时,调 `get_operations_data`
获取真实数据再回答;数据为空时如实说明,不编造。

## 测试

- 新增 `tests/data_foundation/test_operations.py`:
  - 6 个 view 都能经工具调到、返回对应 `load_*` 结果。
  - 鉴权:普通用户读矩阵总览被拒(返回权限提示)、admin 可读、单账号任意用户可读、recents 只读自己。
  - 空态:accounts/trends 恒空正确返回。
- `test_studio_api.py` 迁移后照过(行为不变),必要时改 import。
- 全量 `pytest tests/data_foundation` 绿。

## 风险与缓解

- **迁移改动面**:`studio_api.py` 大量 `_load_*` 迁出 + 改引用。缓解:纯搬家不改逻辑,
  迁完立即跑 `test_studio_api.py` 验证行为不变,再加工具。
- **循环 import**:operations.py 只依赖 db/permissions/performance_feedback(底层),
  不依赖 studio_api/internal_api/tools,处于依赖底部,无环。
