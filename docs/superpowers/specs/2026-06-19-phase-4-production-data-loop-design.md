# 第四阶段：生产级数据闭环设计

- 日期：2026-06-19
- 状态：设计稿，等待用户 review
- 范围：同步闭环、检索增强创作、创作沉淀、效果反馈、轻量运维闭环

## 1. 目标

第四阶段不是重做智能体，也不是替换 DeepAgents。目标是在现有 Web 对话 + DeepAgents/LangGraph 多 Agent 架构上，把第三阶段已经完成的 Postgres 通用数据底座真正跑成生产闭环：

1. 飞书等外部协作数据持续沉淀到 Postgres。
2. Agent 写文案前能从 Postgres 检索事实、案例、风格和关系。
3. Agent 生成的选题、文案、分析、用户反馈也沉淀回 Postgres。
4. 发布后的效果数据进入同一资源体系，反过来影响后续选题和文案。
5. 整个系统只通过 Web 对话面向用户，不再保留项目自有业务 CLI 运行入口。

## 2. 产品定位

这个系统是一个基于 DeepAgents 的小红书内容智能体平台。用户在 Web 对话中提出内容方向、修改意见或数据问题；后端 DeepAgents 多 Agent 协作读取通用数据底座，分析爆款规律，产出选题和小红书文案，并把结果沉淀成后续可复用的知识。

底层数据不是小红书专用，也不是飞书专用。Postgres 是权威数据底座；飞书、数据库、未来其他业务系统都是数据来源或协作出口。

## 3. 不可突破的边界

1. Web 对话是唯一用户入口。
2. 彻底移除项目自有业务 CLI，不允许 `python sync_xxx.py`、`python agent_cli.py` 这类命令成为业务运行入口。
3. 不做管理后台，不新增面向用户的管理 dashboard。
4. DeepAgents/LangGraph 继续作为原生 Agent runtime，不 fork、不 monkey-patch、不访问 compiled graph 私有字段。
5. Agent 只能通过 LangChain tools 访问数据能力，不能直接执行 SQL、Cypher 或 lark-cli。
6. 飞书 CLI 只作为内部适配器，被后端服务或工具封装调用，不暴露给用户，也不成为业务入口。
7. 运维脚本只允许用于部署、健康检查、备份、回滚等平台操作，不允许承载业务同步或 Agent 行为。
8. 高风险写操作继续走 DeepAgents `interrupt_on` 或明确的人类确认。
9. 所有 Agent 侧新增能力必须映射到 DeepAgents/LangGraph 官方扩展点；如果某个能力找不到官方扩展点承载，就不能直接塞进 Agent runtime。

## 4. DeepAgents / LangGraph 原生边界

第四阶段必须依托 DeepAgents 和 LangGraph 的官方使用方式来扩展：

1. 使用 `create_deep_agent(...)` 组装主智能体。
2. 使用 `tools=[...]` 注册普通 LangChain tools。
3. 使用 `subagents` 保持多 Agent 协作。
4. 使用 `middleware` 做模型路由、质量检查、重试等横切能力。
5. 使用 `backend` / memory / checkpointer 保存会话和 Agent 状态。
6. 使用 `interrupt_on` 做需要人工确认的动作边界。
7. 使用 `RunnableConfig` 读取当前 Web 用户身份和租户上下文。
8. 使用 LangGraph server + Web 前端作为运行入口。

Postgres、`sync_runs`、outbox worker、定时同步、embedding worker、资源图谱、创作沉淀和效果反馈不是 DeepAgents 官方内置模块，也不需要伪装成 DeepAgents 内核能力。它们属于应用服务层。它们通过稳定的服务函数和 LangChain tools 暴露给 DeepAgents，保持在官方扩展点之内。

### 4.1 官方扩展方式落位矩阵

第四阶段全部按官方扩展方式落位：

