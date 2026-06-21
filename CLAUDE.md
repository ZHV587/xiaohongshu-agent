# 项目开发规则

## 部署与测试

- **直接部署到服务器测试,不在本地跑测试验证。** 所有功能验证、回归、冒烟都在服务器真实环境(真实 Postgres 库、真实飞书凭据、PM2 进程)上进行。本地只做代码编写。
  - 标准流程:本地改代码 → `git commit` → `git push origin master` → 服务器 `git pull --ff-only` → 重新构建/重启 → 在服务器上验证。
  - 本地推送走 HTTPS,git 配了 `127.0.0.1:7897` 代理但 Gitee 不需要,推送用 `git -c http.proxy= -c https.proxy= push origin master` 绕过。

## 服务器拓扑(详见 docs/deployment/server-deployment-rules.md)

- 服务器:`124.221.173.80`,ubuntu,SSH 密码登录(凭据见 `verify_remote_logs.py` 等脚本)。项目路径 `/home/ubuntu/xiaohongshu-agent`。
- PM2 两进程:`xhs-backend`(`./.venv/bin/python3 tools/run_backend.py`,langgraph dev,端口 2030)、`xhs-frontend`(`/usr/bin/npm run start -- -p 9091`,cwd web)。
- 前端用 **npm**(非 pnpm)。前端改动:`cd web && npm run build` 后 `pm2 restart xhs-frontend --update-env`。后端改动:`pm2 restart xhs-backend --update-env`。
- `.env` 与 `web/.env` 不进 git,服务器独立维护;改 deploy-only 变量后必须 `--update-env` 重启。
- 服务器真实库测试:`set -a && . ./.env && set +a && TEST_XHS_DATABASE_URL="$XHS_DATABASE_URL" ./.venv/bin/python3 -m pytest <path> -q`。

## 安全

- 严禁在服务器源码里临时插 print/诊断代码再跑(历史上两次因转义/笔误把 .py 改出 SyntaxError 导致后端中断)。诊断用本地复现脚本或服务器**只读** monkey-patch 内存验证,不改磁盘源码。
- 日志/错误/响应里不得打印密钥、token、Authorization、UAT、sync_sources.credentials。
