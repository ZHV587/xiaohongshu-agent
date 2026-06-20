# Phase 5：生产化运行、创作智能增强与结构治理设计

- 日期：2026-06-20
- 状态：已确认，待实施计划
- 前置：Phase 2 配置中心、Phase 3 通用数据底座、Phase 4 创作闭环、Phase 4.5A 运行事实表
- 范围：运行入口原生化、只读管理员状态、检索排序增强、效果反馈闭环、Web 结构治理、文档事实收敛

## 1. 背景

项目已经从“飞书读表生成小红书文案”升级为基于 DeepAgents/LangGraph 的 Web 对话式内容生产系统。DeepAgents 负责多 Agent 编排、工具调用、子智能体、middleware、MCP 与 HITL；Postgres + pgvector 是通用数据底座；飞书 Base/Wiki/Doc 只是 ingestion adapter 与协作沉淀层。

当前系统已有：

- Web 对话作为唯一业务入口，项目自有交互式 Python CLI 已移除。
- `langgraph.json` 注册 `agent.py:agent` 与 `data_foundation/http_app.py:app`。
- Postgres schema、资源版本、图边、outbox、sync source、embedding index、telemetry 与 scheduler。
- 配置中心、embedding 热索引、明文管理员配置读取、数据底座工具、创作记忆与效果反馈资源。
- 服务端使用 PM2 运行前后端，后台服务由 LangGraph `http.app` ASGI lifespan 启停。

本阶段不是引入新 runtime，也不是新增管理后台，而是把已成型的系统打磨到更稳定、可观测、可迭代的生产形态。

## 2. 总目标

Phase 5 同时解决三类问题：

1. 运行生产化：减少启动副作用，收敛 Web 到 Python 的内部桥接，基于 LangGraph 官方 ASGI 扩展提供内部状态 API。
2. 创作智能增强：让检索、证据、历史表现和用户反馈真正影响选题与文案策略。
3. 结构治理：拆分高复杂度 Web 文件，收敛旧文档与旧边界，降低后续迭代风险。

验收时系统应满足：

- Agent runtime 仍只使用 DeepAgents/LangGraph 官方扩展面。
- 不 fork DeepAgents，不 monkey-patch，不访问 compiled graph 私有字段。
- Web 仍是唯一业务入口；不恢复项目自有 CLI 运行入口。
- 管理员只读状态页面能解释系统当前是否可用、哪里阻塞、数据是否新鲜。
- 内容生成使用可解释证据与历史表现，不凭空编造。
- 大文件和旧文档不再成为后续改动的主要风险。

## 3. 非目标

- 不做独立管理后台。
- 不引入 Meilisearch、Graphiti、Neo4j/FalkorDB 或 Dagster 的实际部署。
- 不把 Agent 变成自由 SQL/Cypher 执行器。
- 不做预测模型训练或自动投放系统。
- 不做多租户商业化管理台。
- 不恢复项目自有业务 CLI。
- 不改变 DeepAgents/LangGraph 底层框架。

## 4. 官方框架边界

本阶段所有新增能力必须落在官方或项目应用层边界：

- Agent 编排：DeepAgents `create_deep_agent`。
- Agent 能力：LangChain tools、DeepAgents subagents、middleware、skills、MCP。
- 后台服务：`langgraph.json` 的 `http.app` ASGI lifespan。
- 内部 HTTP：Starlette route 挂在 `data_foundation/http_app.py`，由 LangGraph server 承载。
- Web：Next.js 负责用户界面、管理员鉴权、调用 LangGraph/内部 API。
- 数据：Postgres + pgvector 是当前权威业务库和向量库。

禁止：

- import DeepAgents 内部实现路径作为稳定契约。
- 在 `agent.py` import 阶段启动业务后台线程。
- 通过 Web 组件直接访问数据库。
- 通过 prompt 要求模型绕过 tools 访问数据库、CLI 或底层 API。
- 把 disabled processor 的任务标记为 succeeded。

## 5. Phase 5.1 运行接口原生化

### 5.1.1 问题

当前 Next 内部 API 通过 `execFile` 调用 `tools/web_bridge_runner.py` 来执行配置、飞书状态和部分内部查询。这条路径能工作，但有几个长期问题：

- 每次请求启动 Python 子进程，延迟和错误面更大。
- 内部能力散落在脚本参数里，不如 HTTP route 易观测、易鉴权、易测试。
- 与已经存在的 LangGraph `http.app` ASGI 扩展重复。
- 错误处理和日志边界需要靠脚本约定维持。

