# 全栈统一 Docker Compose 重构方案(根治版)

> 目标:把后端从 `langgraph dev`(pickle 持久化、OOM 即丢)迁到自托管 langgraph 生产 server,
> 并把 **pg / redis / meilisearch / falkordb / langgraph-server / web 六个服务统一进一份声明式
> `docker-compose.yml`**,统一网络、服务名互连。消灭 PM2 与散装容器。一份文件描述整个生产栈。
>
> 原则:根本性重构,不兜底、不兼容。现有散装拓扑(绑 127.0.0.1 的孤立容器 + 宿主 PM2 进程 +
> 运行时 `docker network connect` 拼接)全部废弃,改为单一编排声明。

## 一、为什么要做(三个已确认的现网问题)

1. **持久化是 pickle,OOM 即丢**:`langgraph dev` 把会话/`/shared`方法论/`/drafts` 全存进程本地
   `.langgraph_api/*.pckl`(已 ~1.7MB),`checkpointer=True` 在 dev 模式下被忽略(读源码确认)。
2. **检索链路当前是断的**:`.env` 里 `XHS_MEILI_URL`/`XHS_MEILI_KEY`/`XHS_FALKOR_URL` **全为空**,
   `engine_config.py` 判定 meili/falkor 均 `disabled` → `search_resources` 返回 `MEILI_UNAVAILABLE`、
   `graph_expand` 不可用。引擎容器在跑但后端没连上。统一 compose 用服务名一并接通。
3. **拓扑散装**:pg-db/meili/falkor 三个孤立容器各绑 127.0.0.1、不在同一网络;后端是宿主 PM2 进程;
   无单一事实源描述"生产栈长什么样"。重启/迁移/排障都靠口口相传。

## 二、license / 成本结论(读源码确认,非文档臆测)

- `langgraph_license/validation.py` 全文是 **noop**,`plus_features_enabled()` 永远 True,
  "No license check is performed"。`metadata.py` 无 key 时仅 skip metadata loop,有 air-gapped 分支。
- 包:`langgraph`/`-checkpoint`/`-checkpoint-postgres`/`deepagents` = MIT;`langgraph-api` = ELv2
  (自托管自用允许,仅禁转售为托管服务)。
- **结论:自托管自用零费用,不需要任何付费 license。**

## 三、目标架构(六服务一网络)

```
docker network: xhs-net (bridge)
├── pg           (local/postgres16-pgvector:0.8.3)  vol: pgdata          → 业务库 xhs_agent + 新建 langgraph 库
├── redis        (redis:7-alpine)                    无暴露端口           → langgraph server 队列/pubsub
├── meili        (getmeili/meilisearch:v1.10)         bind: ./data/meili  → 全文检索
├── falkor       (falkordb/falkordb:latest)           bind: ./data/falkor → 图谱
├── langgraph    (xhs-langgraph:latest, langgraph build 产物)             → 容器内 8000 → 宿主 127.0.0.1:2030
└── web          (Next.js standalone)                                     → 宿主 0.0.0.0:9091(公网入口)
```

服务间一律用**服务名**互连(不再 127.0.0.1):
- langgraph → `pg:5432` / `redis:6379` / `meili:7700` / `falkor:6379`
- web(BFF/内部) → `langgraph:8000`
- 仅 web(9091,公网)和 langgraph(2030,仅 127.0.0.1 供调试/前端 BFF)对宿主暴露端口。

## 四、现有数据的无损接管(已实测卷/路径)

| 服务 | 现有数据载体 | compose 声明(复用同一份,不丢数据) |
|---|---|---|
| pg | named volume `pgdata` → /var/lib/postgresql/data | `volumes: [pgdata:/var/lib/postgresql/data]`,external 复用 |
| meili | bind `/home/ubuntu/meili-data` → /meili_data | 统一到项目内 `./data/meili`,**迁移时 mv 现有目录过去** |
| falkor | bind `/home/ubuntu/falkor-data` → /data | 统一到 `./data/falkor`,迁移时 mv |
| pg 库 | `xhs_agent`(用户 xhs_user) | 不动;新建独立 `langgraph` 库给 server 持久化 |

> meili/falkor 的 bind 路径迁移:`docker compose down` 旧容器后,`mv /home/ubuntu/meili-data
> /home/ubuntu/xiaohongshu-agent/data/meili`(falkor 同理),再 `up`。数据是同一份文件,不重建索引。
> pgdata 是 named volume,compose 用 `external: true` 直接挂同一个卷,零迁移。

## 五、文件清单(本地新增/改动,全部进 git)

1. **`docker-compose.yml`(新增,根目录)**:六服务声明,见 §三。
   - pg/meili/falkor 用与现有完全相同的镜像 + 环境(MEILI_MASTER_KEY 等经 env_file 注入)。
   - langgraph:`image: xhs-langgraph:latest`(由 `langgraph build` 产出),env_file=.env,
     额外注入 `REDIS_URI=redis://redis:6379`、`POSTGRES_URI=postgres://xhs_user:${PG_PW}@pg:5432/langgraph`、
     `XHS_MEILI_URL=http://meili:7700`、`XHS_FALKOR_URL=redis://falkor:6379`、`XHS_SYNC_ENABLED=true`。
   - web:`build: ./web`(Dockerfile),env_file=web/.env,挂载配置中心目录与 UAT store。
