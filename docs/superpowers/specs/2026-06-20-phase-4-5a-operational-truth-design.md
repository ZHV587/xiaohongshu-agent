# Phase 4.5A：运行状态可信化设计

- 日期：2026-06-20
- 状态：已确认，待实施计划
- 前置：Phase 4.1-4.4
- 后续：Phase 4.5B 内部健康接口、Phase 4.5C 管理员状态界面、Phase 4.5D 正式生产运行时

## 1. 目标

在实现管理员状态界面前，先把 scheduler、outbox、embedding 和同步执行改造成可恢复、可验证、不会制造假成功的应用服务。系统必须保存运行事实，由后续 HealthService 计算健康结论。

本阶段不修改 DeepAgents 内核。DeepAgents 继续负责编排 Agent；数据同步、异步任务、向量生成和运行遥测位于应用服务层。后台服务通过 LangGraph 官方 `langgraph.json` 的 `http.app` ASGI lifespan 启停，不在 `agent.py` import 时启动线程。

## 2. 已确认决策

1. 当前处于开发阶段，没有需要保留的 Phase 3/4 业务数据。
2. 全部旧数据底座表一次性重建，不编写旧结构兼容和数据转换逻辑。
3. 保留 `lark_uat_tokens`、配置中心、管理员和登录配置等非业务数据。
4. 删除旧 scheduler/outbox 实现、旧测试、兼容别名和回退开关。
5. 第一版只实现真实 pgvector embedding processor。
6. Meilisearch、Graphiti 及其他未配置 processor 明确为 `disabled`，不得把任务标记成功。
7. embedding 使用独立的 OpenAI 兼容配置，不复用聊天模型配置。
8. embedding 维度固定为 1536；配置维度不为 1536 时 processor 禁用。
9. outbox 最多重试 8 次，使用指数退避、随机抖动和死信终态。
10. scheduler 从已到期同步源和待处理 outbox 动态发现租户，并公平轮询。
11. `sync_sources.credentials` 允许在 PostgreSQL 中明文保存飞书和数据库凭证。
12. 凭证明文不得进入日志、outbox payload、错误摘要、遥测或后续管理员 API。

## 3. 范围

### 3.1 包含

- 多租户 scheduler 与租户发现。
- `sync_sources` 登记、到期领取、租约、执行记录及首批 Feishu/PostgreSQL source processor。
- outbox 幂等入队、租约、续租、恢复、退避、阻塞和死信。
- processor registry 与真实 embedding processor。
- embedding 分块、版本校验、批量生成、原子写入和模型切换。
- 服务实例心跳和每轮执行事实。
- ASGI lifespan 启停与优雅关闭。
- 全新 schema、repository/service 边界及 PostgreSQL 集成测试。

### 3.2 不包含

- 管理员页面和可视化。
- 对外或管理员健康 API。
- 手动重试、重启、迁移等写操作。
- Meilisearch、Graphiti、Neo4j/FalkorDB 的部署或 processor。
- 任意向量维度支持。
- 应用内租户、角色或凭证管理页面。
- LangGraph 正式生产运行时迁移；该项属于 Phase 4.5D。

## 4. 删除与替换

实施时直接删除以下旧行为，不保留双轨：

- `data_foundation/scheduler.py` 中单租户、进程内 `_started` 和静默吞异常的循环。
- `data_foundation/outbox_worker.py` 中只校验 topic 就标记成功的 `_process_item()` 与 `SUPPORTED_TOPICS`。
- `agent.py` import 阶段启动后台线程的路径。
- 旧 scheduler/outbox 单元测试及其旧状态假设。
- `available_at`、原始 `last_error` 等旧 outbox 字段和语义。
- 任何旧函数别名、兼容 adapter、legacy feature flag 或 fallback。

新实现可以复用文件名以保持模块归属清晰，但文件内容和公开服务契约按本设计重写。

## 5. 组件边界

```text
LangGraph http.app ASGI lifespan
  -> BackgroundServiceSupervisor
      -> Scheduler
          -> TenantDiscovery
          -> SyncSourceService
              -> SourceProcessorRegistry
                  -> FeishuSourceProcessor
                  -> PostgresSourceProcessor
          -> OutboxService
              -> ProcessorRegistry
                  -> EmbeddingProcessor
          -> ExecutionTelemetry
```

### 5.1 `BackgroundServiceSupervisor`

- 在 ASGI lifespan 启动和停止后台任务。
- 重复启动幂等。
- 收到 SIGTERM 后停止领取新任务，等待当前任务完成到宽限期；超时则释放或等待租约自然过期。
- 不持有业务状态，跨实例协调全部依赖 PostgreSQL。

### 5.2 `TenantDiscovery`

只返回两类租户：

- 存在已启用且 `next_run_at <= now()` 的同步源。
- 存在到期 `pending/retry` 或可恢复任务的 outbox 租户。

不得根据历史 `sync_runs` 推断活跃租户。租户按 `last_dispatched_at` 升序调度，每租户每轮最多一个批次。

### 5.3 `ProcessorRegistry`

