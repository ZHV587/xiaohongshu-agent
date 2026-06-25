# 事务性发件箱事件驱动自愈优化设计规约

本文档描述了如何通过 PostgreSQL 的 `LISTEN/NOTIFY` 机制重构小红书智能体数据底座发件箱的调度机制，将原有的忙轮询模式升级为事件驱动模式，实现零空载数据库压力与毫秒级即时数据同步唤醒，并保障多租户及并发测试环境下的物理隔离。

## 1. 背景与现状分析

目前，项目数据底座采用事务性发件箱（Transactional Outbox）来保证 PostgreSQL 业务库、Meilisearch 检索服务和 FalkorDB 图数据库三者之间的最终一致性。

### 现有缺陷：
1. **数据库轮询负载**：后台守护服务 `BackgroundServiceSupervisor` 目前通过固定时间间隔（默认 30 秒）周期性发起 `SELECT FOR UPDATE SKIP LOCKED` 等锁扫描操作。在系统空闲期，这会对数据库连接池和 CPU 造成持续且不必要的轮询开销。
2. **内容同步延迟**：当用户在 Chat UI 中产生选题策划或文案，或者外部数据源发生变更时，发件箱任务被插入后无法被即时处理，必须等待下一轮 30 秒周期的到来，导致用户体验上存在秒级的同步停顿感。

## 2. 优化方案设计

我们引入 **PostgreSQL 触发器事件广播 (LISTEN/NOTIFY)** 机制来解决轮询开销和延迟问题。

### 方案概述：
- **发件箱插入/重置时通知**：当发件箱 `resource_outbox` 产生新任务（即状态变更为 `pending`）时，数据库触发器通过 `pg_notify` 发出以当前 Schema 隔离的通道通知。
- **后台守护进程即时监听唤醒**：后台监听器（基于 `psycopg` 异步连接的 `LISTEN` 循环）接收通知并设置同步唤醒事件，打破原有固定周期的 sleep 限制，实现毫秒级响应。
- **低频兜底轮询**：对于重试任务（`status = 'retry'`，重试时间在未来的任务），由于无法由实时插入触发，系统保留 30 秒的兜底超时轮询，在没有新任务时平稳处理退避重试。

---

## 3. 详细设计与实现路径

### 3.1 数据库触发器与函数设计 (`data_foundation/schema.sql`)

我们在数据库层面增加一个触发器函数和两个事件触发器，物理定义必须紧随 `resource_outbox` 表的创建 SQL 之后：

```sql
-- 1. 创建 Schema 隔离的通知函数
create or replace function notify_resource_outbox_insert()
returns trigger as $$
begin
    -- 动态拼接 current_schema() 作为通道，空则回退到 public，防止并发测试和多租户干扰
    perform pg_notify('outbox_work_' || coalesce(current_schema(), 'public'), new.tenant_id);
    return new;
end;
$$ language plpgsql;

-- 2. 针对 INSERT 操作的触发器：仅当新记录为 pending 时触发
drop trigger if exists trg_resource_outbox_notify_insert on resource_outbox;
create trigger trg_resource_outbox_notify_insert
  after insert on resource_outbox
  for each row
  when (new.status = 'pending')
  execute function notify_resource_outbox_insert();

-- 3. 针对 UPDATE 操作的触发器：当 status 更新为 pending 且旧状态不为 pending 时触发
drop trigger if exists trg_resource_outbox_notify_update on resource_outbox;
create trigger trg_resource_outbox_notify_update
  after update of status on resource_outbox
  for each row
  when (new.status = 'pending' and old.status <> 'pending')
  execute function notify_resource_outbox_insert();
```

**设计要点**：
- **Schema 动态拼接**：通道名称为 `outbox_work_<schema_name>`，当测试框架（如 pytest Conftest 治具）为并发测试用例创建临时 schema `test_xxxx` 时，通知仅在 `outbox_work_test_xxxx` 通道内广播，互不污染。
- **幂等性与执行时序**：使用 `DROP TRIGGER IF EXISTS` 确保迁移脚本可重复执行。物理顺序定义在 `resource_outbox` 创建之后，确保不会发生找不到表的关系错误。
- **过滤机制**：使用 `after update of status` 限制触发列，屏蔽了高频更新租约（`lease_expires_at`）等修改操作。通过 `WHEN` 子句在 PG 引擎内初筛，减少函数调用的无谓 CPU 开销。

