# 项目开发规则

## 核心原则(最高优先级)

- **根本性修复,不做兼容。** 所有问题都查到根因后从根上改,不打补丁、不加兼容层、不为保旧测试/旧行为束手束脚。需要改契约/删旧逻辑就直接改,相关测试一并重写。
- **浏览器验证直接操作,不必逐次征求同意。** 用浏览器工具登录、点按钮、跑 OAuth 授权、触发对话等验证动作直接执行,不用每步问用户。
- **Git commit 一律用中文,且要详细到能看懂。** commit message 必须用中文书写(标题 + 正文),不用英文。标题一句话讲清"改了什么",正文用要点说清楚:① 问题/根因是什么(为什么要改),② 具体怎么改的(动了哪些模块、关键逻辑),③ 影响与验证(有无破坏性、跑了什么测试)。让不看代码的人只读 commit 就能明白这次改动。允许保留 `fix(scope):`/`feat(scope):` 这类前缀,但冒号后的描述用中文。

## 部署与测试

- **所有服务统一在 Docker Compose 环境下运行与测试。** 生产环境与远端回归均在容器化拓扑（六容器编排、有界网络互联）上完成。
  - 标准流程: 本地改代码 ➔ 本地/CI 跑完整测试 ➔ `git commit` ➔ `git push origin master` ➔ 服务器 `git pull --ff-only` ➔ 重新编译并拉起服务 ➔ 运行生产 smoke 与人工验证。
  - 本地推送走 HTTPS，绕过代理：`git -c http.proxy= -c https.proxy= push origin master`。

## 服务器拓扑(详见 docs/deployment/server-deployment-rules.md)

- 服务器：`124.221.173.80`，ubuntu，SSH 密钥登录（本地 `~/.ssh/xhs_deploy` 免密，`scripts/deploy.py` 走密钥；密码登录仍可作应急）。项目路径 `/home/ubuntu/xiaohongshu-agent`。代码托管在 GitHub 私有仓库 `git@github.com:ZHV587/xiaohongshu-agent.git`，服务器经只读 deploy key 拉取。
- 容器编排架构（六容器）：
  - 核心微服务：`xhs-langgraph`（后端，宿主机 127.0.0.1:2030）、`xhs-web`（Next.js，宿主机 0.0.0.0:9091）。
  - 底座数据库与引擎：`xhs-pg` (Postgres 16)、`xhs-redis` (Redis 7)、`xhs-meili` (Meilisearch)、`xhs-falkor` (FalkorDB)，全部隐藏在 `xhs-net` 网络内部，不对公网暴露，通过服务名直连。
- 重新部署命令：
  ```bash
  git pull --ff-only origin master
  langgraph build -t xhs-langgraph:latest
  docker compose up -d --build
  ```
- **⚠️ langgraph 后端必查:`compose up --build` 不会重建 langgraph,易静默沿用旧镜像跑旧代码(历史踩坑两次:893ab3d、本次 0e14f29)。** 根因:compose 里**只有 `web` 有 `build:` 段,langgraph 只有 `image: xhs-langgraph:latest`**——`--build` 只重建 web;langgraph 完全依赖先跑 `langgraph build` 把 `:latest` tag 指到新镜像,compose 再按 tag 拉起。一旦 `langgraph build` 结束后 `:latest` 仍指向旧 image ID(tag 没动),compose 认为无变化→输出里 langgraph 显示 **`Running`(而非 `Recreated`)**→容器继续跑旧代码。**部署 langgraph 后必须做两道只读校验,`Running` 不是 `Recreated` 就是没生效的信号:**
  ```bash
  # 1) latest tag 是否指到本轮新建的 image ID
  docker image inspect xhs-langgraph:latest --format '{{.Id}} {{.Created}}'
  # 2) 运行中的容器实际用的 image ID 是否 == 上面的新 ID
  docker inspect xhs-langgraph --format '{{.Image}} started={{.State.StartedAt}}'
  # 3) 兜底:核验容器内代码含本轮特征(如新提交才有的关键字/行数),而非只信 tag
  docker compose exec -T langgraph sh -c 'wc -l < subagents_executor.py'
  ```
  两者不一致(或容器 imageID 仍是旧的)时,**显式强制重建 langgraph,不依赖 compose 自动发现**:
  ```bash
  docker compose up -d --force-recreate --no-deps langgraph
  ```
  重建后重跑上面校验确认 imageID 已切到新镜像、容器 healthy,再跑 smoke。
- 环境变量：宿主机根目录下 `.env` 和 `web/.env` 挂载至对应容器，宿主机修改后需执行 `docker compose up -d` 重新装载。
- 服务器生产 smoke 验收：
  ```bash
  docker compose exec -T langgraph python scripts/runtime_import_smoke.py
  python3 scripts/deploy_health_check.py --public-url http://127.0.0.1:9091/
  ```

## 安全

- 严禁在服务器源码里临时插 print/诊断代码再跑(历史上两次因转义/笔误把 .py 改出 SyntaxError 导致后端中断)。诊断用本地复现脚本或服务器**只读** monkey-patch 内存验证,不改磁盘源码。
- 日志/错误/响应里不得打印密钥、token、Authorization、UAT、sync_sources.credentials。
