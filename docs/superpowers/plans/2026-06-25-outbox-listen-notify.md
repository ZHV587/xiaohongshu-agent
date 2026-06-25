# 事务性发件箱事件驱动自愈优化实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目发件箱（Transactional Outbox）调度从忙轮询重构为基于 PostgreSQL LISTEN/NOTIFY 的事件驱动自愈机制，消除空载数据库压力，实现毫秒级内容同步。

**Architecture:** 
1. 在数据库层对 `resource_outbox` 表的写入和状态重置绑定 Schema 隔离的通知触发器。
2. 后端 Supervisor 启动专用的异步连接进行监听，接收通知后通过 `asyncio.Event` 唤醒工作协程。
3. 守护线程保持 30 秒超时进行重试任务的轮询兜底，并在链接故障时进行 5 秒退避自动重连。

**Tech Stack:** PostgreSQL 16, Python 3.11, Asyncio, Psycopg 3 (AsyncConnection)

---

## 1. 物理文件及职责变更

| 文件路径 | 状态 | 职责 |
| :--- | :--- | :--- |
| `data_foundation/schema.sql` | [MODIFY] | 追加创建通知函数 `notify_resource_outbox_insert` 以及 `trg_resource_outbox_notify_insert` / `trg_resource_outbox_notify_update` 触发器，确保幂等性。 |
| `data_foundation/supervisor.py` | [MODIFY] | 声明 `_wake_event` 与 `_listener_task`，实现后台异步监听重连循环及优雅停机清理，将 `_run` 阻塞时间由固定 sleep 改为 `asyncio.wait_for` 超时。 |
| `tests/data_foundation/test_outbox_notify.py` | [NEW] | 包含三个测试用例：事件即时唤醒、Schema 测试物理隔离、以及数据库断线自愈重连。 |

---

## 2. 逐步任务分解

### Task 1: 数据库 Schema 变更与迁移校验