### 5.1.2 目标设计

将内部能力按用途迁入 `data_foundation/http_app.py` 的 Starlette routes：

- `GET /internal/ok`：基础存活。
- `GET /internal/config`：读取管理员配置，当前私人项目允许明文返回。
- `POST /internal/config`：保存配置中心配置。
- `GET /internal/feishu/status`：查询当前用户飞书 UAT 状态。
- `GET /internal/feishu/chats`：查询飞书会话。
- `GET /internal/feishu/wiki-space`：查询 wiki space 配置或可用状态。
- `GET /internal/data-foundation/status`：只读数据底座摘要。
- `GET /internal/health/facts`：返回 scheduler/outbox/sync/embedding/service telemetry 事实。

Next API route 保留管理员鉴权、cookie/JWT 解析和响应格式适配，然后转发到 LangGraph server 内部 route。第一版可以通过 loopback HTTP 调用，后续再按部署拓扑改为内网地址或同进程方式。

内部 HTTP client 必须显式配置：

- `XHS_INTERNAL_BASE_URL`：Next 服务端访问 LangGraph internal routes 的 base URL。
- `XHS_INTERNAL_SECRET`：Next 与 LangGraph internal routes 之间的共享密钥，沿用现有 deploy-only 配置名，不新增平行密钥名。
- 固定超时、错误码映射和 `Cache-Control: no-store`。

`XHS_INTERNAL_BASE_URL` 与 `XHS_INTERNAL_SECRET` 均为 deploy-only 配置，不能出现在管理员配置页可编辑项、配置中心历史版本、状态页明文响应或普通 API payload 中。

迁移前必须统一 Web 与 Python 的配置 allowlist：

- Web `assertAllowedConfigKeys` 与 Python `ConfigCenter.EDITABLE_KEYS` 共享同一份语义契约。
- config-center 模式下，只有 Python 配置中心明确支持的 key 才能保存。
- `.env` fallback 模式可继续支持 `XHS_BACKEND_APPLY_MODE` 等运行 apply key；若 config-center 不支持这些 key，UI 必须隐藏或禁用对应字段，而不是提交后让 Python 报错。
- deploy-only key 包括 `XHS_ADMIN_OPEN_IDS`、`XHS_JWT_SECRET`、`XHS_INTERNAL_SECRET`、`XHS_INTERNAL_BASE_URL`、`XHS_CONFIG_ENCRYPTION_KEY`、`XHS_CONFIG_CENTER_PATH`、`PATH`、`NODE_OPTIONS`。

`tools/web_bridge_runner.py` 在迁移完成后不能再作为 Web 生产请求主路径。配置读写允许保留一个管理员 break-glass fallback：只有当 LangGraph internal route 不可达时，Next 配置 API 可显式降级到本地维护路径读取/写入配置中心，并在响应中返回 `degraded: true` 与原因。该 fallback 只服务配置恢复，不承载飞书查询、状态页或普通业务请求；若后续有同等恢复能力，应删除。

break-glass fallback 必须满足：

- 只在 Next 与 Python/LangGraph 同机部署且配置中心文件路径可访问时启用。
- 优先复用现有 Python 配置中心读写逻辑，避免在 TypeScript 里重新实现 Fernet 格式。
- 若部署拓扑不满足同机文件访问，fallback 明确返回不可用，而不是静默写入另一份配置。

### 5.1.3 鉴权

内部 route 即使被公网或内网直接访问，也必须拒绝缺少共享密钥的请求。不能只依赖“由 Next 转发”这一假设，因为 `langgraph.json` 当前 custom route auth 不保证覆盖项目自定义鉴权。

Next 转发时必须携带：

- `X-XHS-Internal-Key`：等于 `XHS_INTERNAL_SECRET`。
- `X-XHS-Open-Id`：当前用户 open_id。
- `X-XHS-Is-Admin`：Next 服务端基于管理员白名单计算的结果，仅作为审计/诊断辅助。

Python internal route 不得信任 `X-XHS-Is-Admin` 作为唯一授权依据。它必须在服务端根据 `XHS_ADMIN_OPEN_IDS` 对 `X-XHS-Open-Id` 重新计算管理员身份；header 中的 `is_admin` 与服务端复算不一致时拒绝请求并记录脱敏安全事件。

