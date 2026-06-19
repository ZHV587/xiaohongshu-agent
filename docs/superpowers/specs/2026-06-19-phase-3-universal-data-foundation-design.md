# 第三阶段通用数据底座与图谱增强设计

- 日期: 2026-06-19
- 范围: Postgres 权威数据底座、飞书双沉淀、统一资源模型、检索、图谱、事件日志、DeepAgents tools
- 状态: 设计待评审

## 1. 目标

第三阶段把当前小红书文案智能体升级为通用数据底座上的多 Agent 应用平台。底层数据必须是通用的，不绑定小红书单一业务，也不只依托飞书。Postgres 是权威业务数据库；飞书是协作沉淀层；搜索、向量、图谱和事件日志围绕统一资源模型组合。

核心目标:

- 所有业务对象统一抽象为 `resource`。
- Postgres 存储结构化记录、映射、版本、权限、事件和图边。
- `pgvector` 存储向量索引，支撑语义召回。
- Meilisearch 提供快速全文检索和关键词召回。
- Graphiti + Neo4j/FalkorDB 提供时间知识图谱和事实演化能力。
- DeepAgents / LangGraph 继续作为 agent runtime，不被替换、不 fork、不 monkey-patch。
- 所有数据能力通过 Data Access Layer 和 DeepAgents tools 暴露，Agent 不直接执行 SQL、Cypher 或绕过权限访问底层存储。

## 2. 架构原则

1. Postgres 是第三阶段权威业务库，不使用 SQLite 作为正式路径。
2. 飞书不是临时外部源，而是人可读、可协作、可审批的业务沉淀层。
3. 数据库与飞书之间必须维护双向映射、版本状态和同步事件。
4. 图谱先以 Postgres `resource_edges` 落地基础图能力，再接 Graphiti + 图数据库做时间知识图谱。
5. 检索采用关键词、向量、图扩展、权限过滤和重排序的组合，而不是单一向量库。
6. DeepAgents tools 是 agent 访问数据底座的唯一入口。
7. 高风险写操作继续使用 DeepAgents `interrupt_on` 或人工确认。
8. 第三阶段不是引入多 Agent；多 Agent 协作已经由 DeepAgents 提供。本阶段为既有多 Agent 协作提供统一数据、检索、图谱和权限底座。

## 3. 分层架构

```text
Web / Admin UI
  -> Next API routes
    -> Data Access Layer
      -> Postgres + pgvector
      -> Meilisearch
      -> Graphiti + Neo4j/FalkorDB
      -> Feishu APIs / lark-cli bridge
DeepAgents / LangGraph
  -> tools/search_resources
  -> tools/semantic_search
  -> tools/graph_expand
  -> tools/get_resource
  -> tools/query_records
  -> tools/write_artifact
  -> tools/sync_to_feishu
```

边界:

- Web 负责用户交互、管理页面和 API 鉴权。
- Python DAL 负责资源模型、同步、检索、权限过滤和审计。
- Agent 只调用 tools，不直接连接 Postgres、Meilisearch、Neo4j 或飞书底层 API。
- 数据同步任务可以由管理 API、后台 worker 或 Dagster 触发，但写入必须统一经过 DAL。
- 项目自身不恢复 CLI 运行入口；`lark-cli bridge` 仅作为飞书 API adapter 被 server/worker 调用。

## 4. Postgres 权威数据模型

### 4.0 数据库前置条件

第三阶段正式环境必须提供 Postgres 连接字符串:

- `XHS_DATABASE_URL`

必要扩展:

- `pgcrypto`: 使用 `gen_random_uuid()` 生成 UUID。
- `vector`: pgvector 向量列和近邻索引。

迁移策略:

- 所有 schema 变更以 SQL migration 文件落地，禁止在应用启动时隐式改表。
- migration 必须可重复验证，测试环境必须从空库完整迁移成功。
- 第一版不引入 ORM 作为强依赖；DAL 可以先使用 `psycopg`/SQLAlchemy Core 风格的显式 SQL，避免 schema 与业务语义漂移。

### 4.1 `resources`

所有业务对象的根表。

字段:

- `id uuid primary key`
- `tenant_id text not null`
- `type text not null`
- `title text not null`
- `summary text`
- `content_text text`
- `content_json jsonb not null default '{}'`
- `status text not null default 'active'`
- `visibility text not null default 'private'`
- `owner_open_id text`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

约束:

- `type` 使用受控枚举语义: `feishu_base_record`、`feishu_doc`、`draft`、`artifact`、`agent_run`、`topic`、`memory`、`task`、`approval`、`published_content`。
- `tenant_id + type + title` 可建立普通索引，但不能作为唯一键。
- 资源正文统一进入 `content_text`，结构化字段进入 `content_json`。

### 4.2 `resource_mappings`

维护内部资源和外部系统对象的映射。

字段:

- `id uuid primary key`
- `resource_id uuid not null references resources(id)`
- `system text not null`
- `external_type text not null`
- `external_id text not null`
- `external_url text`
- `external_updated_at timestamptz`
- `sync_cursor text`
- `sync_status text not null default 'pending'`
- `last_error text`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

唯一约束:

- `(system, external_type, external_id)`

示例:

- `system=feishu, external_type=base_record, external_id=<app_token>:<table_id>:<record_id>`
- `system=feishu, external_type=docx, external_id=<document_id>`
- `system=feishu, external_type=wiki_node, external_id=<space_id>:<node_token>`

### 4.3 `resource_versions`

资源内容版本。

字段:

- `id uuid primary key`
- `resource_id uuid not null references resources(id)`
- `version int not null`
- `content_hash text not null`
- `content_text text`
- `content_json jsonb not null default '{}'`
- `changed_by text`
- `change_summary text`
- `created_at timestamptz not null default now()`

唯一约束:

- `(resource_id, version)`

### 4.4 `resource_events`

事件日志用于审计、同步重放、图谱增量和复盘。

字段:

- `id uuid primary key`
- `tenant_id text not null`
- `resource_id uuid references resources(id)`
- `event_type text not null`
- `actor_open_id text`
- `payload jsonb not null default '{}'`
- `created_at timestamptz not null default now()`

事件类型:

- `imported`
- `updated`
- `generated`
- `synced_to_feishu`
- `synced_from_feishu`
- `review_requested`
- `approved`
- `published`
- `feedback_received`
- `permission_changed`
- `config_changed`

### 4.5 `resource_edges`

基础图边先落在 Postgres，支撑 BFS/k-hop、血缘、解释路径和轻量图扩展。

字段:

- `id uuid primary key`
- `tenant_id text not null`
- `source_resource_id uuid not null references resources(id)`
- `target_resource_id uuid not null references resources(id)`
- `edge_type text not null`
- `weight double precision not null default 1.0`
- `properties jsonb not null default '{}'`
- `created_at timestamptz not null default now()`

唯一约束:

- `(source_resource_id, target_resource_id, edge_type)`

边类型:

- `DERIVED_FROM`
- `SYNCED_TO`
- `MENTIONS`
- `SIMILAR_TO`
- `APPROVED_BY`
- `FEEDBACK_TO`
- `MEASURES`
- `BELONGS_TO`

### 4.6 `resource_permissions`

资源级权限快照。

字段:

- `id uuid primary key`
- `tenant_id text not null`
- `resource_id uuid not null references resources(id)`
- `subject_type text not null`
- `subject_id text not null`
- `permission text not null`
- `created_at timestamptz not null default now()`

`subject_type`:

- `user`
- `role`
- `team`

`permission`:

- `read`
- `write`
- `admin`

### 4.7 `resource_embeddings`

pgvector 语义索引。

字段:

- `id uuid primary key`
- `resource_id uuid not null references resources(id)`
- `chunk_index int not null`
- `chunk_text text not null`
- `embedding vector`
- `embedding_model text not null`
- `created_at timestamptz not null default now()`

约束:

- `(resource_id, chunk_index, embedding_model)` 唯一。

说明:

- 第一版可以先写 chunk 记录，embedding 生成可由后续 worker 补齐。
- `embedding vector` 维度按实际模型迁移文件固定，例如 `vector(1536)` 或 `vector(3072)`。

### 4.8 `resource_outbox`