---

### 3.2 后端监听器与自愈逻辑设计 (`data_foundation/supervisor.py`)

在 `BackgroundServiceSupervisor` 内重构任务循环：

#### 成员初始化：
```python
self._listener_task: asyncio.Task | None = None
self._wake_event = asyncio.Event()
```

#### 异步自愈监听协程：
```python
async def _listen_db_notifies(self) -> None:
    """异步监听当前 Schema 的 PG 发件箱广播通知，连接断开时自动 5 秒退避重连。"""
    from psycopg import AsyncConnection
    from psycopg.rows import dict_row
    from data_foundation.db import database_url
    
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
                    # 监听到事件，设置唤醒标记
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

#### 任务循环更新 (`_run`):
```python
async def _run(self) -> None:
    loop = asyncio.get_running_loop()
    
    # 启动后台自愈监听任务
    self._listener_task = asyncio.create_task(self._listen_db_notifies())
    
    while self.accepting_work:
        # 在 cycle 开始前清空 event，保证处理期间新到达的通知可以在下一轮无缝重入
        self._wake_event.clear()
        
        scheduler = self._scheduler
        if scheduler is not None and self._executor is not None:
            self.last_cycle_started_at = _utc_now()
            try:
                self._cycle_future = loop.run_in_executor(
                    self._executor, lambda: asyncio.run(self._scheduler.run_cycle())
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
        
        # 阻塞等待唤醒，超时（30秒）后进入下一轮，防止协程内存泄漏
        try:
            await asyncio.wait_for(
                self._wake_event.wait(), 
                timeout=self.interval_seconds
            )
        except TimeoutError:
            continue
```

#### 优雅停机更新 (`stop`):
```python
async def stop(self, *, grace_seconds: float = 10.0) -> None:
    self.accepting_work = False
    self._stop_event.set()
    self._wake_event.set()  # 即刻打断等待挂起，实现快速关停
    
    # 1. 关停监听协程并等待其退出，消除长连接泄漏
    if self._listener_task is not None:
        self._listener_task.cancel()
        try:
            await self._listener_task
        except asyncio.CancelledError:
            pass
        self._listener_task = None

    # 2. 通知主 scheduler 结束当前轮次
    scheduler = self._scheduler
    request_stop = getattr(scheduler, "request_stop", None)
    if callable(request_stop):
        request_stop()
        
    # 3. 正常等待主任务退出
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
            
    # 4. 关闭独占的 ThreadPoolExecutor 线程池
    if self._executor is not None:
        await asyncio.to_thread(self._executor.shutdown, True)
        self._executor = None
    self._stop_scheduler()
```

---

## 4. 测试与验证方案

### 4.1 自动化集成测试
在现有的 `tests/data_foundation/` 下增加新单元测试 `test_outbox_notify.py`：
1. **即时唤醒测试**：向 `resource_outbox` 写入一条 `pending` 数据，使用 `asyncio.wait_for` 验证 `BackgroundServiceSupervisor` 是否在 50 毫秒内接收并启动 cycle 线程，而非等待 30 秒。
2. **Schema 隔离测试**：在不同的 schema（`test_schema1` 和 `test_schema2`）中分别启动监听和写入。验证在 `test_schema1` 中的写入不会意外唤醒 `test_schema2` 的事件。
3. **断线自愈测试**：通过模拟网络故障人为关闭连接，验证 `_listen_db_notifies` 协程能正常捕获异常，并在 5 秒后重试重新 LISTEN。

### 4.2 性能对比指标
- 空闲时 `SELECT` SQL 对数据库产生的 TPS 开销应降至 **`0`**（不含常规 telemetry 心跳统计）。
- 发件箱新任务创建到处理器开始执行 `process` 的时延应小于 **`10ms`**（此前平均时延为 `15000ms`）。
