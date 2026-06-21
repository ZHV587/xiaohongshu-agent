# 服务器部署规则与运维 Runbook

本文档是服务器部署、验证、重启、回滚和数据清理的统一规则。后续所有服务器操作优先以本文档为准；阶段性设计文档只作为背景资料。

## 1. 部署原则

1. 生产和联调入口只允许是 Web 对话 + LangGraph server。
2. 项目不恢复交互式 Python CLI 作为业务运行入口。
3. `agent.py` 是 DeepAgents/LangGraph 的装配入口；不得 fork DeepAgents、monkey-patch DeepAgents，或依赖 compiled graph 私有字段。
4. 后台同步、outbox、embedding 和运行事实由 LangGraph `http.app` ASGI lifespan 管理。
5. Postgres + pgvector 是权威业务库和向量库；飞书、外部数据库等都是 ingestion adapter。
6. 运维脚本只允许承担部署、健康检查、备份、回滚、配置恢复和受控数据清理，不允许承载 Agent 业务行为。
7. `lark-cli` 只允许作为 Feishu adapter 在 server/worker 内部使用，不是用户可见运行入口。

## 2. 服务器拓扑

当前单机部署包含：

- `xhs-backend`：LangGraph/Python 后端，由 PM2 管理。
- `xhs-frontend`：Next.js Web 前端，由 PM2 管理。
- Postgres：权威业务库，必须启用 `pgcrypto` 与 `vector` 扩展。
- LangGraph `http.app`：承载 `/internal/*` route、scheduler supervisor、outbox 和 embedding 生命周期。
- Next.js API route：负责浏览器侧鉴权、管理员判断和转发内部请求。

内部调用链：

```text
Browser
  -> Next.js Web / API
  -> XHS_INTERNAL_BASE_URL
  -> LangGraph http.app /internal/*
  -> Postgres / Feishu adapter / outbox processor
```

## 3. 环境变量分层

### 3.1 Deploy-only 配置

这些配置只允许在服务器环境或受控部署文件中维护，不进入管理员配置中心历史版本，不出现在普通状态 API payload 中：

- `XHS_DATABASE_URL`
- `XHS_INTERNAL_BASE_URL`
- `XHS_INTERNAL_SECRET`
- `XHS_ADMIN_OPEN_IDS`
- `XHS_JWT_SECRET`
- `XHS_CONFIG_CENTER_PATH`
- `XHS_CONFIG_ENCRYPTION_KEY`
- `PATH`
- `NODE_OPTIONS`

### 3.2 管理员可明文配置

当前私人项目决策允许管理员界面明文查看和保存业务配置，包括：

- `LLM_*`
- `FEISHU_*`
- `XHS_EMBEDDING_*`

但这些值不得进入日志、错误摘要、outbox payload、telemetry、runtime facts、普通状态 API 或外部响应。

### 3.3 数据库存储凭证

`sync_sources.credentials` 当前允许明文存入 Postgres。约束是：

- 可以由管理员配置和维护。
- 不得出现在 `sync_runs.error_summary`、`service_executions.error_summary`、outbox payload、日志、health facts 或 data foundation status。
- 调试时不得直接打印完整 `sync_sources` 行。

## 4. 标准发布流程

### 4.1 本地发布前检查

发布前至少完成：

```bash
uv run pytest tests/data_foundation -q
git diff --check
```

涉及 Web 改动时还要运行：

```bash
cd web
pnpm test:unit
pnpm exec tsc --noEmit
pnpm lint
pnpm build
```

如果本地没有 `TEST_XHS_DATABASE_URL`，Postgres 集成测试可能跳过；这种情况下服务器真实 Postgres 测试是必跑项。

### 4.2 Git 发布

所有部署必须来自 Git 提交：

```bash
git status --short
git add <changed-files>
git commit -m "<type>: <summary>"
git push origin master
```

不得在服务器直接手改业务代码后长期运行。服务器代码状态必须能由 Gitee `origin/master` 复现。

### 4.3 服务器拉取

服务器项目目录：

```bash
/home/ubuntu/xiaohongshu-agent
```

拉取规则：

```bash
cd /home/ubuntu/xiaohongshu-agent
git pull --ff-only origin master
```

只允许 fast-forward。若失败，先查清楚服务器是否存在未提交改动，不得用 `reset --hard` 直接覆盖，除非明确确认这些改动应废弃。

### 4.4 服务器真实库测试

服务器必须使用真实 Postgres 验证：

```bash
cd /home/ubuntu/xiaohongshu-agent
set -a
source .env
set +a
TEST_XHS_DATABASE_URL="$XHS_DATABASE_URL" ./.venv/bin/pytest tests/data_foundation -q
```

注意：

- 运行命令时不得打印 `.env`。
- 不得输出 `XHS_DATABASE_URL`、API key、internal secret。
- 当前开发阶段允许用生产库跑集成测试，因为测试 fixture 使用隔离 schema；不要改成临时 SQLite。

### 4.5 重启服务

后端代码或 deploy-only 环境变量变化后：

```bash
pm2 restart xhs-backend --update-env
```

前端代码或 Web 环境变量变化后：

```bash
pm2 restart xhs-frontend --update-env
```

只修改配置中心内的 embedding 配置时，不需要立刻重启后端；下一轮 scheduler 会按新配置创建新 index，完成后切换 active index。

## 5. 健康检查

### 5.1 PM2 状态