异步索引、向量生成、飞书写回和图谱入图的可靠任务队列。

字段:

- `id uuid primary key`
- `tenant_id text not null`
- `resource_id uuid references resources(id)`
- `event_id uuid references resource_events(id)`
- `topic text not null`
- `payload jsonb not null default '{}'`
- `status text not null default 'pending'`
- `attempts int not null default 0`
- `last_error text`
- `available_at timestamptz not null default now()`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

约束:

- `status` 使用 `pending`、`processing`、`succeeded`、`failed`。
- `topic` 使用受控枚举语义: `meili_index`、`embedding_generate`、`graph_ingest`、`feishu_writeback`。
- worker 必须通过 `available_at`、`attempts` 和幂等键实现重试，不允许无限热循环。

## 5. Data Access Layer

DAL 是所有数据访问的唯一服务层。

模块建议:

- `data_foundation/db.py`: Postgres 连接、事务 helper。
- `data_foundation/schema.sql`: 初始 schema 和索引。
- `data_foundation/models.py`: `Resource`、`ResourceMapping`、`ResourceSearchResult` 等 typed dataclass。
- `data_foundation/repository.py`: CRUD、版本、事件、映射、图边。
- `data_foundation/permissions.py`: 当前用户权限过滤。
- `data_foundation/search.py`: 关键词、向量、RRF 重排。
- `data_foundation/graph.py`: BFS/k-hop、shortest path、图扩展。
- `data_foundation/feishu_sync.py`: 飞书 Base/Wiki/Doc 同步入库。
- `data_foundation/tools.py`: DeepAgents tools 封装。

DAL 规则:

- 所有读操作必须接收 `tenant_id` 与 `actor_open_id`。
- 所有读结果必须经过 `permission_filter`。
- 所有写操作必须写 `resource_events`。
- 所有外部对象写入必须 upsert `resource_mappings`。
- 所有大结果必须分页或限制 `limit`，tools 默认不超过 10 条资源。

tenant 解析:

- 第一版使用部署默认 tenant: `XHS_DEFAULT_TENANT_ID`，未配置时为 `default`。
- 用户身份来自 LangGraph auth 注入的 `server_info.user.identity`，即飞书 `open_id`。
- 后续接入多 tenant 时，tenant 必须来自用户会话或角色表，不允许由 Agent tool 参数自由传入。

事务规则:

- 单个资源写入、mapping upsert、version 写入和 event 写入必须处于同一 Postgres 事务。
- 外部系统调用不得放在数据库事务内部；需要先写 `resource_events` 和 `resource_outbox`，再由 worker 执行外部同步。

## 6. 飞书双沉淀同步

### 6.1 Base 同步

同步目标:

- 把飞书 Base 行转换为 `resources(type=feishu_base_record)`。
- 维护 `resource_mappings(system=feishu, external_type=base_record)`。
- 将原始字段保存到 `content_json.fields`。
- 将标题、正文、标签、状态等规范字段抽取到 `title`、`content_text`、`status`。

同步策略:

- 初版支持手动全量同步指定 Base table。
- 第二步支持基于 `external_updated_at` 或 sync cursor 的增量同步。
- 每次变更写 `resource_versions` 和 `resource_events`。

### 6.2 Wiki / Doc 同步

同步目标:

- Wiki node 建资源映射。
- Docx 文档内容转 Markdown/plain text 后写入 `resources(type=feishu_doc)`。
- 文档标题写 `title`，正文写 `content_text`，结构化元信息写 `content_json`。

同步策略:

- 初版同步指定 `FEISHU_WIKI_SPACE_ID` 下的 doc/docx 节点。
- 单次最多同步配置的上限，例如 200 篇。
- 大文档 chunk 写入 `resource_embeddings`，embedding 可异步生成。

### 6.3 写回飞书

写回场景:

- Agent 生成草稿后写入飞书 Base。
- Agent 生成复盘或方法论文档后写入飞书 Doc。
- 审核通知发送到飞书 IM。

规则:

- 写回前必须有人工确认或 DeepAgents interrupt。
- 写回后必须更新 `resource_mappings` 与 `resource_events`。
- 写回失败要记录 `last_error`，不得假成功。