| 能力 | 官方扩展点 | 设计约束 |
| --- | --- | --- |
| 数据检索 | `create_deep_agent(tools=[...])` + LangChain tools | Agent 只调用 `search_resources`、`semantic_search_resources`、`graph_expand`、`get_resource` 等工具，不直连数据库 |
| 手动同步 | LangChain tool + `RunnableConfig` 用户上下文 | Web 对话触发 `sync_feishu_resources`，工具内部调用应用服务层，不出现业务 CLI |
| 数据状态查询 | LangChain tool | `get_data_foundation_status` 返回结构化状态，LLM 负责解释给用户 |
| 文案创作 | DeepAgents 主智能体 + Skills + LLM | LLM 生成选题和文案，检索工具只提供上下文和依据 |
| 爆款分析 | `subagents` | 继续用专用子智能体承接分析任务，主智能体只接收压缩后的结论 |
| 质量检查 | `middleware` / rubric | 文案质量、数据依据、AI 腔检查放在 middleware 或评分子流程，不改 graph 私有结构 |
| 人工确认 | `interrupt_on` | 发布、外部写入、批量覆盖等高风险动作必须可中断确认 |
| 会话和长期状态 | `backend` / memory / checkpointer | 会话状态、文件状态和长期记忆走官方后端接口，不自建旁路会话机制 |
| 权限身份 | `RunnableConfig` | 工具从配置读取当前用户、租户、飞书身份，权限在工具/服务层过滤 |
| Web 运行入口 | LangGraph server + Web frontend | 不恢复项目业务 CLI，不新增管理后台 |
| 后台同步 | 应用服务层，非 Agent runtime | scheduler/outbox 可以与后端进程同启，但只能调用 repository/service，不挂进 DeepAgents 内核 |
| 图谱与 embedding | 应用服务层 + tools 查询 | 计算和索引在 worker/service，Agent 通过 tools 读取结果 |

这张表是实现阶段的硬约束。任何新增代码如果不能放入上表某个位置，需要先回到设计阶段补充边界，不能为了方便直接绕过 DeepAgents/LangGraph。

### 4.2 当前非官方扩展路径审计

现有代码里仍有几条历史路径没有完全落到官方扩展方式。第四阶段实施时必须一起收敛：

| 当前路径 | 问题 | 改造目标 |
| --- | --- | --- |
| `lark_mcp_server.py::execute_lark_command` | 通过 MCP 暴露飞书命令，但没有贯通 `RunnableConfig` 用户身份；形式上是 MCP tool，身份边界不完整 | 优先直接把 `tools.lark_cli.lark_cli` 作为 LangChain tool 挂入 `create_deep_agent(tools=[...])`；若继续保留 MCP，必须证明 MCP 能透传当前用户身份 |
| `web/src/app/api/feishu/sync/route.ts` -> `tools/web_bridge_runner.py --action sync` | 前端按钮直连 Python runner 写飞书 Base，绕过 DeepAgents tool、middleware 和 `interrupt_on` | 改为 `save_generated_copy` / `sync_copy_to_feishu` LangChain tool，由 Web 对话触发；写飞书前走 `interrupt_on` |
| `web/src/app/api/feishu/notify/route.ts` -> `tools/web_bridge_runner.py --action notify` | 前端按钮直连 Python runner 发飞书消息，绕过 Agent 官方工具链和人工确认 | 改为 `send_review_notification` LangChain tool，由 Agent 调用；发送前走 `interrupt_on` |
| `tools/web_bridge_runner.py` 多 action runner | 不是交互式业务 CLI，但承载了业务动作、配置动作、认证动作，边界混杂 | 只保留认证/配置桥接等平台动作；业务动作迁移到 Agent-facing LangChain tools，底层再调用应用服务层 |
| `agent.py::get_lark_mcp_tools()` 启动时同步拉 MCP tools | MCP 是官方扩展点，但当前在 import 阶段开线程取工具，生命周期和错误边界不清 | 第四阶段优先使用显式 LangChain tools；通用飞书能力若保留 MCP，需要有启动失败降级、身份透传和测试覆盖 |

不需要改成 Agent tool 的平台路径：

1. Web 登录、飞书 OAuth callback、UAT 保存。
2. 配置中心读写、模型配置保存、后端 apply/restart。
3. Web 健康检查、后端健康状态、部署和回滚脚本。
4. Postgres repository、schema、outbox、scheduler、embedding worker 的内部服务函数。

这些路径可以保留在应用服务层或平台控制面，但不能直接承载“写飞书、发通知、同步文案、发布内容”等用户业务动作。

## 5. LLM 在文案中的职责

文案生成仍然由 LLM 完成，而且这是系统的核心能力。数据底座、图算法、向量检索和同步机制不生成最终文案，它们为 LLM 提供更可靠的上下文。

LLM 负责：

1. 理解用户意图、内容方向、语气和修改要求。
2. 决定需要调用哪些工具检索数据。
3. 综合爆款案例、历史文案、用户反馈、效果数据和品牌约束。
4. 生成选题、标题、正文、标签和多版本改写。
5. 判断内容是否像真人小红书笔记，避免 AI 腔和空泛营销话术。
6. 在质量检查中重写不合格内容。
7. 把生成结果整理成可复制、可沉淀、可追踪来源的结构。