```bash
pm2 status
```

期望：

- `xhs-backend` 为 `online`
- `xhs-frontend` 为 `online`

### 5.2 内部运行事实

使用管理员 open_id 和 internal secret 调用：

```bash
curl -fsS \
  -H "X-XHS-Internal-Key: $XHS_INTERNAL_SECRET" \
  -H "X-XHS-Open-Id: ${XHS_ADMIN_OPEN_IDS%%,*}" \
  -H "X-XHS-Is-Admin: true" \
  "$XHS_INTERNAL_BASE_URL/internal/health/facts"
```

只允许对外汇总这些状态：

- `startup`: `running`
- `scheduler`: `healthy`
- `database`: `healthy`

不得复制完整响应给非管理员，因为未来响应可能包含更细的运行指标。

### 5.3 数据底座 smoke

涉及 scheduler、outbox、embedding、search 的改动，应验证：

1. 写入一条通用 `resources` 记录。
2. scheduler 能发现非 source 工作租户。
3. outbox 处理 `embedding_generate` 成功。
4. `embedding_indexes` 切为 `active`，`expected_resources == completed_resources`。
5. `semantic_search_resources` 返回 `mode=semantic` 且能查回该资源。
6. smoke 数据清理后，确认 baseline 符合预期。

## 6. 数据库规则

### 6.1 权威存储

- 正式路径只使用 Postgres。
- 不引入 SQLite 作为正式数据底座。
- `data_foundation/schema.sql` 是当前 schema 权威来源。
- `pgcrypto` 和 `vector` 扩展必须可用。

### 6.2 数据清理

开发阶段需要清空数据底座时，使用受控 reset：

```python
from data_foundation.db import connect, reset_data_foundation

conn = connect()
try:
    reset_data_foundation(conn)
finally:
    conn.close()
```

禁止手写无 allowlist 的批量 `drop table` 或跨 schema 删除。

### 6.3 数据备份

进入正式数据阶段后，清理或回滚前必须先备份 Postgres。当前仍处开发阶段且用户确认无正式数据时，可以按干净环境策略直接 reset。

## 7. 回滚规则

代码回滚优先使用 Git：

```bash
git log --oneline
git revert <bad-commit>
git push origin master
```

服务器执行：

```bash
git pull --ff-only origin master
pm2 restart xhs-backend --update-env
pm2 restart xhs-frontend --update-env
```

禁止事项：

- 不用 `git reset --hard` 作为默认回滚方式。
- 不在服务器留下未提交热修复。
- 不用数据库 reset 代替代码回滚。

## 8. 安全与日志规则

不得进入日志、错误、状态、遥测、outbox 或普通 API 的内容：

- `XHS_DATABASE_URL`
- `XHS_INTERNAL_SECRET`
- `XHS_JWT_SECRET`
- `LLM_API_KEY`
- `XHS_EMBEDDING_API_KEY`
- `FEISHU_APP_SECRET`
- Feishu user access token / refresh token
- `sync_sources.credentials`
- Authorization header
- outbox payload 中的密钥字段
- 正文 chunk 和完整用户素材

允许输出的内容：

- 聚合状态，如 `healthy`、`running`、`succeeded`
- 固定错误码，如 `RUNTIME_FACTS_DATABASE_UNAVAILABLE`
- 脱敏摘要
- 资源数量、队列数量、索引计数

## 9. 禁止事项

1. 禁止恢复项目业务 CLI 运行入口。
2. 禁止把 `tools/web_bridge_runner.py` 变回 Web 生产请求主路径；它只能作为配置恢复或维护工具。
3. 禁止绕过 Postgres 数据底座直接读飞书作为内容生成兜底。
4. 禁止把未启用组件标记为 succeeded，例如 Meilisearch、Graphiti、Neo4j/FalkorDB、Dagster。
5. 禁止 agent 直接连接 Postgres、飞书底层 API 或图数据库；必须通过官方 tools、subagents、middleware、MCP 或内部服务层。
6. 禁止在响应、日志或测试输出里打印密钥。
7. 禁止服务器代码与 Gitee `origin/master` 长期不一致。

## 10. 常用验证命令

本地：

```bash
uv run pytest tests/data_foundation -q
git diff --check
```

服务器：

```bash
cd /home/ubuntu/xiaohongshu-agent
git pull --ff-only origin master
set -a
source .env
set +a
TEST_XHS_DATABASE_URL="$XHS_DATABASE_URL" ./.venv/bin/pytest tests/data_foundation -q
pm2 restart xhs-backend --update-env
pm2 status
```

内部 health：

```bash
curl -fsS \
  -H "X-XHS-Internal-Key: $XHS_INTERNAL_SECRET" \
  -H "X-XHS-Open-Id: ${XHS_ADMIN_OPEN_IDS%%,*}" \
  -H "X-XHS-Is-Admin: true" \
  "$XHS_INTERNAL_BASE_URL/internal/health/facts"
```

## 11. 当前服务器事实

当前已知服务器事实：

- 服务器项目路径：`/home/ubuntu/xiaohongshu-agent`
- Git remote：Gitee `origin/master`
- 进程管理：PM2
- 后端进程名：`xhs-backend`
- 前端进程名：`xhs-frontend`
- 数据库：Postgres + pgvector
- 后台服务入口：LangGraph `http.app` ASGI lifespan

如果服务器拓扑变化，必须先更新本文档，再按新规则执行部署。