内部 route 仍要做二次校验，权限矩阵固定为：

- 配置读写、运行事实、管理员状态：必须 internal key 正确，且 Python 端复算 `open_id` 属于管理员。
- 飞书 UAT 保存、UAT 状态、chats、wiki-space：必须 internal key 正确且有当前用户 open_id；只允许访问该用户自己的 UAT 上下文。
- 基础存活 `/internal/ok`：可只要求 internal key，不能返回敏感数据。

非管理员不得读取配置或运行事实。普通用户飞书 route 不得因为管理员状态页需求而被误收紧为 admin-only。

## 6. Phase 5.2 启动确定性

### 6.1 问题

`agent.py` import 阶段仍会根据环境调用飞书 skill/CLI 自动更新。这与业务 CLI 删除不矛盾，因为 `lark-cli` 是内部 adapter；但它会让 graph import 带有网络、文件写入和外部仓库状态副作用。

### 6.2 目标设计

把自动更新从 `agent.py` import 阶段移出，改成显式路径：

- 部署步骤：在发布脚本或服务器维护命令中执行飞书 skill/CLI 更新。
- 或后台服务：由 ASGI lifespan 下的 supervisor 在受控条件下执行一次性更新，记录 telemetry，不阻塞 graph import。

默认生产启动必须满足：

- import `agent.py` 只做 graph 装配。
- 无网络调用。
- 无自动修改 `.agents`、`.lark-cli` 或全局 npm。
- 更新失败不会导致 graph import 失败。

保留 `DISABLE_AUTO_UPDATE` 作为过渡环境变量时，它只能影响受控更新任务，不能成为长期分叉逻辑。

## 7. Phase 5.3 只读管理员状态页

### 7.1 定位

这是管理员可见的“运行状态界面”，不是管理后台。它只读展示事实和诊断，不提供危险写操作。

### 7.2 页面内容

状态页应展示：

- 后端连接状态：LangGraph server、Next API、Postgres。
- 配置版本：当前 config version、embedding config version、是否 config-center。
- Scheduler：是否启用、最近 cycle 时间、最近结果、失败摘要。
- Sync sources：启用数量、到期数量、running 数量、最近同步结果。
- Outbox：pending、retry、processing、blocked、dead、succeeded、superseded 数量。
- Embedding：active index、building index、模型、配置版本、完成率、失败数。
- 资源概览：资源总数、按 type 分布、最近 indexed_at。
- 错误聚合：按 component、operation、error_code 的最近错误统计。

页面不显示：

- `sync_sources.credentials`。
- API key、Authorization Header、数据库 DSN。
- outbox payload 中可能包含的敏感值。

管理员配置页已经按当前私人项目决策允许明文配置；状态页仍应按运行诊断边界脱敏。

### 7.3 交互

- 默认 15 秒轮询。
- 支持手动刷新。
- 支持按模块折叠。
- blocked/dead 显示错误码和脱敏摘要。
- 数据不足或服务未启用时显示明确空状态，不伪装健康。

## 8. Phase 5.4 检索排序增强

### 8.1 问题

现有检索已经具备关键词、语义和图扩展能力，但排序主要还是基础召回结果。下一步需要让系统从“能查到”变成“查得准、解释得清、能影响创作”。

### 8.2 目标设计

新增 `rank_evidence` 应用服务，融合以下信号：

- 关键词分数。
- 语义分数。
- 图距离和边权。
- 来源新鲜度：`source_updated_at` 新于旧，未知时间降权但不删除。
- 索引新鲜度：`indexed_at` 表示本地处理时间，不能冒充源端时间。
- 资源类型权重：爆款案例、发布效果、用户反馈、方法论、普通文档权重不同。
- 历史表现权重：绑定 `performance_metric` 的高表现内容提升权重。
- 证据覆盖率：能支持用户方向、标题、正文结构、标签习惯的来源更高。
- 去重：相同 external mapping、相似标题、相同主题角度只保留代表项。

第一版使用可解释规则，不引入学习排序模型。

### 8.3 Tools 行为

保留现有 tools 名称，避免 prompt 和前端大改：

- `search_resources` 返回新增 `rank_signals` 和 `why_selected`。
- `semantic_search_resources` 在 semantic 可用时返回融合结果；不可用时仍结构化回退关键词。
- `graph_expand` 只做有界扩展，不把图数据库作为权威事实。
- `get_resource_performance` 用于解释历史表现。

