# 多用户安全边界与配置演进设计

- 日期: 2026-06-19
- 范围: 多用户权限、配置应用一致性、运行时配置中心、飞书身份边界、草稿同步语义、通用数据底座、图谱增强多 Agent 平台
- 状态: 设计待评审

## 1. 背景

当前项目已经具备小红书内容智能体、LangGraph/DeepAgents 后端、Next.js 工作台、飞书 OAuth、多维表格读取与飞书通知能力。但整体仍带有单人本地工具的假设:

- 已登录用户都能访问和修改系统配置。
- 配置 UI 保存的字段与 Python 模型调度实际读取的字段存在漂移。
- 配置保存后是否真正被 LangGraph 后端应用不可验证。
- 飞书工具存在用户 UAT 与 bot 兜底混用的边界风险。
- 同步到多维表格仍有演示态固定 `record_id`。
- 部署路径、IP、敏感日志和质量门还没有生产化收口。

本设计把修复拆为三个阶段。第一阶段优先保证安全边界和配置应用状态真实可见。第二阶段再把配置从 `.env + 应用/重启` 演进为运行时配置中心和无重启模型热切换。第三阶段建设通用数据底座与图谱增强多 Agent 平台，小红书文案智能体只是首个上层业务应用。

## 2. 顶层约束

1. 必须依托原生 DeepAgents / LangGraph 框架改造。
2. 明确认知 DeepAgents 的底层结构: DeepAgents 是构建在 LangChain Agent 与 LangGraph `CompiledStateGraph` 之上的封装组装层。DeepAgents 提供文件工具、子智能体、backend、memory、permissions、interrupt、harness profile 等深度智能体能力；LangChain 提供 agent 与 middleware 抽象；LangGraph 提供 graph runtime、thread、store、auth 与 server 生命周期。
3. 保留 `create_deep_agent`、LangGraph auth/thread/store、DeepAgents backend、permissions、memory 和 middleware 机制。
4. 不 fork DeepAgents。
5. 不 monkey-patch DeepAgents 内部模块。
6. 不访问已编译 graph 的私有字段。
7. 模型运行时切换只能通过原生 `AgentMiddleware.wrap_model_call` / `awrap_model_call` 和 `request.override(model=...)`。
8. 通用数据底座、图谱、索引、同步和配置中心都必须作为外部服务或 DeepAgents tools 暴露给 agent，不得替代 LangGraph runtime 或绕过 DeepAgents 工具权限体系。
9. 若某项热切能力无法通过原生扩展点证明覆盖，则使用受控应用/重启兜底，而不是修改框架内部。
10. 项目运行入口只保留 Web 对话 + LangGraph server；交互式 Python CLI 入口已移除，`agent.py` 是唯一 DeepAgents/LangGraph 装配入口。

## 3. 第一阶段: 多用户安全边界与配置应用一致性

### 3.1 目标

第一阶段目标不是无感热更新，而是让配置变更真实、安全、可验证:

- 谁能看和改配置是确定的。
- 能写入哪些配置字段是确定的。
- 后端是否已经应用新配置是可见的。
- 飞书操作使用谁的身份是确定的。
- 同步多维表格不会误覆盖固定演示记录。
- 改造遵守 DeepAgents 原生生命周期。

产品文案应使用“保存并应用配置”，不要承诺“无感热更新”。

### 3.2 管理员模型

新增部署级环境变量:

```env
XHS_ADMIN_OPEN_IDS=ou_xxx,ou_yyy
```

规则:

- 值为逗号分隔的飞书 `open_id`。
- `XHS_ADMIN_OPEN_IDS` 是部署级配置，不允许通过应用配置页修改。
- 首次部署时，任何登录用户都可以通过 `/api/me` 查看自己的 `open_id`，运维将该值写入 `.env` 后重启 Next 服务完成管理员 bootstrap。

新增 Next 服务端鉴权 helper:

- `requireUser(req)`: 校验 `xhs_auth` JWT，返回 `{openId, name, isAdmin}`。
- `requireAdmin(req)`: 在 `requireUser` 基础上检查 `XHS_ADMIN_OPEN_IDS`。

