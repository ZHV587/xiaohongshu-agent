# 小红书文案智能体

基于 [deepagents](https://github.com/langchain-ai/deepagents) 的小红书文案创作智能体。
从飞书多维表格读取爆款数据,分析套路,产出小红书选题与文案。

## 环境准备

1. 安装依赖(需 [uv](https://docs.astral.sh/uv/)):
   ```bash
   uv sync
   ```
2. 复制 `.env.example` 为 `.env`,填入:
   - 模型网关:`LLM_PROVIDER` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_QUALITY_MODELS`
   - 飞书自建应用:`FEISHU_APP_ID` / `FEISHU_APP_SECRET`
   - 爆款表定位:`FEISHU_BITABLE_APP_TOKEN` / `FEISHU_BITABLE_TABLE_ID`
   - 管理员白名单:`XHS_ADMIN_OPEN_IDS`

## 多用户部署关键配置

- `XHS_ADMIN_OPEN_IDS`: 逗号分隔的飞书 open_id,只有这些用户能访问系统配置。
- `XHS_UAT_ENCRYPTION_KEY`: 飞书用户令牌(UAT)落盘加密密钥,必须与 `XHS_JWT_SECRET` 不同。两者解耦后,JWT 签名密钥泄露不会同时导致存储的飞书用户令牌可被解密;留空时回退用 `XHS_JWT_SECRET` 派生并打告警,生产部署应配置独立密钥。
- `XHS_BACKEND_APPLY_MODE`: `.env` 回退模式下使用 `manual`、`pm2` 或 `systemd`。配置中心开启后，embedding 配置不走重启生效，而是由 scheduler 新建索引后切换。
- `LLM_PROVIDER`: 第一阶段生产路径建议固定为 `openai`。
- `LLM_QUALITY_MODELS`: 高质量模型池,逗号分隔;第一项是首选模型。
- 飞书操作在 server 模式下默认使用当前用户 UAT,缺授权时不会静默退回 bot。

## 运行与部署方式

### 1. 本地开发与调试 (Local Dev)
本地单独调试后端：
```bash
uv run langgraph dev
```
默认起在 `http://127.0.0.1:2024`。

本地调试前端 (Next.js)：
```bash
cd web
npm run dev
```

### 2. 生产环境部署 (Docker Compose)
项目在生产服务器上使用 **Docker Compose** 进行全栈六容器统一编排部署：

```bash
# 1. 编译后端智能体最新镜像
langgraph build -t xhs-langgraph:latest

# 2. 现场构建前端并拉起全部服务
docker compose up -d --build
```
启动后，全栈组件（`xhs-langgraph`, `xhs-web`, `xhs-pg`, `xhs-redis`, `xhs-meili`, `xhs-falkor`）会在专有的内部有界网络中自动互联，仅 `xhs-web` 前端容器对公网映射 `9091` 端口。

---

## 存储边界

- Postgres 是业务数据唯一权威源：资源、证据关系、选题、文案、反馈、效果指标、诊断、报告和决策快照均写入数据库。
- 飞书是协作与展示镜像：已确认且需要团队查看的业务资产在数据库写入成功后同步飞书；通知和审批等瞬时协作动作可仅走飞书。
- 本地文件不保存业务数据。`/skills/` 只提供只读工作流定义；`/memories/` 与 `/user-memories/` 仅用于 DeepAgents 内部运行记忆。

## 第二阶段配置中心与热切边界

- 配置中心由 `XHS_CONFIG_CENTER_PATH` 指向的加密文件提供，`XHS_CONFIG_ENCRYPTION_KEY` 是启动级密钥，不能通过 UI 修改。
- phase-2 模式开启条件：同时设置 `XHS_CONFIG_ENCRYPTION_KEY` 与 `XHS_CONFIG_CENTER_PATH`。开启后 `/api/config` 读写配置中心并返回当前配置版本；未开启时保留 `.env + apply` 的 phase-1 回退。
- 管理员配置页和 `/api/config` 管理员接口按当前私人项目决策返回明文配置，便于直接检查和修改；日志、错误摘要、outbox payload、telemetry 和普通状态接口仍不得输出密钥。
- `XHS_INTERNAL_BASE_URL` 与 `XHS_INTERNAL_SECRET` 是 deploy-only 配置，不进入管理员配置中心历史版本或状态 API。
- 已纳入无重启热切的路径：主 agent 的 `ModelRouterMiddleware` sync/async 调用、子 agent 的 `ModelRouterMiddleware` 调用，以及 rubric 评分模型——后者经 `RegistryRoutedChatModel`(`rubric_model.py`)在每次评分时取 registry 当前最强候选，registry 空时回退 import-time 占位实例，故 config-center 热重载后下一次评分即生效，无需重启。
- 模型池构建(`build_pool_from_config`)对多网关的探测为并发执行：墙钟收敛到最慢的单个网关(`_DISCOVER_TIMEOUT`≈5s),与网关数量解耦,加速启动对齐、定时健康探测与配置 verify。
- `tools/web_bridge_runner.py` 不再是 Web 生产请求主路径；仅允许作为配置恢复或维护工具使用，且 degraded fallback 必须明确返回降级状态。进程内 registry reload 必须通过 LangGraph 后端进程内管理通道或 supervisor/sidecar 完成。
- Embedding 热生效以配置中心为版本权威：保存 `XHS_EMBEDDING_*` 后配置立即持久化，下一轮 `XHS_SCHEDULER_INTERVAL_SECONDS` scheduler cycle 会用该版本创建或续建 `building` index，回填完成后原子切换为 `active`。
- 旧 `active` index 在新 index 完成前继续服务语义搜索；查询会按 index 记录的 `config_version` 回放历史 embedding profile，不会误用刚保存的新模型或新密钥。
- 仅环境变量模式无法查询历史配置版本，因此 embedding profile 变化仍属于后端应用/重启边界；生产部署应开启配置中心。
- 不 fork DeepAgents，不 monkey-patch DeepAgents，不访问 compiled graph 私有字段。

## 第三阶段数据底座

- `XHS_DATABASE_URL` 指向 Postgres 权威业务库；底层通用数据沉淀不绑定单一飞书来源，飞书 Base/Wiki/Doc 只是 ingestion adapter。
- 数据库必须启用 `pgcrypto` 与 `vector` 扩展；关键词检索走 Postgres full-text + `ILIKE` 中文兜底，语义检索走 pgvector。
- `XHS_DEFAULT_TENANT_ID` 默认是 `default`；Agent tool 不接受自由 tenant 参数，tenant 和 actor 权限在服务端解析。
- Embedding 只使用显式 `XHS_EMBEDDING_*` 配置；未配置 `XHS_EMBEDDING_API_KEY`、没有 active embedding index，或 active index 的历史 profile 不可用时，语义搜索结构化降级为关键词搜索，不回退到 `LLM_*` 文案模型配置。
- DeepAgents/LangGraph 仍是唯一 agent runtime；第三阶段只新增普通 LangChain tools 并挂入 `create_deep_agent`。
- Web 内部请求通过 LangGraph `http.app` 的 `/internal/*` routes 访问 Python 能力；Next 负责用户/管理员 cookie 鉴权，并用 `XHS_INTERNAL_SECRET` 调用内部 route。
- `/internal/health/facts` 由内部密钥和管理员 open_id 双重校验；数据库不可用时接口仍返回 200 的局部模块事实，但不会把 DSN、API key、Authorization header、credentials、outbox payload、正文 chunk 或异常详情写入响应/日志。
- 项目不恢复交互式 Python CLI 运行入口；飞书 `lark-cli` 只作为 server/worker 内部 adapter。
- 飞书写操作不再经过 frontend business API，而是由 Agent tools 发起，并通过 HITL 完成人工确认。
- MCP 是官方工具路径；MCP tools 必须经 interceptor 或等价 adapter 传递受控身份上下文。
- Phase 4.5A 已将同步、outbox、embedding 与运行遥测收敛到 Postgres 事实表；后台服务由 LangGraph `http.app` ASGI lifespan 启停，`XHS_SYNC_ENABLED=true` 只控制 supervisor 是否领取周期任务。
- Phase 4.2 已将选题和文案改为统一资源检索优先：Agent 先检索 Postgres 数据底座，可选语义检索和图扩展，输出可见的关键来源摘要，并区分源端更新时间 `source_updated_at` 与本地索引时间 `indexed_at`；语义检索不可用时回退关键词检索，完全无可用来源时明确提示“当前数据不足”并建议同步或补充数据。
- 内容创作不再直接调用 `read_xhs_data` 或 `read_feishu_wiki` 作为未沉淀兜底；飞书读取只由 Feishu source processor 作为 ingestion adapter 使用，沉淀到 Postgres 后再进入证据链。
- Phase 4.3 已加入创作记忆沉淀：`save_generated_topic`、`save_generated_copy`、`save_user_feedback` 会把选题、文案、反馈/修改意见写入 Postgres，并用 `derived_from` / `feedback_on` 关系连接来源资源。
- Phase 4.4 已加入效果反馈闭环：`save_performance_metric` 会把发布后的点赞、收藏、评论、转发、浏览和转化沉淀为 `performance_metric` 资源，`get_resource_performance` 可读取历史表现；内容资源通过 `measured_by` 边连接效果资源，第一版只做可解释评分，不做预测模型。
- Phase 4 仍通过 DeepAgents 官方 `tools`、`skills`、`subagents` 和 `middleware` 扩展；LLM 负责分析与创作，Postgres 只提供来源、时效和关系上下文，不新增业务 CLI 或管理后台。
- active outbox processor:`embedding_generate`(pgvector 语义)、`meili_index`(Meilisearch 全文)、`graph_ingest`(FalkorDB 图谱)三者均已启用。检索/图谱以引擎为唯一路径:`search_resources` 走 Meilisearch、`graph_expand` 走 FalkorDB、`semantic_search_resources` 走 pgvector;引擎返回 resource_id 后统一回 Postgres 经 `readable_resource_where` 裁决可见性。PG tsvector 全文与递归 SQL 图谱旧逻辑已移除,无降级(引擎不可用时工具返回 `ok:false`)。图谱时序与任务编排不依赖外部组件:图查询由 FalkorDB 承担,同步/索引/入图的调度与重试由 outbox + 幂等 worker 承担;Graphiti、Dagster 不在当前架构中,如需事实演化能力优先走 Postgres 资源版本化。
- `sync_sources.credentials` 按当前开发决策允许明文保存在 Postgres，但凭证不得进入日志、错误摘要、outbox payload、遥测或后续只读状态接口。
- **第五阶段证据检索与服务解耦**：
  - **检索重排序 (Retrieval Ranking)**：`search_resources` 与 `semantic_search_resources` 工具内置 `rank_evidence` 加权排序服务，综合考虑相关度归一化得分、源端时效指数衰减（$e^{-0.05 \times t}$）、资源类型权重（`performance_metric`/`generated_copy`/`generated_topic`）及 $\tanh$ 历史效果表现分，并利用 Python 的 `SequenceMatcher` 进行 $>0.90$ 相似度的标题模糊去重。
  - **模块化前端结构**：`index.tsx` 已重构为状态提供者与布局 Wrapper，将聊天时间线（`ChatTimeline.tsx`）、输入控件（`ComposerPanel.tsx`）、依据分析看板（`EvidenceInspector.tsx`）与飞书协作看板（`RightInspector.tsx`）完全解耦，通过 `ThreadContext` 统一管理状态。

## 测试
```bash
uv run pytest
cd web
.\node_modules\.bin\tsc.CMD --noEmit
.\node_modules\.bin\eslint.CMD src
```

## 文档
- 设计:`docs/superpowers/specs/2026-06-15-xhs-content-agent-design.md`
- 计划:`docs/superpowers/plans/`
- 服务器部署规则:`docs/deployment/server-deployment-rules.md`
