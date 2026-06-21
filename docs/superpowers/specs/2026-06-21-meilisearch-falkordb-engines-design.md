# Meilisearch 全文检索 + FalkorDB 图谱引擎接入设计

日期:2026-06-21
状态:已与用户确认设计,待写实现计划

## 1. 背景与目标

数据底座当前用 Postgres 一库承担三种检索:全文(`to_tsvector` + `ILIKE`)、图谱(`resource_edges` 递归 SQL)、语义(pgvector,已打通)。outbox 里 `meili_index` / `graph_ingest` 两个 topic 自项目初期就声明在 `DEFAULT_TOPICS`,但**从未实现 processor**(`default_processor_registry` 只注册 `EmbeddingProcessor`),因此永远 `PROCESSOR_DISABLED`。

本设计**真实部署 Meilisearch + FalkorDB 两个独立引擎**,实现对应 processor 接入现有 outbox 管线,并将其作为检索/图谱的**唯一路径**——彻底删除 PG tsvector 全文与递归 SQL 图谱旧逻辑,**不保留降级兜底**(用户明确选择)。

### 用户确认的关键决策
- 要真实引擎(非 PG 增强模拟)
- 图库选 **FalkorDB**(基于 Redis,单容器轻量,Cypher;优于 Neo4j 的内存占用,优于 PG+AGE 的安装复杂度)
- graph_ingest 范围:**同步现有 `resource_edges` 关系进图**(非 LLM 实体抽取)
- PG 全文/图谱旧逻辑:**彻底删除,无降级**

## 2. 架构总览

```
资源写入 → resource_outbox 三个 topic 并行:
  ├ embedding_generate → EmbeddingProcessor → pgvector        (已有)
  ├ meili_index        → MeiliProcessor     → Meilisearch     (新增)
  └ graph_ingest       → GraphProcessor     → FalkorDB         (新增)

检索 tools:
  ├ search_resources          → Meilisearch(唯一,删 PG tsvector)
  ├ semantic_search_resources → pgvector(不变)
  └ graph_expand              → FalkorDB Cypher(唯一,删递归 SQL)
```

两个新引擎为 Docker 容器,与现有 `pg-db` 容器并列,均只绑 `127.0.0.1`。

**核心对称性**:两个新 processor 完全复刻 `EmbeddingProcessor` 的 `Processor` 协议(`topic` / `state()` / `process()`),注册进 `default_processor_registry`。**已核对确认**:`process_outbox_batch` / `process_outbox_item` 对 `registry.topics` 全部一视同仁地 lease 并按 `state_for(topic)` 判定,普通 topic(meili/graph)走完整处理路径,**不需要 embedding 那样的 reconcile 分支,无需改 scheduler/outbox_worker**。embedding 的 reconcile 是其独有的增量索引逻辑。

**权限边界(重点)**:Meili / Falkor 都**不存 ACL**,只存可搜索内容 / 关系。检索 tool 拿到引擎返回的 resource_id 后,**一律回 Postgres 用 `readable_resource_where` 裁决可见性**。多租户/权限隔离不被引擎绕过。

## 3. 组件设计

### 3.1 MeiliProcessor(`data_foundation/processors/meili.py`,新建)
- `topic = "meili_index"`
- `state()`:依 `XHS_MEILI_URL` / `XHS_MEILI_KEY` 是否配置判 active / disabled(对齐 EmbeddingProcessor 用 config 判定的模式)
- `process(item, lease)`:取 payload 的 resource_id/version → 读 resource 的 title/summary/content_text/type/table_name → upsert 进 Meili `resources` 索引(文档主键 = resource_id;`tenant_id`、`type` 设为 filterable;title/content_text/summary 设为 searchable)→ `assert_owned` 后返回 succeeded
- 幂等:Meili 按文档主键 upsert,重复处理覆盖同一文档