结果仍必须限量，默认不超过 10 条摘要；精读正文仍通过 `get_resource`。

## 9. Phase 5.5 创作效果闭环

### 9.1 当前基础

系统已能保存：

- 生成选题。
- 生成文案。
- 用户修改反馈。
- 发布后表现指标。
- 来源资源与生成资源的 `derived_from`、`feedback_on`、`measured_by` 关系。

### 9.2 目标设计

创作流程中增加历史表现反馈：

1. 用户给出方向后，先检索相关来源和历史生成内容。
2. 若存在发布表现，读取 `performance_metric`。
3. 排序时提升高表现来源和高表现生成策略。
4. 输出选题时增加内部决策依据，但前端展示只保留简洁的“推荐理由”和来源摘要。
5. 用户选择某个选题后，文案生成应继承该选题的证据和表现线索。
6. 用户反馈或修改意见继续沉淀，并影响后续相似方向。

### 9.3 明确边界

- 不训练预测模型。
- 不声称能保证爆款。
- 不把历史表现当作唯一依据。
- 没有表现数据时如实说明，不编造。

## 10. Phase 5.6 Web 结构治理

### 10.1 问题

聊天主界面文件已经超过 1600 行，配置页面也较大。继续叠功能会让验证成本和回归风险上升。

### 10.2 拆分目标

优先拆高变化区：

- `ThreadShell`：页面总体布局和 provider 连接。
- `ChatTimeline`：消息流、滚动、loading。
- `ComposerPanel`：输入、附件、发送。
- `EvidencePanel`：创作依据展示。
- `TopicCardList`：选题卡片。
- `CopyCardList`：文案卡片和复制。
- `RightInspector`：飞书状态、预览、运行状态入口。
- `ConfigSections`：LLM、embedding、飞书配置分区。
- `AdminStatusPage`：只读状态页。

拆分时保持行为不变，先补单元或轻量组件测试，再移动代码。不得顺手重做视觉风格。

## 11. Phase 5.7 文档事实收敛

文档需要分三类：

- 当前事实：已经实现并上线的行为。
- 禁用事实：代码有接口或历史设计提到，但当前 disabled，不得误标成功。
- 后续愿景：可选增强，不能被测试或 UI 当作已可用能力。

重点修正：

- Phase 3 里 Meilisearch、Graphiti、Neo4j/FalkorDB、Dagster 的表述要与 README 对齐。
- Phase 4.5A 的“待实施计划”状态要按当前实现情况更新。
- 配置中心文档要反映管理员明文配置页的最新决策。
- Web 内部桥接迁移后，删除或降级 `web_bridge_runner.py` 的生产路径说明。

## 12. 实施切片

### 12.1 Slice A：内部 HTTP 与运行事实 API

交付：

- Starlette internal routes。
- Next internal client 从 `execFile` 迁到 HTTP。
- 配置、飞书状态、数据底座状态保持行为等价。
- `web_bridge_runner.py` 退出生产主路径，仅配置恢复 fallback 可暂留。
- internal key、open_id、is_admin header 契约和 route ACL 矩阵。
- LangGraph 不可达时的配置 break-glass fallback，响应明确 `degraded: true`。
- Web/Python 配置 allowlist 收敛为同一语义契约，config-center 不再接受 Web-only key。

验收：

- 本地和服务器 Web 配置页可读写。
- 不再为普通配置请求启动 Python 子进程。
- 后端 route 测试覆盖管理员、非管理员、普通用户飞书 route、缺失/错误 internal key。
- 关闭 LangGraph internal route 后，管理员仍可通过 degraded 配置恢复路径读取/写入配置中心；普通状态和飞书查询不降级。
- config-center 模式下提交 Web-only runtime apply key 会在前端被禁止或隐藏，不会到 Python 后端才失败。

### 12.2 Slice B：启动确定性

交付：

- `agent.py` import 无自动更新副作用。
- 飞书 skill/CLI 更新变为显式维护路径或 supervisor 受控任务。
- 测试钉死 graph import 不触发更新。

验收：

- `python -c "import agent"` 不联网、不写更新文件。
- LangGraph server 启动仍能加载飞书 MCP/tools。

### 12.3 Slice C：只读管理员状态页

交付：

- `/api/admin/status` 或等价 Next route。
- 管理员 UI 入口。
- 15 秒轮询、手动刷新、脱敏错误展示。