数据系统负责：

1. 提供可检索的事实、案例、历史内容和关系。
2. 提供来源、权限、版本、时间和效果指标。
3. 支持关键词检索、向量检索、图谱扩展和去重。
4. 记录生成结果和反馈，形成长期记忆。

因此第四阶段的目标不是“数据库替代 LLM”，而是“LLM + 私域数据 + 图谱/检索 + 反馈闭环”。文案表达、创意组合和最终输出始终由 LLM 完成。

## 6. 总体架构

```text
Web 对话
  -> LangGraph Server
  -> DeepAgents 主智能体
  -> SubAgents / Skills / Middleware
  -> LangChain Tools
  -> Application Services
  -> Postgres Data Foundation
```

后台服务与 Agent runtime 并行存在：

```text
Backend Process
  -> LangGraph Server
  -> Scheduler
  -> Outbox Worker
  -> Sync Service
  -> Repository
  -> Postgres
```

第一版可以让 scheduler/outbox worker 跟后端进程一起启动，后续再拆成独立 worker。无论是否拆进程，都不改变用户入口，也不新增业务 CLI。

## 7. 四个业务闭环

### 7.1 外部数据沉淀闭环

飞书 Base、飞书 Wiki、飞书文档、未来业务数据库等外部来源进入统一 `resources` 表。同步过程记录到 `sync_runs`，资源变更写入 `resource_events` 和 `resource_outbox`。

同步有两种触发方式：

1. 定时自动同步。
2. Web 对话中由 Agent 调用受控工具手动触发。

手动触发不是 CLI，而是 DeepAgents 的工具调用；定时触发是后端应用服务，不是用户入口。

### 7.2 检索增强创作闭环

用户要求写选题或文案时，Agent 先通过工具检索：

1. `search_resources`：关键词检索。
2. `semantic_search_resources`：向量语义检索。
3. `graph_expand`：从相关资源扩展到作者、主题、标签、相似案例和衍生文案。
4. `get_resource`：读取具体资源详情。

LLM 根据检索结果完成创作，并在回复里保留关键来源摘要，避免凭空编造。

### 7.3 创作沉淀闭环

Agent 生成的选题、文案、改写版本、分析结论、用户反馈不再只留在会话里。它们会作为通用资源写入 Postgres：

1. `type=generated_topic`
2. `type=generated_copy`
3. `type=analysis`
4. `type=user_feedback`
5. `type=revision_request`

这些资源继续进入 embedding、图谱和检索索引，成为下一次创作的素材。

### 7.4 效果反馈闭环

发布后的点赞、收藏、评论、转化、发布时间、账号、主题、标题结构等数据进入资源体系。后续创作时，Agent 不只参考“像不像爆款”，还参考真实效果。

效果反馈第一版不做复杂预测模型，先做可解释权重：

1. 高表现内容在检索排序中加权。
2. 低表现内容作为反例保留。
3. 同主题、同人群、同账号、同发布时间段可以被图谱扩展出来。
4. LLM 在写作时明确参考“成功样本”和“避坑样本”。

## 8. 第四阶段分期

### 8.1 Phase 4.1：同步与状态闭环

目标：让数据自动进来，让用户能在 Web 对话里问“数据现在是什么状态”，也能要求 Agent 触发一次同步。

新增能力：

1. `sync_runs` 表，记录同步来源、触发者、状态、统计、错误。
2. `data_foundation/sync_service.py`，统一封装飞书 Base/Wiki 同步。
3. `data_foundation/scheduler.py`，按配置定时触发同步。
4. `data_foundation/outbox_worker.py`，处理资源变更后的索引、embedding、图谱任务。
5. `get_data_foundation_status` tool，供 Agent 查询数据底座状态。
6. `sync_feishu_resources` tool，供 Agent 在 Web 对话中受控触发同步。

第一版 outbox worker 至少处理：

1. `embedding_generate`
2. `graph_ingest`
3. `meili_index` 保持 skipped/pending，直到搜索服务正式接入。

### 8.2 Phase 4.2：检索增强文案

目标：让文案生成稳定使用 Postgres 数据底座，而不是只读飞书当前表。

新增能力：