## 7. 检索架构

检索流程:

1. `search_resources(query)`: Postgres `tsvector` 或 Meilisearch 关键词召回。
2. `semantic_search(query, top_k)`: pgvector 向量召回。
3. `graph_expand(resource_ids, hops, edge_types)`: 沿图扩展上下文。
4. `permission_filter(actor, resources)`: 权限过滤。
5. `rerank`: 使用 RRF 或加权融合排序。
6. `get_resource(resource_id)`: 精读资源。

第一版落地:

- Postgres `to_tsvector` 全文索引。
- pgvector 表结构和接口。
- Meilisearch adapter 先定义接口，后续接服务。

第二版增强:

- Meilisearch 作为快速全文召回。
- embedding worker 异步补齐向量。
- RRF 融合关键词和向量结果。

## 8. 图谱与图算法

第一层: Postgres 图边。

- BFS/k-hop: 通过递归 CTE 查询 `resource_edges`。
- shortest path: 初版用 BFS 限制 hop 深度实现。
- Personalized PageRank: 先定义接口，后续可迁移到图数据库或离线任务。
- Community Detection: 不在第一版同步执行，交给后续 Graphiti/图数据库或离线 pipeline。

第二层: Graphiti + Neo4j/FalkorDB。

- Graphiti 负责 temporal knowledge graph、事实演化、provenance。
- Neo4j 或 FalkorDB 作为图查询执行层。
- Postgres 仍是资源权威库，Graphiti 图节点必须保存 `resource_id` 回指。

图谱同步:

- `resource_events` 作为图谱增量输入。
- `resource_edges` 作为轻量图和 Graphiti 入图前缓冲。
- 图谱失败不得阻断 Postgres 主写入，但必须记录同步错误事件。

异步索引与 outbox:

- Meilisearch 索引、pgvector embedding 生成、Graphiti 入图都通过 `resource_events` 和 `resource_outbox` 异步消费。
- Postgres 主写入成功后，索引失败只能影响检索新鲜度，不能回滚权威业务数据。
- worker 必须支持幂等重放，依据 `resource_id + version` 或 `event_id` 去重。

## 9. DeepAgents Tools

第三阶段 tools:

- `search_resources(query: str, limit: int = 10)`
- `semantic_search(query: str, top_k: int = 10)`
- `graph_expand(resource_ids: list[str], hops: int = 1, edge_types: list[str] | None = None)`
- `get_resource(resource_id: str)`
- `query_records(resource_type: str, filters: dict, limit: int = 20)`
- `write_artifact(title: str, content: str, metadata: dict | None = None)`
- `sync_to_feishu(resource_id: str, target: dict)`

工具返回:

- 必须返回结构化 JSON。
- 搜索结果只返回摘要、score、resource_id 和少量 metadata。
- 精读才返回正文。
- 所有工具内部从 `RunnableConfig.server_info.user.identity` 解析当前用户。
- 缺用户身份时，server 模式拒绝访问。

## 10. 权限模型

第一版权限:

- `tenant_id` 必填。
- 用户只能读取:
  - owner 是自己的资源。
  - `visibility=team` 且同 tenant 的资源。
  - `resource_permissions` 显式授予 read 的资源。
- 管理员可读写同 tenant 全部资源。

后续增强:

- 与飞书组织架构、群组或知识库权限同步。
- 将飞书资源权限快照导入 `resource_permissions`。
- 对搜索结果先召回后过滤，避免泄露正文。

## 11. 开源组合与职责

必须集成:

- Postgres: 权威业务库。
- pgvector: 向量检索。

第一优先集成:

- Meilisearch: 关键词和全文检索。
- dlt: 飞书和外部系统的数据加载 pipeline。
- Unstructured: 文档解析。

第二优先集成:

- Graphiti: 时间知识图谱。
- Neo4j 或 FalkorDB: 图查询执行层。
- Dagster: 数据资产调度、同步编排、血缘和重试。

后续治理:

- DataHub 或 OpenMetadata 只在数据资产规模上来后引入，不作为第三阶段第一版核心依赖。

不采用:

- 不用 AgentGPT 作为参考或底座。
- 不整体引入 LlamaIndex 作为 agent runtime。
- 不把 Microsoft GraphRAG 当业务数据底座。
- 不让 Agent 直接执行自由 SQL 或 Cypher。

## 12. 实施切片

虽然第三阶段设计一次性完善，实施必须按可验证切片推进。

第一份实施计划只覆盖 Phase 3.1 到 Phase 3.4 的可运行闭环:

- Postgres schema 和 DAL。
- 飞书 Base/Wiki/Doc 入库最小同步。
- Postgres 全文检索和 pgvector 接口。
- `resource_edges` 与 `graph_expand`。
- DeepAgents tools 暴露。

Meilisearch、Graphiti、Neo4j/FalkorDB、Dagster 在同一设计中保留接口和 outbox 边界，但不作为第一份实现计划的阻塞依赖。

### Phase 3.1 Postgres 资源底座

交付:

- Postgres schema。
- Python DAL。
- `resources`、`resource_mappings`、`resource_events`、`resource_edges` CRUD。
- 基础权限过滤。
- 单元测试和迁移测试。

### Phase 3.2 飞书同步入库

交付:

- Base 记录同步到 Postgres。
- Wiki/Doc 同步到 Postgres。
- 版本、事件、映射和错误状态。
- 同步命令或管理 API。

### Phase 3.3 检索与 pgvector

交付:

- Postgres 全文检索。
- `resource_embeddings` 和 pgvector 查询接口。
- `search_resources`、`semantic_search`、`get_resource` tools。

### Phase 3.4 图边与 graph_expand

交付:

- `resource_edges` 生成和维护。
- BFS/k-hop 查询。
- `graph_expand` tool。
- 检索结果解释路径。

### Phase 3.5 Meilisearch 与 Graphiti

交付:

- Meilisearch 索引同步。
- Graphiti 入图 adapter。
- Neo4j/FalkorDB 配置。
- 时间事实和 provenance 查询。

### Phase 3.6 写回与工作流

交付:

- `write_artifact`。
- `sync_to_feishu`。
- 人工确认和审计。
- 草稿、审核、发布、反馈闭环。

## 13. 测试与验收

测试:

- DAL 单元测试使用测试 Postgres。
- 测试 Postgres 必须启用 `pgcrypto` 和 `vector` 扩展。
- schema 迁移测试必须可重复运行。
- 权限过滤测试覆盖 owner、team、explicit permission、admin。
- 同步测试 mock 飞书返回，验证 upsert、version、event 和 mapping。
- 检索测试覆盖关键词召回、向量接口、RRF 排序。
- 图测试覆盖 BFS/k-hop、edge type filter、权限过滤后图扩展。
- tools 测试验证无身份拒绝、结果限量、结构化输出。

验收:

- 每个业务对象都有 `resource_id`。
- 飞书 Base/Wiki/Doc 可同步到 Postgres。
- DB 和飞书之间有双向 mapping。
- `resource_events` 记录所有导入、生成、同步和写回。
- `search_resources`、`semantic_search`、`graph_expand`、`get_resource` 可组合完成 GraphRAG。
- 所有读取经过权限过滤。
- Agent 只通过 DeepAgents tools 访问数据底座。
- 不 fork DeepAgents，不 monkey-patch，不绕过 LangGraph runtime。

## 14. 风险与决策

风险:

- 一次性接入 Postgres、Meilisearch、Graphiti、Neo4j 会提高部署复杂度。
- 飞书权限模型和本地权限模型可能不一致。
- 大文档同步和 embedding 生成可能产生较高成本。
- 图谱抽取质量不稳定，不能作为权威事实源。

决策:

- Postgres 是权威事实源。
- Graphiti/图数据库是增强层，不替代 Postgres。
- Meilisearch 是召回加速层，不替代 Postgres。
- 飞书是协作沉淀层，不替代 Postgres。
- Agent 只能通过 tools 访问 DAL。

## 15. 非目标

- 不在第三阶段第一版实现完整组织级数据治理。
- 不在第一版做自由 SQL/Cypher Agent。
- 不在第一版承诺所有外部系统 connector。
- 不把图数据库作为权威业务库。
- 不替换 DeepAgents/LangGraph runtime。