### 3.2 GraphProcessor(`data_foundation/processors/graph.py`,新建)
- `topic = "graph_ingest"`
- `state()`:依 `XHS_FALKOR_URL` 是否配置判 active / disabled
- `process(item, lease)`:读该 resource 节点信息 + 它在 `resource_edges` 的所有出边 → Cypher `MERGE` 节点 `(:Resource {id, tenant_id, type, title})` 与边(按 edge_type,如 derived_from;边带 `weight` 与 `properties`)→ succeeded。`resource_edges` 字段已核对:`source_resource_id/target_resource_id/edge_type/weight/properties/tenant_id`。现存边数据:`derived_from` 7 条(feedback_on/measured_by 边类型动态支持,暂无数据)。
- **边端点占位**:MERGE 一条边时,target 节点可能尚未被自己的 graph_ingest 任务处理。故对 target 也 `MERGE (:Resource {id})` 仅建占位节点(不写属性);target 自己的任务跑到时再 MERGE 补全 title/type 等属性。避免边因端点缺失而丢失。
- 幂等:`MERGE` 保证节点/边不重复创建
- **不处理删除**:项目 resource 只 upsert 新版本、不物理删除,故 Graph/Meili 均不实现删除清理(隐含假设显式声明)。

### 3.3 检索 tools 改造
- `search_resources`:`data_foundation.search.keyword_search` 与 `repository.keyword_rows`(tsvector/ILIKE SQL)**删除**,改为查 Meili(带 tenant_id filter)→ 得**有序** resource_id 列表(Meili 相关性排序)→ 回 PG 过 `readable_resource_where` + 取 title/summary/时效 → **按 Meili 原顺序返回**(PG 只做权限过滤,不重排)。无 Meili 降级。
- `graph_expand`:`repository.graph_rows`(递归 SQL)**删除**,改为 FalkorDB Cypher 有界扩展(hops/edge_types)→ 得 node/edge → 回 PG 过权限 → 返回。无 SQL 降级。
- `semantic_search_resources`:**不动**。
- **outbox 请求接线(已核对真实代码与运行数据,纠正前稿误判)**:
  - `default_write_requests()` 返回 `meili_index` + `graph_ingest` 两个**声明式**请求(payload `{}`、dedupe_parts `("search",)`/`("graph",)`),被 6 处写入路径调用(creation_memory、performance_feedback、feishu_sync、sources/postgres)。
  - **payload 补全机制**:`repository.upsert_resource` 在 enqueue 时对每个 request 做 `{**request.payload, "resource_id": row.id, "version": version}`,自动补上 resource_id/version。故最终入库的 meili/graph 任务 payload **已带 resource_id+version**(运行数据已确认:blocked 任务 payload = `{'version':1,'resource_id':'...'}`)。
  - **结论:接线机制本来就正确,无需改 default_write_requests。** 这些 meili/graph 任务一直在正常 enqueue,只因 processor 未实现(`PROCESSOR_DISABLED`)而 `blocked`。embedding 任务则由 `reconcile_tenant` 单独 enqueue(带 embedding_index_id)。
  - processor 上线 + scheduler `unblock_available` 后,存量 blocked 任务自动转 pending 被处理,**无需清理重建**(payload 已就绪)。`default_resource_requests`(仅测试在用)是历史冗余,可顺手删。

## 4. 部署与配置

### 4.1 Docker 服务(服务器,与 pg-db 并列,只绑 127.0.0.1)
- Meilisearch:`getmeili/meilisearch`,`127.0.0.1:7700`,带 `MEILI_MASTER_KEY`,`--restart unless-stopped`
- FalkorDB:`falkordb/falkordb`,`127.0.0.1:6379`,`--restart unless-stopped`

### 4.2 Python 依赖(pyproject.toml)
- `meilisearch`(官方同步客户端)
- `falkordb`(官方客户端,基于 redis-py)