- topic 到真实 processor 的显式注册表。
- processor 必须报告 `enabled/disabled/misconfigured` 和配置版本。
- 未注册、禁用或配置错误的 topic 不得领取执行。
- 对应任务进入 `blocked`；配置恢复后下一轮自动转回 `pending`。

### 5.4 `SourceProcessorRegistry`

同步来源与 outbox topic 使用两套 registry，不能混为同一种任务：

- `feishu_base`：读取指定 Base/table 并沉淀为通用资源。
- `feishu_wiki`：读取指定 Wiki space/node 并沉淀文档与分块。
- `postgres_table`：以只读事务和结构化表映射读取外部 PostgreSQL 表或视图。

PostgreSQL 来源不接受任意 SQL 字符串。`sync_sources.config` 必须声明 schema、table/view、主键列、标题列、正文列、更新时间列和可选固定过滤条件；标识符经过白名单校验和安全引用。读取采用 keyset pagination、连接超时、语句超时和只读事务。

各 source processor 必须把读取结果交给统一 repository，资源、版本、事件、映射和 outbox 写入仍处于同一事务边界。来源处理器不得直接写这些表。

### 5.5 `EmbeddingProcessor`

- 使用独立 OpenAI 兼容 embedding endpoint。
- 采用确定性分块并记录 `chunker_version`。
- 批量响应必须完整校验数量、顺序、数值和 1536 维度。
- 写入前重新确认资源当前版本和任务租约。
- 所有向量在单个事务中写入；部分响应或部分写入必须整体回滚。

## 6. 数据库重建

一次性删除并重建以下 Phase 3/4 业务表：

```text
resources
resource_versions
resource_events
resource_mappings
resource_permissions
resource_embeddings
resource_edges
resource_outbox
embedding_indexes
sync_sources
sync_runs
service_instances
service_executions
service_error_aggregates
```

不得删除 `lark_uat_tokens` 和配置中心数据。重建命令只允许明确列出上述表，不使用按模式模糊匹配的删除逻辑。

### 6.1 `resource_outbox`

核心字段：

- `id`, `tenant_id`, `topic`, `payload`
- `resource_id`, `resource_version`
- `dedupe_key`，全局唯一且不可变
- `status`
- `attempts`, `next_attempt_at`
- `lease_owner`, `lease_expires_at`
- `error_code`, `error_summary`
- `dead_at`, `created_at`, `updated_at`

状态固定为：

```text
pending | processing | retry | blocked | succeeded | superseded | dead
```

Embedding dedupe key 至少包含 tenant、resource、resource version、topic、embedding model 和 chunker version。重复入队返回已有任务。

### 6.2 `resource_embeddings`

- `(resource_id, resource_version)` 外键关联 `resource_versions(resource_id, version)`。
- 唯一键包含 resource、resource version、chunk index、embedding model 和 chunker version。
- 向量列固定为 `vector(1536)`。
- 搜索只读取当前资源版本和当前 active embedding index。

### 6.3 `embedding_indexes`

每个 tenant/model/config version 记录：

- `status`: `building | active | retired | failed`
- `embedding_model`, `dimensions`, `chunker_version`, `config_version`
- `expected_resources`, `completed_resources`, `failed_resources`
- `activated_at`, `created_at`, `updated_at`

同一租户最多一个 active index。模型变更时创建 building index并为全部当前资源生成回填任务；覆盖率达到 100% 且失败数为 0 后，才在一个事务中切换 active/retired。构建期间搜索继续使用旧 active index。

### 6.4 `sync_sources`

记录 tenant、来源类型、外部标识、明文 `credentials jsonb`、启用状态、调度周期、`next_run_at`、`last_dispatched_at`、租约字段和时间戳。

同步源领取使用 `FOR UPDATE SKIP LOCKED`。多个服务实例不得重复领取同一到期源。

### 6.5 `sync_runs`

每次同步执行关联 `sync_source_id`、tenant、source type、instance ID 和 execution ID，记录开始/结束、游标、读取/新增/更新/跳过/失败数量、结果和脱敏错误。运行中断后根据同步源租约和执行心跳判定 stale，不通过历史状态猜测仍在运行。

### 6.6 `service_instances`、`service_executions` 与错误聚合

`service_instances` 保存 component、instance ID、deployment ID、started/heartbeat/stopped 时间和配置版本。

`service_executions` 保存 component、instance ID、tenant、开始/结束时间、处理数量、耗时、结果、标准错误码和脱敏摘要。数据库只保存事实，不保存 `healthy/degraded` 等派生结论。

`service_error_aggregates` 保存按时间窗口、tenant、component、topic/source type 和错误码聚合的数量。它不保存原始错误或凭证，用于 dead/blocked 明细过期后的趋势判断。

## 7. 任务状态机

```text
pending -> processing -> succeeded
                   |-> superseded
                   |-> retry -> processing
                   |-> dead

pending/retry <-> blocked
processing -- lease expired --> retry
```

所有迁移使用带前置状态和 lease owner 的条件更新。更新行数不是 1 时，worker 已失去所有权，必须停止处理并禁止提交。

系统提供 at-least-once，不宣称 exactly-once。processor 必须幂等。远程调用成功、本地提交前中断时允许再次调用，但不得产生重复数据库结果。