1. 调整 topic-content skill，让创作流程优先调用统一资源检索工具。
2. 输出选题和文案时带上关键依据摘要。
3. 增加来源不足时的降级话术：明确告诉用户“当前数据不足”，并建议同步或补充数据。
4. 强化 rubric middleware，检查“是否有数据依据、是否引用过时、是否凭空编造”。

### 8.3 Phase 4.3：创作记忆

目标：让 Agent 产出的内容反向成为数据资产。

新增能力：

1. `save_generated_topic` tool。
2. `save_generated_copy` tool。
3. `save_user_feedback` tool。
4. 生成内容与来源资源建立 `resource_edges`。
5. 同一次创作过程产生 `resource_events`，可回溯“从哪些数据生成了哪篇文案”。

### 8.4 Phase 4.4：效果反馈

目标：把发布效果变成下一轮创作的依据。

新增能力：

1. `performance_metric` 类型资源或结构化 metadata。
2. 内容与效果数据的图谱边。
3. 检索排序加入表现权重。
4. Agent 能回答“为什么推荐这个方向”“这个方向过去表现如何”。

### 8.5 Phase 4.5：运维闭环

目标：生产环境可持续运行，不靠临时人工命令维持状态。

新增能力：

1. 健康检查覆盖 Postgres、LangGraph server、Web、scheduler、outbox。
2. 同步失败、outbox 积压、embedding 连续失败有明确状态。
3. 部署、回滚、备份只作为平台运维动作，不承载业务入口。
4. Web 对话可以查询系统状态，但不提供管理后台。

## 9. 同步身份模型

同步需要区分两个身份：

1. `actor_open_id`：谁触发了同步，用于审计。
2. `source_credential`：用什么凭证读取飞书或其他来源。

手动同步使用当前 Web 用户身份作为 actor，并优先使用当前用户可用的飞书授权。定时同步使用 `system:scheduler` 作为 actor，并使用服务端配置的系统授权。缺少授权时，同步不静默失败，要写入 `sync_runs` 并让 `get_data_foundation_status` 返回可见错误。

## 10. 并发与锁

同一租户、同一数据源、同一同步类型同一时间只允许一个运行中任务。

1. 使用 PostgreSQL advisory lock 控制同步互斥。
2. 手动同步遇到锁冲突时，返回“已有同步正在运行”。
3. 定时同步遇到锁冲突时跳过本轮，并记录 skipped。
4. outbox worker 使用 `FOR UPDATE SKIP LOCKED` 领取任务。
5. outbox 失败按 `attempts`、`available_at`、`last_error` 做重试和退避。

## 11. 配置

建议新增配置：

```env
XHS_SYNC_ENABLED=false
XHS_SYNC_INTERVAL_SECONDS=1800
XHS_SYNC_STARTUP_DELAY_SECONDS=30
XHS_SYNC_BATCH_SIZE=100
XHS_SYNC_SYSTEM_ACTOR=system:scheduler

XHS_OUTBOX_ENABLED=true
XHS_OUTBOX_INTERVAL_SECONDS=300
XHS_OUTBOX_BATCH_SIZE=20
XHS_OUTBOX_MAX_ATTEMPTS=5

XHS_RESOURCE_CHUNK_SIZE=1200
XHS_RESOURCE_CHUNK_OVERLAP=160
```

本地默认可以关闭定时同步；服务器按部署环境开启。配置热生效继续沿用第二阶段的配置中心能力，不为第四阶段新增 CLI 配置入口。

## 12. Agent 工具返回格式

`get_data_foundation_status` 返回：

```json
{
  "ok": true,
  "tenant_id": "default",
  "resources": {
    "total": 128,
    "by_type": {
      "feishu_base_record": 80,
      "feishu_wiki_doc": 32,
      "generated_copy": 16
    }
  },
  "sync": {
    "last_success_at": "2026-06-19T12:30:00Z",
    "last_status": "success",
    "running": false
  },
  "outbox": {
    "pending": 12,
    "failed": 0
  }
}
```

`sync_feishu_resources` 返回：

```json
{
  "ok": true,
  "run_id": "uuid",
  "status": "completed",
  "created": 12,
  "updated": 6,
  "skipped": 80,
  "failed": 0
}
```

这些结构化结果给 LLM 使用，前端仍只展示 Agent 整理后的自然语言和结构化文案卡片。

## 13. 图算法与数据结构

第四阶段不引入重型图数据库作为必需项。Postgres 继续作为权威存储，使用 `resource_edges` 表承载图关系。

第一版图能力采用：