2. **`web/Dockerfile`(新增)**:多阶段,`output: standalone`,**用 npm 构建**(对齐服务器现状+CLAUDE.md)。
3. **`web/next.config.mjs`(改)**:加 `output: "standalone"`,产出精简自包含运行包。
4. **`.dockerignore`(新增,已建)** + **`web/.dockerignore`(已存在,复核)**。
5. **`tools/run_backend.py`(废弃或改造)**:不再作为 PM2 入口;langgraph dev 入口退役。
6. **lock 文件统一**:本地 git 只跟踪 `web/pnpm-lock.yaml` 但服务器用 npm。**统一为 npm**:
   删 pnpm-lock,提交 `package-lock.json`,Dockerfile 用 `npm ci`。(消除双 lock 不一致)
7. **`docs/deployment/server-deployment-rules.md`(改)**:重写部署/重启/回滚为 compose 流程。
8. **`langgraph.json`**:保持不变(server 镜像读它装配 graph)。

## 六、env 改造(关键:服务名替换 localhost)

容器内服务互连不能再用 127.0.0.1。改动(经 compose `environment` 覆盖,不必改 .env 文件本身):
- 后端读的:`XHS_MEILI_URL=http://meili:7700`、`XHS_FALKOR_URL=redis://falkor:6379`、
  `XHS_DATABASE_URL` 的 host `127.0.0.1`→`pg`、`POSTGRES_URI`(langgraph 持久化)→`pg:5432/langgraph`。
- web 读的:`LANGGRAPH_API_URL=http://langgraph:8000`、`XHS_INTERNAL_BASE_URL=http://langgraph:8000`。
- 浏览器侧(保持公网,不变):`NEXT_PUBLIC_API_URL=http://124.221.173.80:9091/api`、`FEISHU_REDIRECT_URI` 同。
- 密钥(MEILI_MASTER_KEY、pg 密码、各 API key)经 `env_file` 注入,**不写进 compose、不进 git**。

## 七、实施步骤(全程 git,服务器不手改源码)

### 阶段 A — 本地(编码 + 提交)
1. 写 `docker-compose.yml`(六服务)、`web/Dockerfile`(npm + standalone)、`.dockerignore`。
2. `web/next.config.mjs` 加 `output: "standalone"`。
3. lock 统一:删 `web/pnpm-lock.yaml`,生成并提交 `web/package-lock.json`;CLAUDE.md 已记 npm。
4. 退役 `tools/run_backend.py` 的 PM2 角色(保留文件或删,二选一)。
5. 重写 `docs/deployment/server-deployment-rules.md` 为 compose 运维。
6. 本地 `docker compose config` 校验语法(若本地有 docker);commit + push。

### 阶段 B — 服务器(前置)
7. 加 2G swap(防 build/启动尖峰)+ 写 fstab。
8. `sudo apt install docker-compose-plugin`(实测未装)。
9. `git pull --ff-only`。
10. 数据归位:停旧三容器→`mv /home/ubuntu/{meili-data,falkor-data}` 到 `项目/data/`;
    pgdata 是 named volume,compose `external: true` 直接挂。
11. 在 pg 建独立库:`CREATE DATABASE langgraph OWNER xhs_user;`。

### 阶段 C — 切换
12. `langgraph build -t xhs-langgraph:latest`(出后端镜像)。
13. `pm2 delete xhs-backend xhs-frontend`(导出定义备份留底)。
14. `docker compose up -d --build`(web 镜像现场 build,其余拉起)。

### 阶段 D — 验证(逐项,失败即停)
15. `docker compose ps` 六服务 healthy。
16. `curl 127.0.0.1:2030/ok` + `/internal/health/facts`(带 internal key):startup/scheduler/database healthy。
17. 真实库 `pytest tests/data_foundation`(隔离 schema)。
18. **检索接通验证**(本次连带修复的重点):浏览器发"露营装备"→ `search_resources` 返回 meili 命中
    (不再 MEILI_UNAVAILABLE),`graph_expand` 可用。
19. **持久化验证**:跑一轮对话 → `docker compose restart langgraph` → 会话历史还在(证明落 pg,不再 pickle)。
20. 公网 `http://124.221.173.80:9091` 飞书 OAuth 登录 + 对话端到端通。
21. `docker stats` / `free -h` 看内存峰值是否在 swap 兜底内。

## 八、回滚

- compose 整体回滚:`docker compose down` → `pm2 start` 旧定义(dev 模式)。pickle 文件保留不动,
  dev 模式可立即恢复。meili/falkor 数据已 mv,回滚需 mv 回原路径(或旧容器也指新路径)。
- 代码回滚走 `git revert`。pg 的 langgraph 库独立,drop 不影响业务库。

## 九、风险与待确认

1. **web 容器化是最大新增面**:standalone 构建 + 配置中心/UAT store 路径挂载若漏,登录/配置会坏。
   验证步 20 专门覆盖。
2. **meili/falkor 数据 mv**:需停机窗口(分钟级)。停机期间服务不可用。
3. **历史 pickle 会话弃用**(已确认):迁移后全新开始。
4. **检索此前是断的**:本方案首次真正接通 meili/falkor,等于双引擎首次在生产生效,需重点验证
    outbox 是否把存量 resources 索引进 meili(可能需触发一次全量 reindex)。

### 待你确认
- [ ] meili/falkor 数据目录从 `/home/ubuntu/*-data` 迁到项目内 `./data/*`,接受分钟级停机?
- [ ] 存量 resources 是否需要在接通 meili 后触发一次全量重索引(否则只有新同步的能被检索到)?
- [ ] `tools/run_backend.py` 退役方式:删除,还是保留为应急 dev 入口?