验收：

- 非管理员 403。
- 页面不显示 credentials/API key/DSN。
- blocked/dead/outbox/embedding building 状态可见。

### 12.4 Slice D：检索排序与效果闭环

交付：

- `rank_evidence` 服务。
- search/semantic tool 返回解释性排序信号。
- 创作 prompt 使用历史表现但不夸大。
- 发布效果资源影响相似方向排序。

验收：

- 高表现相关资源在同等相关性下排序更高。
- 过时来源不会被包装成当前事实。
- 无表现数据时输出不编造。

### 12.5 Slice E：Web 结构治理

交付：

- 拆分聊天主界面高变化组件。
- 拆分配置页分区。
- 保持 UI 行为和测试通过。

验收：

- 单文件复杂度明显下降。
- unit、tsc、lint、build 通过。
- 主要用户路径无视觉和交互回归。

### 12.6 Slice F：文档事实收敛

交付：

- README、Phase 3、Phase 4、Phase 4.5A 文档状态对齐。
- disabled 组件明确标注。
- 生产路径和内部 API 路径更新。

验收：

- 文档不再声称未启用组件已上线。
- 新开发者能从 README 理解真实运行方式。

## 13. 测试策略

Python：

- 内部 HTTP route 鉴权测试。
- 配置明文管理员读取与非管理员拒绝。
- internal key 缺失、错误、伪造 open_id/is_admin header、Next 声称 admin 但 Python 复算不是 admin 的拒绝测试。
- 普通用户飞书 route 不要求管理员权限，但只能访问自己的 UAT 上下文。
- LangGraph internal route 不可达时配置 break-glass fallback 测试。
- 运行事实 API 不泄露凭证。
- scheduler/outbox/embedding 状态汇总测试。
- `agent.py` import 副作用测试。
- rank_evidence 排序单元测试。
- 历史表现影响排序测试。

Web：

- config-store/internal-client 单元测试。
- Web/Python 配置 allowlist 一致性测试，覆盖 deploy-only key 与 config-center 不支持的 runtime apply key。
- 管理员状态页 API 测试。
- xhs blocks 和 evidence 渲染测试。
- TypeScript、lint、build。
- 必要时用 Playwright 检查管理员状态页和核心聊天路径。

服务器：

- `git pull --ff-only`。
- 使用真实 Postgres 运行 data_foundation focused tests。
- Web unit/tsc/build。
- PM2 restart 后检查 backend/frontend online。

## 14. 风险与缓解

- 内部 HTTP 替换桥接可能影响配置页：先做等价 route，再切 Next client，保留回滚点。
- 后端不可用时配置页失去修复能力：保留管理员-only 配置 break-glass fallback，并在 UI 和 API 响应中明确 degraded 状态。
- custom route 被直接访问绕过 Next 鉴权：所有 internal routes 强制校验 `XHS_INTERNAL_SECRET`，再按 route ACL 校验用户或管理员身份；管理员身份由 Python 端复算，不能只信任 header。
- 状态页可能暴露敏感数据：API 层统一脱敏，测试用真实样式的 token/DSN 断言不出现。
- 排序规则可能让结果变“黑箱”：每条结果返回 `rank_signals` 和 `why_selected`。
- Web 拆分可能引入回归：先补测试，再按组件边界小步移动。
- 配置页文案过度承诺热生效：根据 config-center、embedding 索引、rubric 重启边界分别显示真实 apply 状态，不使用“一律即时热重载”。
- 文档更新可能与代码进度不同步：每个 slice 完成时同步 README 当前事实。

## 15. 最终验收标准

- Web 生产请求不依赖 Python 子进程桥接主路径；仅管理员配置恢复允许显式 degraded fallback。
- Internal routes 不能被直接访问绕过 Next 鉴权或伪造管理员身份。
- `agent.py` import 无外部更新副作用。
- 管理员能看到只读运行状态，并能定位 sync/outbox/embedding/config 的主要问题。
- 检索结果能解释为什么被采用，历史表现可影响但不支配创作。
- 内容输出继续包含可信 evidence，不编造来源和发布时间。
- 配置页只展示真实 apply 状态，不把需要 scheduler 回填或重启的路径说成即时生效。
- Web 大文件得到拆分，后续功能能在清晰组件边界内演进。
- 文档与真实系统状态一致。