1. 邻接表：`resource_edges(source_resource_id, target_resource_id, relation_type, weight)`。
2. 有界 BFS：从命中资源向外扩展 1 到 2 跳。
3. 权重排序：按关系类型、资源新鲜度、效果数据、相似度综合排序。
4. 去重与可见性过滤：所有扩展结果必须经过租户和权限过滤。
5. 防环：记录 visited 节点，避免循环扩展。

不一开始引入复杂图算法如 PageRank、社区发现或 GraphRAG 框架。只有在资源规模和查询需求证明必要后，再做离线权重计算或图数据库增强。

## 14. 错误处理

1. 同步失败要写入 `sync_runs.error` 和 outbox 错误状态。
2. 单条资源失败不应中断整个批次，批次最终状态可以是 partial_success。
3. embedding provider 不可用时，关键词检索仍可工作。
4. 图谱构建失败不影响资源入库。
5. Agent 手动触发同步超时时，应返回 run_id 和当前状态，允许之后查询。
6. 权限不足时，工具只返回用户可见资源，不暴露资源存在性细节。

## 15. 测试策略

1. Repository 单元测试：`sync_runs`、锁、outbox 领取、状态统计。
2. Service 测试：同步成功、部分失败、重复同步幂等。
3. Tool 测试：`RunnableConfig` 身份解析、权限过滤、错误返回。
4. Agent 装配测试：新工具进入 `create_deep_agent(tools=...)`。
5. Web UAT：用户从对话触发同步、查询状态、生成基于资源的文案。
6. 生产冒烟：服务器健康检查、PM2 进程、Postgres 扩展、同步状态。

## 16. 验收标准

1. 用户只通过 Web 对话完成数据状态查询、同步触发和文案创作。
2. 项目不存在业务 CLI 运行入口。
3. DeepAgents 原生装配方式不被破坏。
4. 飞书数据可以自动沉淀到 Postgres。
5. 生成文案会使用 LLM，并能引用 Postgres 中的来源依据。
6. 生成内容可以作为资源沉淀，后续可检索。
7. 同步、outbox、embedding、图谱失败都有可查询状态。
8. 不新增管理后台。

## 17. 风险与决策

1. 风险：把同步、worker、Agent 工具混在一起会让边界变乱。决策：同步和 worker 属于应用服务层，Agent 只能通过工具触发或查询。
2. 风险：用户误以为数据库替代 LLM 写文案。决策：文案生成明确由 LLM 完成，数据底座只提供依据、记忆和反馈。
3. 风险：过早引入复杂图算法导致实现膨胀。决策：先用 Postgres 邻接表 + 有界 BFS + 权重排序。
4. 风险：无管理后台导致状态不可见。决策：通过 Web 对话工具返回系统状态，不做独立后台。
5. 风险：定时同步凭证不清。决策：明确 actor 和 source credential 分离。

## 18. 暂不做

1. 不做管理后台。
2. 不恢复业务 CLI。
3. 不引入独立图数据库作为必需依赖。
4. 不把 scheduler/outbox 写进 DeepAgents 内核。
5. 不让前端直接解析业务数据生成文案。
6. 不让数据库、搜索引擎或图算法替代 LLM 写文案。

## 19. 官方依据

本设计遵守 DeepAgents / LangGraph 的公开扩展边界：

1. Deep Agents 官方定位是基于 LLM 的 agent harness，支持规划、文件系统、子智能体、长期记忆和人工确认等能力。
2. Deep Agents 官方支持通过 `create_deep_agent(tools=...)` 接入自定义函数、LangChain tools 和 MCP tools。
3. Deep Agents 官方支持通过 `subagents` 参数定义专用子智能体，让主智能体把复杂任务委派给隔离上下文。
4. Deep Agents 官方支持 pluggable backends，用于状态、文件系统、存储和持久化能力。
5. Deep Agents 官方支持 human-in-the-loop，在关键工具调用前暂停等待批准。

第四阶段的 Postgres 数据底座、同步服务、outbox worker、embedding worker 和资源图谱不是 DeepAgents 官方内置功能。它们是应用服务层能力，必须通过官方 tools/subagents/backend/middleware/human-in-the-loop 等扩展点接入，而不是修改 DeepAgents 内核。

参考：

1. https://docs.langchain.com/oss/python/deepagents/overview
2. https://docs.langchain.com/oss/python/deepagents/tools
3. https://docs.langchain.com/oss/python/deepagents/subagents
4. https://docs.langchain.com/oss/python/deepagents/backends
5. https://docs.langchain.com/oss/python/deepagents/human-in-the-loop