### 4.3 配置(deploy-only;服务器 .env 维护,纳入 config_center 分类)
- `XHS_MEILI_URL=http://127.0.0.1:7700`
- `XHS_MEILI_KEY=<master key>`(纳入 SECRET_KEYS)
- `XHS_FALKOR_URL=redis://127.0.0.1:6379`
- `XHS_FALKOR_GRAPH=xhs`
- 四者纳入 `config_center.DEPLOY_ONLY_KEYS`;`.env.example` 文档化

processor `state()` 依配置在否判 active/disabled——**这即"启用"的真实语义**:配置就绪则 active,scheduler 自然开始派发该 topic 任务。

## 5. 错误处理(对齐现有 outbox 语义)
- 引擎连不上/超时 → 普通异常 → outbox `failed`(可重试)
- payload 缺字段/resource 不存在 → `PermanentProcessingError` → `blocked`
- 客户端调用经线程池(已有 `--allow-blocking` 兜底 blockbuster)
- 检索 tool 引擎调用失败 → 返回 `{"ok": false, "error": ...}`(无 PG 降级,用户选择)

## 6. 死代码清除
1. **物理删代码**:`repository.keyword_rows`(tsvector SQL)、`repository.graph_rows`(递归 SQL)、`search.keyword_search`;`default_resource_requests`(仅测试引用的历史冗余);`feishu_bitable` 多表改造残留的快照兜底与 `sync_service` 未用的 table_id config。**注意**:`default_write_requests` **不删**(是正常工作的接线,配合 repository 补 payload)。
2. **数据库僵尸任务**:meili/graph 的 blocked 任务 payload **已就绪**(带 resource_id),无需清理——processor 上线 + `unblock_available` 即自动转 pending 处理。仅需清理缺 `embedding_index_id` 的早期 embedding 任务(若仍有)。用定向 delete,不裸 drop。
3. 相关测试同步重写(删 tsvector/递归 SQL 断言;删 `default_resource_requests` 相关测试)

## 7. 测试(分两层)
- **单测(本地写、随代码提交,mock 引擎客户端)**:验证 processor 的 process 逻辑、state 判定、检索 tool 在引擎返回后的权限过滤/排序保持。mock 不连真实引擎,纯逻辑验证。
- **真实验证(全部在服务器,遵 CLAUDE.md:不在本地跑功能验证)**:
  - 集成:真 Meili/Falkor 起来后,sync 一条 → Meili 能搜到 + Falkor 有节点/边
  - 端到端:agent search 走 Meili、graph_expand 走 Falkor、权限过滤生效、引擎不可用时 tool 返回 ok:false

## 8. 分阶段实施(每阶段独立部署 + 服务器验证)
- **阶段 1 基础设施**:部署 Meili + FalkorDB 两个 Docker 服务,装客户端库,配 .env / config_center / .env.example
- **阶段 2 全文**:MeiliProcessor + search_resources 切 Meili + 删 PG 全文 SQL + default_write_requests 加 meili_index
- **阶段 3 图谱**:GraphProcessor + graph_expand 切 Falkor + 删递归 SQL + default_write_requests 加 graph_ingest
- **阶段 4 收尾**:死代码清除 + 全链路端到端验证。**回填存量**:meili/graph blocked 任务 payload 已就绪,processor 上线后 scheduler 每轮 `unblock_available` 自动转 pending 处理,无需手动回填;只需确认 508 条全部进 Meili 索引 + FalkorDB(约数分钟跑完)。

## 9. 风险与权衡
- **无降级(用户明确选择)**:Meili/Falkor 容器挂掉时,检索/图谱直接返回 ok:false,agent 退回"功能不可用"。单机 Docker 服务存在 OOM/重启导致的不可用窗口。缓解:两容器 `--restart unless-stopped` 自动拉起。
- **单机资源**:服务器已有 pg-db,新增两容器(Meili 约数百 MB,FalkorDB 基于 Redis 内存型,数据量小占用可控)。需关注总内存。
- **回填**:启用后存量 508 条需重新 enqueue meili/graph 任务(reconcile 或手动触发),约数分钟。