**Files:**
- Modify: [schema.sql](file:///e:/小红书智能体/data_foundation/schema.sql) (在 `resource_outbox` 索引定义行下方追加)

- [ ] **Step 1: 在 `schema.sql` 底部追加触发器定义**

在 `schema.sql` 原有的 `create index if not exists idx_resource_outbox_tenant_status` 定义后追加触发器函数与触发器：

```sql
-- 3. 创建动态 Schema 隔离的通知函数
create or replace function notify_resource_outbox_insert()
returns trigger as $$
begin
    perform pg_notify('outbox_work_' || coalesce(current_schema(), 'public'), new.tenant_id);
    return new;
end;
$$ language plpgsql;

-- 4. 幂等性创建 INSERT 触发器
drop trigger if exists trg_resource_outbox_notify_insert on resource_outbox;
create trigger trg_resource_outbox_notify_insert
  after insert on resource_outbox
  for each row
  when (new.status = 'pending')
  execute function notify_resource_outbox_insert();

-- 5. 幂等性创建 UPDATE 触发器
drop trigger if exists trg_resource_outbox_notify_update on resource_outbox;
create trigger trg_resource_outbox_notify_update
  after update of status on resource_outbox
  for each row
  when (new.status = 'pending' and old.status <> 'pending')
  execute function notify_resource_outbox_insert();
```

- [ ] **Step 2: 运行测试以确保数据库迁移可以干净执行并具备幂等性**

Run:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/test_schema.py -v
```
Expected: PASS，验证 migration 能够正常加载并编译 PL/pgSQL 触发器。

- [ ] **Step 3: Commit**

```bash
git add data_foundation/schema.sql
git commit -m "migration: add schema-isolated notify trigger on resource_outbox"
```

---

### Task 2: 创建单元测试结构并实现异步监听重连

**Files:**
- Create: [test_outbox_notify.py](file:///e:/小红书智能体/tests/data_foundation/test_outbox_notify.py)
- Modify: [supervisor.py](file:///e:/小红书智能体/data_foundation/supervisor.py) (添加监听协程与初始化声明)

- [ ] **Step 1: 新建测试文件 `test_outbox_notify.py` 并编写监听唤醒测试用例**

在 `tests/data_foundation/test_outbox_notify.py` 中写入：

```python
import asyncio
import pytest
import psycopg
from data_foundation.db import connect
from data_foundation.supervisor import BackgroundServiceSupervisor

@pytest.mark.asyncio
async def test_supervisor_listener_wake_event(migrated_conn):
    schema_row = migrated_conn.execute("SELECT current_schema()").fetchone()
    schema = schema_row[0] if (schema_row and schema_row[0]) else "public"
    
    supervisor = BackgroundServiceSupervisor(enabled=True)
    supervisor.accepting_work = True
    supervisor._wake_event.clear()
    
    supervisor._listener_task = asyncio.create_task(supervisor._listen_db_notifies())
    
    # 等待监听器连接
    await asyncio.sleep(0.5)
    
    # 模拟手动发送通知
    with connect() as conn:
        conn.autocommit = True
        conn.execute(f"NOTIFY outbox_work_{schema}, 'test_tenant'")
        
    try:
        await asyncio.wait_for(supervisor._wake_event.wait(), timeout=2.0)
        assert supervisor._wake_event.is_set()
    finally:
        supervisor.accepting_work = False
        if supervisor._listener_task:
            supervisor._listener_task.cancel()
            try:
                await supervisor._listener_task
            except asyncio.CancelledError:
                pass
```

- [ ] **Step 2: 运行测试并确保它失败（TDD）**

Run:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/test_outbox_notify.py -k test_supervisor_listener_wake_event -v
```
Expected: FAIL，提示 `BackgroundServiceSupervisor` 无 `_listen_db_notifies` 成员。

- [ ] **Step 3: 在 `supervisor.py` 中初始化属性并实现重连监听逻辑**

在 `BackgroundServiceSupervisor.__init__` 中新增：
```python
        self._listener_task = None
        self._wake_event = asyncio.Event()
```

并在类内添加异步监听方法 `_listen_db_notifies`：
```python
    async def _listen_db_notifies(self) -> None:
        """异步监听当前 Schema 的 PG 发件箱广播通知，连接断开时自动 5 秒退避重连。"""
        import logging
        from psycopg import AsyncConnection
        from psycopg.rows import dict_row
        from data_foundation.db import database_url
        
        logger = logging.getLogger(__name__)
        db_url = database_url()
        
        while self.accepting_work:
            try:
                async with await AsyncConnection.connect(db_url, autocommit=True) as conn:
                    async with conn.cursor(row_factory=dict_row) as cur:
                        await cur.execute("SELECT current_schema()")
                        row = await cur.fetchone()
                        schema = row["current_schema"] if (row and row["current_schema"]) else "public"
                        channel = f"outbox_work_{schema}"
                        await cur.execute(f"LISTEN {channel}")
                    
                    logger.info("Outbox listener connected and listening to channel: %s", channel)
                    
                    async for notify in conn.notifies():
                        self._wake_event.set()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(
                    "Outbox listener connection lost, retrying in 5 seconds. Error: %s", 
                    exc
                )
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
```

- [ ] **Step 4: 运行测试并使其通过**

Run:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/test_outbox_notify.py -k test_supervisor_listener_wake_event -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/data_foundation/test_outbox_notify.py data_foundation/supervisor.py
git commit -m "feat: implement outbox notification listener task"
```

---

### Task 3: 重构 Supervisor 工作流与关停清理逻辑

**Files:**
- Modify: [supervisor.py](file:///e:/小红书智能体/data_foundation/supervisor.py) (更新 `start`、`_run` 与 `stop` 方法)
- Modify: [test_outbox_notify.py](file:///e:/小红书智能体/tests/data_foundation/test_outbox_notify.py) (追加即时唤醒端到端测试)

- [ ] **Step 1: 在 `test_outbox_notify.py` 中追加 `test_supervisor_outbox_trigger_wakeup` 测试用例**

在 `tests/data_foundation/test_outbox_notify.py` 底部写入：

```python
@pytest.mark.asyncio
async def test_supervisor_outbox_trigger_wakeup(migrated_conn):
    schema_row = migrated_conn.execute("SELECT current_schema()").fetchone()
    schema = schema_row[0] if (schema_row and schema_row[0]) else "public"
    
    cycle_run_count = 0
    cycle_done = asyncio.Event()
    
    class MockScheduler:
        def __init__(self):
            self.telemetry = None
            self.config = None
        async def run_cycle(self):
            nonlocal cycle_run_count
            cycle_run_count += 1
            cycle_done.set()
            from data_foundation.scheduler import CycleStats
            return CycleStats()
        def stop(self):
            pass
            
    supervisor = BackgroundServiceSupervisor(
        scheduler_factory=MockScheduler,
        enabled=True,
        interval_seconds=10.0
    )
    
    await supervisor.start()
    await asyncio.sleep(0.5)
    cycle_done.clear()
    
    # 插入外键所需的底层资源数据
    import uuid
    resource_id = uuid.uuid4()
    
    migrated_conn.execute(
        "insert into resources (tenant_id, id, type, title, summary, content_text) "
        "values ('tenant_test', %s, 'note', 'title', 'summary', 'content')",
        (resource_id,)
    )
    migrated_conn.execute(
        "insert into resource_versions (tenant_id, resource_id, version, content_text, content_hash) "
        "values ('tenant_test', %s, 1, 'content', 'hash')",
        (resource_id,)
    )
    migrated_conn.commit()
    
    # 写入 pending 状态的 outbox 记录触发 trigger 唤醒
    migrated_conn.execute(
        "insert into resource_outbox (tenant_id, resource_id, resource_version, topic, dedupe_key, payload, status) "
        "values ('tenant_test', %s, 1, 'meili_index', 'dedupe_key_1', '{}'::jsonb, 'pending')",
        (resource_id,)
    )
    migrated_conn.commit()
    
    try:
        # 验证是否立即触发执行（超时时间设为 3 秒，远低于 interval_seconds=10）
        await asyncio.wait_for(cycle_done.wait(), timeout=3.0)
        assert cycle_run_count >= 1
    finally:
        await supervisor.stop()
```

- [ ] **Step 2: 运行测试并确保它失败（或发生长等待超时）**

Run:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/test_outbox_notify.py -k test_supervisor_outbox_trigger_wakeup -v
```
Expected: FAIL (等待 3.0s 超时报错，因为目前没有对接 `_wake_event` 唤醒主协程)。

- [ ] **Step 3: 重构 `supervisor.py` 中的 `start`、`_run` 与 `stop` 逻辑**

更新 `start` 方法，在启动前清除事件：
```python
    async def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self.accepting_work = True
        self._stop_event.clear()
        self._wake_event.clear()
        self._scheduler = self.scheduler_factory()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xhs-sched-cycle")
        self._task = asyncio.create_task(self._run(), name="xhs-data-foundation-supervisor")
        self.start_count += 1
```

更新 `_run` 方法，用 `_wake_event.wait()` 代替 `_stop_event.wait()`：
```python
    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        self._listener_task = asyncio.create_task(self._listen_db_notifies())
        
        while self.accepting_work:
            self._wake_event.clear()
            scheduler = self._scheduler
            if scheduler is not None and self._executor is not None:
                self.last_cycle_started_at = _utc_now()
                try:
                    self._cycle_future = loop.run_in_executor(
                        self._executor, lambda: asyncio.run(scheduler.run_cycle())
                    )
                    await self._cycle_future
                    self.last_cycle_status = "succeeded"
                    self.last_cycle_error_code = None
                except Exception:
                    self.last_cycle_status = "failed"
                    self.last_cycle_error_code = SCHEDULER_CYCLE_FAILED
                finally:
                    self._cycle_future = None
                    self.last_cycle_finished_at = _utc_now()
            try:
                # 阻塞等待事件唤醒，超时由 interval_seconds 限制做兜底
                await asyncio.wait_for(
                    self._wake_event.wait(), 
                    timeout=self.interval_seconds
                )
            except TimeoutError:
                continue
```

更新 `stop` 方法，在退出时做清理及快速打断：
```python
    async def stop(self, *, grace_seconds: float = 10.0) -> None:
        self.accepting_work = False
        self._stop_event.set()
        self._wake_event.set()  # 唤醒 _run 协程快速退出
        
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None
            
        scheduler = self._scheduler
        request_stop = getattr(scheduler, "request_stop", None)
        if callable(request_stop):
            request_stop()
            
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=max(0.0, float(grace_seconds)))
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            finally:
                self._task = None
                
        if self._executor is not None:
            await asyncio.to_thread(self._executor.shutdown, True)
            self._executor = None
        self._stop_scheduler()
```

- [ ] **Step 4: 运行测试并确保它通过**

Run:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/test_outbox_notify.py -k test_supervisor_outbox_trigger_wakeup -v
```
Expected: PASS (测试应在 1s 内极速通过，代表 trigger 到主工作循环唤醒的物理链路完全打通)。

- [ ] **Step 5: Commit**

```bash
git add data_foundation/supervisor.py
git commit -m "feat: wire wake event to supervisor run loop and implement fast stop cleanup"
```

---

### Task 4: 添加断线自愈重连测试并运行全局验证

**Files:**
- Modify: [test_outbox_notify.py](file:///e:/小红书智能体/tests/data_foundation/test_outbox_notify.py) (追加断线重连恢复测试)

- [ ] **Step 1: 追加 `test_supervisor_listener_reconnect` 测试用例**

在 `tests/data_foundation/test_outbox_notify.py` 底部写入：

```python
@pytest.mark.asyncio
async def test_supervisor_listener_reconnect(migrated_conn):
    schema_row = migrated_conn.execute("SELECT current_schema()").fetchone()
    schema = schema_row[0] if (schema_row and schema_row[0]) else "public"
    
    supervisor = BackgroundServiceSupervisor(enabled=True)
    supervisor.accepting_work = True
    supervisor._wake_event.clear()
    
    supervisor._listener_task = asyncio.create_task(supervisor._listen_db_notifies())
    await asyncio.sleep(0.5)
    
    import os
    original_url = os.environ.get("XHS_DATABASE_URL")
    try:
        # 修改为错误地址，强制触发异常和重连退避
        os.environ["XHS_DATABASE_URL"] = "postgresql://invalid_host:5432/invalid"
        await asyncio.sleep(0.5)
        
        # 恢复正确地址
        os.environ["XHS_DATABASE_URL"] = original_url
        # 等待重连成功（退避 5 秒 + 握手时间）
        await asyncio.sleep(6.0)
        
        # 模拟触发通知
        with connect() as conn:
            conn.autocommit = True
            conn.execute(f"NOTIFY outbox_work_{schema}, 'test_tenant'")
            
        await asyncio.wait_for(supervisor._wake_event.wait(), timeout=3.0)
        assert supervisor._wake_event.is_set()
    finally:
        os.environ["XHS_DATABASE_URL"] = original_url
        supervisor.accepting_work = False
        if supervisor._listener_task:
            supervisor._listener_task.cancel()
            try:
                await supervisor._listener_task
            except asyncio.CancelledError:
                pass
```

- [ ] **Step 2: 运行测试并确保它通过**

Run:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/test_outbox_notify.py -k test_supervisor_listener_reconnect -v
```
Expected: PASS (等待 6s+ 重连恢复后，测试正常唤醒并通过)。

- [ ] **Step 3: 运行数据底座全部测试确保无任何回归**

Run:
```powershell
$env:TEST_XHS_DATABASE_URL="postgresql://postgres:123456@localhost:5432/postgres"; .venv\Scripts\pytest tests/data_foundation/
```
Expected: All tests pass successfully (测试用例总数应增加至至少 316 个且全绿通过)。

- [ ] **Step 4: Commit**

```bash
git add tests/data_foundation/test_outbox_notify.py
git commit -m "test: add db reconnect resilience test case for outbox notification"
```