接口权限:

- `/api/me`: 所有已登录用户可访问，返回 `openId`、`name`、`isAdmin`。
- `/api/config`: 仅管理员可访问。
- `/api/config/test`: 仅管理员可访问。
- 配置应用接口: 仅管理员可触发。
- 飞书 chats/sync/notify/status: 已登录用户可访问，按当前用户 UAT 执行。

前端:

- 侧边栏配置入口只对管理员显示。
- 非管理员直接访问 `?view=llm` 或 `?view=feishu` 时显示无权限。
- 后端权限是最终边界，不能只依赖前端隐藏。

### 3.3 配置安全

管理员可查看明文密钥，但必须按高风险操作处理:

- GET `/api/config` 响应必须设置 `Cache-Control: no-store`。
- 密钥不写入 URL、query、localStorage、toast 或普通日志。
- 前端密码框默认隐藏。
- 点击显示、复制、保存配置都记录审计事件。
- 关闭配置页时尽量清空包含密钥的 React state。
- 错误响应不得包含原始密钥、UAT、JWT、refresh token 或飞书 app secret。

配置写入必须使用字段白名单，并按域拆分:

- `llmConfigKeys`: `LLM_PROVIDER`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_QUALITY_MODELS`、可选多网关字段。
- `feishuConfigKeys`: `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BITABLE_APP_TOKEN`、`FEISHU_BITABLE_TABLE_ID`、字段映射配置。
- `runtimeApplyKeys`: apply 模式相关字段。
- `deployOnlyKeys`: `XHS_ADMIN_OPEN_IDS`、`XHS_JWT_SECRET`、`XHS_INTERNAL_SECRET`、`PATH`、`NODE_OPTIONS` 等，禁止 UI 修改。

保存配置时由服务端生成 `XHS_CONFIG_VERSION`，例如 UTC timestamp 加配置摘要 hash。客户端不能传入或伪造 version。

### 3.4 模型配置契约

第一阶段生产路径只承诺 OpenAI-compatible gateway:

```env
LLM_PROVIDER=openai
LLM_BASE_URL=https://your-gateway/v1
LLM_API_KEY=...
LLM_QUALITY_MODELS=model-a,model-b
```

规则:

- `LLM_QUALITY_MODELS` 是后端模型池主契约。
- UI 的“首选模型”就是 `LLM_QUALITY_MODELS` 第一项。
- 后续项是同质量备用模型。
- `LLM_MODEL` 不再作为后端主契约，可删除或仅作为兼容展示字段。
- `/api/config/test` 返回 discovered models 后，管理员必须显式选择哪些模型进入质量池。
- 不允许自动把 discovered models 全部加入池。

Anthropic/Gemini 原生 provider 可保留为实验路径，但第一阶段不承诺其多模型发现、多网关容灾和保存后应用的一致性。已有原生 provider 设计不删除，但生产验收只覆盖 OpenAI-compatible gateway。

### 3.5 保存并应用配置

第一阶段默认采用受控应用策略，而不是进程内 registry 热切。

新增配置:

```env
XHS_BACKEND_APPLY_MODE=manual|pm2|systemd
XHS_BACKEND_PM2_NAME=xhs-backend
XHS_BACKEND_SYSTEMD_SERVICE=xhs-backend.service
```

规则:

- 默认 `manual`。
- `pm2` / `systemd` 必须显式开启。
- 不支持 `XHS_RESTART_COMMAND` 这类任意 shell 命令。
- 开启 `pm2` / `systemd` 等同授予 Next 进程重启 Python 后端的运维权限，文档必须明确风险。
- 长期更安全方案是外部部署系统或 supervisor 观察 config version 后应用，不由 Web 进程直接重启。

应用流程:

1. 管理员保存配置。
2. Next 校验字段白名单。
3. 服务端生成 `XHS_CONFIG_VERSION`。
4. 写入权威 `.env`。
5. 按 `XHS_BACKEND_APPLY_MODE` 应用:
   - `manual`: 返回“已保存，需手动重启后端”。
   - `pm2`: 执行固定 `pm2 restart <XHS_BACKEND_PM2_NAME>`。
   - `systemd`: 执行固定 `systemctl restart <XHS_BACKEND_SYSTEMD_SERVICE>`。
6. 前端轮询后端 status，确认后端加载了目标 `XHS_CONFIG_VERSION`。

状态区分:

- `.env` 写入失败: 保存失败，不应用。
- apply 命令失败: 配置已保存但未应用。
- 后端不可达: 后端重启失败或启动中。
- 后端 version 旧: 新配置未加载。
- 后端 version 新但模型池错误: 配置已加载但模型不可用。
- 后端 version 新且 active models 非空: 应用成功。

### 3.6 后端状态

需要一个后端状态读取能力:

- public health: 只返回 alive 和 config version，不含敏感信息。
- admin status: 返回 active models、last model error、config version，需要管理员或内部访问。

如果状态端点挂在 LangGraph server 上，需要确认不会被错误 auth 策略阻断健康检查。健康检查不得暴露 key、base_url 完整值或 UAT。

### 3.7 `.env` 权威源

第一阶段可以保留当前双写现实，但目标状态必须明确:

- 根目录 `.env` 是后端权威配置。
- `web/.env` 只保留 Next 运行必需字段。
- 不应长期把所有后端密钥复制到 `web/.env`。
- `/api/config/test` 第一阶段可继续在 Next 侧执行，但长期应迁移到 Python 后端或受控内部 bridge，减少模型密钥进入 Next 进程的需要。

### 3.8 飞书身份边界

server 模式下所有用户触发的飞书操作默认使用当前用户 UAT:

- 读爆款多维表格。
- 创建草稿记录。
- 发送群消息。
- 读取群聊列表。

缺 UAT、UAT 过期且 refresh 失败、scope 不足或飞书表权限不足时，返回明确诊断，不静默 bot fallback。

bot 使用边界:

- bot 只用于显式系统任务或受控开发诊断模式。
- server 用户请求不得静默退回 bot。

建议拆分工具执行入口:

- `lark_cli_user_required(...)`: server 默认，缺 UAT 直接失败。
- `lark_cli_allow_bot_fallback(...)`: 仅受控开发诊断或系统任务明确调用。

MCP 工具注意事项:

- 如果 MCP adapter 无法将 `RunnableConfig` 传到 `execute_lark_command`，则不要通过 MCP 暴露需要用户身份的飞书写操作。
- 需要用户身份的飞书工具应直接注册为 Python tool，以确保能拿到 `config.server_info.user.identity`。

必须新增测试覆盖: 用户请求触发 `baokuan-analyst` 子智能体后，子智能体读取飞书数据仍携带当前用户身份。

### 3.9 飞书状态诊断

新增或完善 `/api/feishu/status`:

- 当前用户是否已绑定 UAT。
- token 是否可刷新。
- scopes 是否包含必需项。
- 是否能访问配置的多维表格。
- 失败原因摘要: 未授权、scope 不足、表权限不足、app 权限不足、表 token/table id 错误等。

第一阶段坚持 UAT-only。若团队共享爆款库普通成员读不到，需在飞书侧授权给成员。管理员显式开启 bot-read shared dataset mode 放到第二阶段。

### 3.10 草稿同步

移除固定 `rec_default_4`。第一阶段同步语义改为“新建草稿记录”:

- `/api/feishu/sync` 不再要求 `recordId`。
- 后端创建新记录，而不是更新固定记录。
- 写入字段:
  - 标题
  - 正文
  - 标签
  - 创建人 open_id/name
  - 创建时间
  - thread_id
  - 状态: 草稿/待审核
  - 幂等键: 可选 `threadId + draftHash`
- 返回 `record_id` 和飞书跳转链接。

字段映射:

```env
XHS_BITABLE_FIELD_TITLE=
XHS_BITABLE_FIELD_BODY=
XHS_BITABLE_FIELD_TAGS=
XHS_BITABLE_FIELD_AUTHOR=
XHS_BITABLE_FIELD_STATUS=
```

如果未配置，后端可读取 field list 后做安全模糊匹配。字段缺失时返回可操作错误，不创建半残记录。

前端状态:

- 未同步: 尚未入库。
- 同步中: 禁用按钮并展示步骤。
- 成功: 已创建草稿记录，展示 record_id 和打开飞书链接。
- 失败: 显示错误，不假成功。

### 3.11 日志、部署与质量门

必须删除敏感 DEBUG 日志，例如 `read_xhs_data` 中打印 app token/table id 的语句。

日志不得输出:

- API key
- 飞书 app secret
- UAT / refresh token
- JWT
- 完整 bitable app token

硬编码迁移:

- 公网 origin 使用 `XHS_PUBLIC_ORIGIN`，其次可信 proxy headers，本地 fallback 为 localhost。
- Python 路径使用 `XHS_PYTHON_BIN` 或固定 apply mode 配置，不写死远程路径。
- 远程验证脚本迁移到 devops 区域或标注为非生产路径。

ESLint:

- 忽略 `.next`、`next-env.d.ts`、`tsconfig.test.tsbuildinfo`。
- 质量门使用 `eslint src`，不 lint 生成文件。

第一阶段质量门:

```bash
uv run pytest
web/node_modules/.bin/tsc.CMD --noEmit
web/node_modules/.bin/eslint.CMD src
```

新增测试:

- admin whitelist 和 `/api/me`。
- 非管理员访问配置返回 403。
- 配置字段 allowlist。
- 保存配置生成 `XHS_CONFIG_VERSION`。
- apply mode 不接受任意命令。
- server 模式禁 bot fallback。
- UAT-only 子智能体读取。
- 同步创建草稿记录，不更新固定 record。
- status 区分 version 旧、新配置错误、active models 非空。

## 4. 第二阶段: 配置中心化与无重启热切换

### 4.1 目标

第二阶段目标是把第一阶段的 `.env + 保存并应用/重启` 演进为真正的平台能力:

- 配置有权威运行时存储。
- Next 和 Python 不再双写 `.env`。
- 对已被 `ModelRegistry` / router middleware 覆盖并通过测试证明的模型调用路径，保存模型配置后 LangGraph 后端无需重启，新请求使用新模型池。
- 配置变更有版本历史和审计。
- 密钥加密存储并支持轮换。
- 仍不 fork、不 monkey-patch DeepAgents。

### 4.2 配置中心

引入后端权威配置存储:

- 首选 Postgres 表。
- 小规模部署可用加密 JSON 文件。

`.env` 仅保留启动必需项:

- `XHS_JWT_SECRET`
- bootstrap admin
- database/config encryption key
- public origin
- config storage location

业务配置迁入配置中心:

- 模型网关与质量池。
- 飞书 app 和 bitable 配置。
- 字段映射。
- apply/reload 策略。
- 后续角色配置。

配置中心要求:

- 配置版本号。
- 修改人。
- 修改时间。
- 变更摘要。
- 密钥字段加密存储。
- 可选回滚。

### 4.3 无重启 ModelRegistry 热切换

在 LangGraph 后端进程内引入 `ModelRegistry`:

- 持有当前 config version。
- 持有当前模型候选池。
- 持有 last_loaded_at 和 last_error。
- 支持 `reload(configVersion)`。

`ModelRouterMiddleware` 仍然是原生 `AgentMiddleware`:

- `wrap_model_call` / `awrap_model_call` 每次从 registry 读取当前 pool。
- 通过 `request.override(model=candidate.model)` 切换模型。
- 健康度按 `registry.version + gateway + model_id` 隔离。

前提验收:

- 主 agent sync 调用读新 registry。
- LangGraph server async 调用读新 registry。
- 子智能体调用读新 registry。
- rubric 调用要么读新 registry，要么明确不纳入无重启热切范围。

若任一关键路径无法通过原生扩展点证明覆盖，则该路径继续使用第一阶段受控应用/重启策略。

### 4.4 管理通道

第二阶段需要进程内管理通道通知 LangGraph 后端 reload:

- 如果提供 HTTP management route，必须启用 `XHS_INTERNAL_SECRET`。
- 请求签名包含 method、path、timestamp、nonce、body hash。
- 后端校验 timestamp 窗口和 nonce 防重放。
- 普通用户 JWT 不能直接调用内部 reload。

如果框架不适合挂管理 route，可以由部署系统或 sidecar 通知后端，但不得通过子进程刷新另一个进程的 registry。`web_bridge_runner.py` 子进程只能作为 Web API 到 Python 工具的临时桥接，不能用于进程内热切，因为它无法修改常驻 LangGraph 进程内存。

### 4.5 统一配置 API

Next 的 `/api/config` 不再直接读写 `.env`。它应调用后端配置服务:

- 管理员读取配置。
- 管理员保存配置。
- 后端配置服务写入配置中心。
- 后端通知 LangGraph registry reload。
- 返回 active config version 和 active models。

模型连通性测试也迁移到后端配置服务，避免模型密钥长期进入 Next 进程。

### 4.6 角色系统

从 `XHS_ADMIN_OPEN_IDS` 演进为配置中心角色表:

- owner
- admin
- member

保留 env bootstrap admin，避免首次部署无人可管。角色修改需要审计。

### 4.7 密钥管理

第二阶段改进密钥策略:

- 密钥加密存储。
- 默认不回显明文。
- 支持 reveal 操作。
- reveal 需要审计。
- 支持密钥轮换。
- 错误日志和审计日志不包含明文。

### 4.8 飞书共享数据模式

第一阶段 UAT-only 不变。第二阶段可增加管理员显式开启的 shared dataset mode:

- 读团队爆款库可使用 bot/app 身份。
- 发消息、同步个人或群操作仍默认使用用户 UAT。
- UI 明确标注每个操作使用团队身份还是个人身份。
- shared dataset mode 必须记录审计。

### 4.9 草稿记录升级

第二阶段在“新建草稿”基础上增加:

- 更新已创建草稿。
- 用户选择飞书记录后更新。
- Agent 结构化绑定来源记录。
- 幂等键查重，避免重复创建。
- 草稿状态流转: 草稿、待审核、已通过、已发布等。

### 4.10 管理与诊断页面

新增管理能力:

- 当前配置版本。
- 配置版本历史。
- active models。
- model registry last error。
- 后端健康状态。
- 飞书授权诊断。
- 最近配置变更审计。
- 最近飞书写操作审计。

## 5. 第三阶段: 通用数据底座与图谱增强多 Agent 平台

### 5.1 目标

第三阶段目标是把当前小红书垂直应用升级为通用数据底座上的多 Agent 应用平台。底层数据不是小红书专用，也不只依托飞书，而是由数据库、飞书协作空间、外部系统、搜索索引、向量索引、图谱索引和事件日志共同组成。

核心原则:

- DeepAgents / LangGraph 继续作为 agent runtime。
- 通用数据底座作为外部服务和工具层存在。
- 小红书文案智能体只是首个 app。
- 第三阶段不是引入多 Agent；多 Agent 协作已经是 DeepAgents 底层前提。本阶段是为既有多 Agent 协作提供统一数据、图谱、检索和权限底座。
- 飞书是协作沉淀层，数据库是高性能权威底座，二者通过同步和映射保持关联。
- 所有数据访问通过 Data Access Layer 和 DeepAgents tools 暴露，不允许 agent 直接连接数据库自由查询。

### 5.2 双沉淀结构

数据库沉淀:

- 标准化结构化记录。
- 资源 ID、外部映射、版本、权限、审计。
- Agent run、artifact、任务状态。
- 检索索引、向量、缓存、事件日志。
- 适合高速读取、批量计算、跨应用复用的数据。

飞书沉淀:

- 人可读、可协作、可审批的业务资产。
- Base 里的运营表、选题池、草稿库、审核状态。
- Doc 里的方法论、复盘、会议纪要、项目说明。
- IM 群里的协作上下文和审核反馈。
- Task/Approval/Calendar 等组织流程数据。

必须维护映射:

- DB record ↔ 飞书 Base record。
- DB artifact ↔ 飞书 Doc。
- DB task ↔ 飞书 Task/Approval。
- DB comment/event ↔ 飞书 IM thread/message。
- DB version ↔ 飞书资源 revision/update time。

### 5.3 统一资源模型

所有可被 agent 读取、生成、同步、审批或引用的对象都抽象为 resource:

- 数据库记录。
- 飞书 Base 行。
- 飞书 Doc。
- 飞书 IM 消息。
- 文件。
- Agent 产物。
- 任务、审批、发布内容、复盘。

基础表建议:

- `resources`: 全局资源 ID、类型、tenant、owner、visibility、created_at、updated_at。
- `resource_mappings`: 外部系统 ID 映射，如 feishu/base/record/doc/message。
- `resource_versions`: 内容版本与变更摘要。
- `resource_events`: 导入、生成、修改、同步、审核、发布、反馈事件。
- `resource_permissions`: 资源级权限快照或引用。
- `resource_edges`: 资源之间的关系边。

### 5.4 推荐开源组合

第三阶段采用组合式集成，不使用单一大而全项目替代平台底座。

下表是推荐组合和选型方向，不是不可裁剪的硬依赖。最终实现可以按部署复杂度和团队能力裁剪具体组件，但必须保留统一 resource model、Data Access Layer、权限过滤、事件日志和 DeepAgents tools 边界。

| 层 | 推荐项目 | 职责 |
|---|---|---|
| 权威业务库 | Postgres + `pgvector` | 结构化业务数据、配置、审计、版本、向量检索 |
| 数据接入 | `dlt`，后续可接 Airbyte | Python-first connector；外部系统多时引入 Airbyte |
| 文档解析 | Unstructured | PDF、Word、HTML、图片等转结构化内容 |
| 全文/混合搜索 | Meilisearch | 快速关键词、全文和应用层混合检索 |
| 时间知识图谱 | Graphiti | 面向 AI agents 的 temporal knowledge graph、provenance、事实演化 |
| 图数据库 | Neo4j 或 FalkorDB | Graphiti 后端和图查询执行层 |
| GraphRAG 管线 | LightRAG 或 Microsoft GraphRAG | 大语料实体/关系抽取、社区摘要、GraphRAG 查询 |
| 编排 | Dagster | 数据资产、同步、索引任务、血缘和调度 |
| 元数据治理 | DataHub 或 OpenMetadata | 组织级数据目录和治理，后半段再引入 |

推荐第一组合:

1. Postgres + `pgvector` 作为权威业务与向量底座。
2. `dlt` 负责飞书、数据库、内部 API 的 Python-first 数据加载。
3. Unstructured 负责非结构化文档解析。
4. Graphiti + Neo4j/FalkorDB 负责时间知识图谱。
5. Meilisearch 负责快速全文和混合检索。
6. DeepAgents tools 封装所有访问能力。

不建议:

- 不把 Microsoft GraphRAG 当完整业务底座。它适合 GraphRAG pipeline，不负责权限、审计、业务记录和飞书同步。
- 不整体引入 LlamaIndex 作为第二套 agent runtime。可借用 property graph/ingestion 能力，但主 runtime 仍是 DeepAgents/LangGraph。
- 不一开始引入 DataHub/OpenMetadata 作为核心依赖。它们适合组织级数据目录，等数据资产规模上来后再接。
- 不让 Agent 直接执行自由 SQL/Cypher。

### 5.5 图谱与图算法

第三阶段一开始就设计资源关系图，不后补血缘和 GraphRAG。

图中节点:

- User、Team、Role。
- Dataset、Field、Record。
- FeishuBaseRecord、FeishuDoc、FeishuMessage、Task、Approval。
- AgentRun、Artifact、Draft、Review、PublishedContent。
- Topic、Entity、Metric、Rule、Memory。

图中边:

- `MEMBER_OF`
- `READ`
- `WROTE`
- `DERIVED_FROM`
- `SYNCED_TO`
- `APPROVED_BY`
- `MENTIONS`
- `SIMILAR_TO`
- `MEASURES`
- `FEEDBACK_TO`

内置图算法:

- k-hop / BFS: 血缘查询、上下文扩展、影响范围分析。
- Personalized PageRank: 按用户、团队、主题找重要资源。
- Community Detection: 自动发现主题簇、知识模块和协作群。
- Shortest Path: 解释推荐和检索结果来源。
- Entity Resolution / Record Linkage: 合并跨系统重复实体。
- Temporal Graph: 复盘选题、草稿、审核、发布、效果回流的时间链路。
- GraphRAG: 关键词/向量召回后沿图扩展邻居，再做权限过滤和重排序。

### 5.6 检索架构

Agent 读取采用粗召回、图扩展、重排序、精读的流程:

1. `search_resources(query)`: 关键词与全文召回。
2. `semantic_search(query, top_k)`: 向量召回。
3. `resolve_entities(query/results)`: 识别实体和候选资源。
4. `graph_expand(resource_ids, hops, edge_types)`: 图邻居扩展。
5. `permission_filter(user, resources)`: 权限过滤。
6. `rerank(results)`: RRF 或加权融合排序。
7. `get_resource(resource_id)`: 精读单条资源。

检索层组合:

- BM25/全文搜索保证精确命中。
- 向量 ANN 保证语义召回。
- 图扩展保证关系上下文和可解释性。
- 权限过滤保证多租户安全。

### 5.7 事件日志与同步

所有关键动作写入 event log:

- 外部导入。
- Agent 生成。
- 人工修改。
- 飞书同步。
- 审核。
- 发布。
- 效果反馈。
- 配置变更。

事件日志用于:

- 审计。
- 同步重放。
- 图谱增量更新。
- 指标和复盘。
- 数据血缘。

飞书和数据库同步必须维护:

- `sync_cursor`
- `external_resource_id`
- `external_updated_at`
- `local_version`
- `sync_status`
- `last_error`

### 5.8 DeepAgents 接入方式

第三阶段所有数据能力通过 DeepAgents tools 暴露:

- `search_resources`
- `query_records`
- `semantic_search`
- `graph_expand`
- `get_resource`
- `write_artifact`
- `sync_to_feishu`
- `create_task`
- `request_approval`

工具要求:

- 工具内部做 tenant/user 权限校验。
- 工具结果限制大小，不能把大表直接塞进上下文。
- 高风险写操作继续使用 DeepAgents `interrupt_on` 或 HITL。
- 工具返回结构化结果，便于前端渲染和后续 agent 决策。

### 5.9 第三阶段验收

- 所有业务对象都有统一 resource_id。
- 数据库和飞书之间有双向映射与版本状态。
- Postgres + pgvector 存储结构化记录和向量。
- Graphiti + 图数据库存储资源关系、事实演化和 provenance。
- Meilisearch 提供全文/快速检索。
- 至少一个飞书 Base 数据集可增量同步到数据库和图谱。
- Agent 通过 tools 完成 hybrid search + graph_expand + get_resource。
- GraphRAG 检索结果可解释其来源路径。
- 所有读取经过权限过滤。
- 写操作可审计、可回放、可同步到飞书协作层。

## 6. 非目标

第一阶段非目标:

- 不做完整数据库配置中心。
- 不做应用内角色管理页面。
- 不做飞书部门/群组管理员自动识别。
- 不做已有记录更新。
- 不做无重启模型热切。
- 不重构整个 `Thread` 大组件。
- 不产品化 Anthropic/Gemini 原生多 provider 灾备。

第二阶段非目标:

- 不 fork DeepAgents。
- 不通过私有字段修改已编译 graph。
- 不以牺牲权限边界换取无感体验。
- 不承诺所有模型调用路径都能无重启热切；只有通过原生 middleware/registry 覆盖测试的路径才纳入无重启范围。

第三阶段非目标:

- 不把 DeepAgents 替换为其他 agent 框架。
- 不把 Microsoft GraphRAG、LlamaIndex、Graphiti 或任何单一开源项目当成完整平台底座。
- 不允许 Agent 直接执行自由 SQL/Cypher 或绕过 Data Access Layer 访问底层数据库。
- 不把飞书降级为临时外部源；飞书仍是协作型数据沉淀层。

## 7. 实施顺序

第一阶段:

1. `/api/me`、admin whitelist、配置 API 权限收口。
2. 配置字段 allowlist、明文密钥 no-store、审计日志。
3. 模型配置 UI 与 `LLM_QUALITY_MODELS` 契约统一。
4. 保存并应用配置: version、apply mode、backend status。
5. 飞书 UAT-only 工具边界与 status diagnostics。
6. 同步改为新建草稿记录。
7. 清理敏感日志、硬编码、ESLint 生成目录。
8. 补齐后端和前端 API 测试。

第二阶段:

1. 设计并引入配置中心。
2. 迁移模型和飞书业务配置。
3. 建立进程内 `ModelRegistry` 和管理 reload 通道。
4. 证明主 agent、server async、subagent、rubric 的热切覆盖。
5. 迁移 `/api/config` 到后端配置服务。
6. 引入角色表和密钥 reveal/轮换。
7. 增强飞书 shared dataset mode 和草稿更新流。
8. 建设管理诊断页面。

第三阶段:

1. 定义通用 resource schema、mapping schema、event log schema。
2. 接入 Postgres + `pgvector`。
3. 接入 `dlt` 飞书数据同步 pipeline。
4. 接入 Unstructured 文档解析。
5. 接入 Meilisearch 全文检索。
6. 接入 Graphiti + Neo4j/FalkorDB 时间知识图谱。
7. 实现 resource_edges 和基础 k-hop 查询。
8. 实现 hybrid search + graph_expand 的 Data Access Layer。
9. 暴露 DeepAgents tools。
10. 用小红书场景作为首个 app 验证通用底座。

## 8. 验收标准

第一阶段验收:

- 非管理员无法访问或保存系统配置。
- 管理员可查看和保存配置，响应不缓存。
- 配置保存只允许白名单字段。
- 保存会生成服务端 config version。
- 后端应用状态可被验证，失败状态可解释。
- 模型配置 UI 保存 `LLM_QUALITY_MODELS`，后端读取同一契约。
- server 模式飞书操作缺 UAT 时失败，不 bot fallback。
- 子智能体读取飞书数据仍使用当前用户身份。
- 同步到飞书新建草稿记录，不覆盖固定记录。
- 敏感 DEBUG 日志被移除。
- 未显式开启 `pm2` / `systemd` apply mode 时，保存配置不得尝试重启后端，只能返回 manual apply 状态。
- `uv run pytest`、`tsc --noEmit`、`eslint src` 通过。

第二阶段验收:

- 配置中心成为模型和飞书业务配置权威源。
- Next 和 Python 不再双写 `.env`。
- 已纳入 `ModelRegistry` / router middleware 覆盖测试的模型调用路径，保存模型配置后无需重启，下一次 agent run 使用新模型池。
- 主 agent、server async、subagent、rubric 热切路径有测试证明，或未覆盖路径明确排除。
- 密钥加密存储，明文 reveal 有审计。
- 配置变更有版本历史和操作者记录。
- 仍遵守 DeepAgents 原生扩展点，不 monkey-patch。

第三阶段验收:

- 通用数据底座支持数据库和飞书双沉淀。
- 小红书业务数据不再是底层唯一抽象。
- Data Access Layer 屏蔽 Postgres、搜索、向量、图谱和飞书差异。
- DeepAgents 只通过 tools 访问数据底座。
- graph_expand、semantic_search、search_resources、get_resource 可组合完成 GraphRAG。
- 图谱至少支持血缘、同步、相似、审核和反馈关系。
- 第一个多 Agent 应用可以复用同一底座，不需要复制小红书专用数据模型。