## 8. 租约、重试与错误分类

- 任务执行期间周期性续租。
- 续租失败时立即停止后续写入。
- 过期 processing 任务由恢复步骤原子转为 retry。
- 429 使用服务端 `Retry-After`。
- 网络超时、DNS、连接错误和 5xx 属于瞬时错误。
- 401/403 或缺失凭证属于可修复配置错误，任务进入 blocked；请求数据无效、响应结构损坏、向量数量或维度错误属于永久任务错误。修复配置后可恢复的错误不得直接死信。
- 最多执行 8 次；指数退避带随机抖动，达到上限进入 dead。
- 错误必须先经过集中脱敏器，摘要有固定最大长度。

## 9. 配置与热生效

独立配置键：

```text
XHS_EMBEDDING_BASE_URL
XHS_EMBEDDING_API_KEY
XHS_EMBEDDING_MODEL
XHS_EMBEDDING_DIMENSIONS=1536
XHS_EMBEDDING_BATCH_SIZE
XHS_EMBEDDING_TIMEOUT_SECONDS
```

每批任务开始时读取一次不可变配置快照并记录配置版本。配置中心按版本保留 active 和 building 两份 embedding profile，直到 building index 激活且旧 index 退休；因此切换 base URL、API key 或模型时，搜索仍能使用旧 profile 生成查询向量。旧 profile 退休后才允许清理。

配置缺失时 processor 为 disabled；维度错误时为 misconfigured。配置中心保存后，下一批自动读取新快照，blocked 任务自动恢复，不要求重启。

模型配置变化会创建新的 building index，而不是立即切换搜索模型。只支持 1536 维模型之间切换。

## 10. 明文凭证边界

`sync_sources.credentials` 按明确决策明文存储，数据库管理员和包含该表的备份可以读取凭证。系统不提供静态加密或字段级加密。

仍必须满足：

- Web 和后续健康接口不返回凭证值。
- 日志、错误摘要、outbox payload 和遥测不包含凭证。
- 脱敏覆盖嵌套 JSON、Authorization Header、API key、带用户信息的 URL 和数据库 DSN。
- 数据库来源第一版只允许 PostgreSQL driver，使用结构化表映射、连接和语句超时及只读事务，不执行用户提供的 SQL。

## 11. 保留与清理

- succeeded/superseded outbox 默认保留 7 天。
- service executions 默认保留 30 天。
- dead/blocked 默认保留 90 天；清理前保留按时间、tenant、topic、错误码聚合的统计事实。
- 新 embedding index 激活后再清理 retired index 的向量。
- 清理任务使用小批次和 `SKIP LOCKED`，不得阻塞正常处理。

## 12. 测试要求

测试以真实 PostgreSQL 集成为主，覆盖：

1. 多租户公平调度和跨租户隔离。
2. 多实例只有一个实例获得同一同步源或任务。
3. 租约续期、过期恢复、失去租约后禁止提交。
4. 幂等入队和 dedupe key。
5. 429、5xx、超时、DNS、401/403、响应损坏的分类、阻塞和退避。
6. 第 8 次失败进入 dead。
7. disabled/misconfigured processor 进入 blocked，配置热生效后恢复。
8. 旧资源版本进入 superseded，不能写入向量。
9. 向量数量、顺序或维度错误整批回滚。
10. 相同文本和 chunker version 生成相同分块。
11. building index 未完成时继续读取旧 active index，完整回填后只切换一次。
12. 配置切回历史模型不生成重复任务。
13. scheduler 异常被记录，不再静默吞掉。
14. SIGTERM 优雅停止、停止领取新任务和租约恢复。
15. 凭证不会出现在日志、错误、payload、遥测和服务返回值。
16. ASGI lifespan 重复启动幂等。
17. 数据库重建只删除列出的业务表，保留飞书令牌和配置数据。
18. Feishu source processor 复用统一 repository，不绕过版本、事件和 outbox。
19. PostgreSQL source processor 拒绝任意 SQL、危险标识符和非只读连接，并能按 keyset 分页续传。

## 13. 验收标准

- 旧 scheduler/outbox 占位代码和旧测试已删除。
- Agent graph import 不再启动后台线程。
- 未注册 processor 不会产生 succeeded 任务。
- 多租户、多实例下无重复提交和跨租户领取。
- 进程中断后 processing 任务可自动恢复。
- embedding 只写入当前资源版本，模型切换无检索空窗。
- 所有失败均有标准错误码和脱敏事实记录。
- 独立 embedding 配置保存后下一批热生效。
- 全量测试通过，且包含真实 PostgreSQL 并发测试。

## 14. 后续阶段

- Phase 4.5B 使用上述事实实现 LangGraph 官方 custom route 内部健康接口，并采用 loopback、内部密钥和 Next 管理员鉴权。
- Phase 4.5C 实现只读管理员状态视图、全局汇总、租户筛选、15 秒轮询和脱敏详情。
- Phase 4.5D 停止把 `langgraph dev` 作为服务器生产运行时，迁移到 LangGraph 正式部署方式。
