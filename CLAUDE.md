# 项目开发规则

## 核心原则(最高优先级)

- **根本性修复,不做兼容。** 所有问题都查到根因后从根上改,不打补丁、不加兼容层、不为保旧测试/旧行为束手束脚。需要改契约/删旧逻辑就直接改,相关测试一并重写。
- **浏览器验证直接操作,不必逐次征求同意。** 用浏览器工具登录、点按钮、跑 OAuth 授权、触发对话等验证动作直接执行,不用每步问用户。

## 部署与测试

- **所有服务统一在 Docker Compose 环境下运行与测试。** 生产环境与远端回归均在容器化拓扑（六容器编排、有界网络互联）上完成。
  - 标准流程: 本地改代码 ➔ `git commit` ➔ `git push origin master` ➔ 服务器 `git pull --ff-only` ➔ 重新编译并拉起服务 ➔ 运行容器内测试与人工验证。
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
- 环境变量：宿主机根目录下 `.env` 和 `web/.env` 挂载至对应容器，宿主机修改后需执行 `docker compose up -d` 重新装载。
- 服务器容器内集成测试：
  ```bash
  docker compose exec langgraph pytest <path_to_test> -q
  ```

## 安全

- 严禁在服务器源码里临时插 print/诊断代码再跑(历史上两次因转义/笔误把 .py 改出 SyntaxError 导致后端中断)。诊断用本地复现脚本或服务器**只读** monkey-patch 内存验证,不改磁盘源码。
- 日志/错误/响应里不得打印密钥、token、Authorization、UAT、sync_sources.credentials。
