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
- `XHS_BACKEND_APPLY_MODE`: `manual`、`pm2` 或 `systemd`。默认 `manual`,不会自动重启后端。
- `LLM_PROVIDER`: 第一阶段生产路径建议固定为 `openai`。
- `LLM_QUALITY_MODELS`: 高质量模型池,逗号分隔;第一项是首选模型。
- 飞书操作在 server 模式下默认使用当前用户 UAT,缺授权时不会静默退回 bot。

## 运行方式

### CLI(1a,单会话)
```bash
uv run python cli.py
```

### LangGraph server(1b-1,多会话 + 共享/隔离)
```bash
uv run langgraph dev
```
默认起在 `http://127.0.0.1:2024`。

联调验证(另开终端,server 起好后):
```bash
uv run python verify_1b1.py
```
验证:跨轮记忆、`/shared` 跨会话共享、`/drafts` 按会话隔离。

## 文件后端路由(1b-1)

- `/skills/` → 磁盘 `skills/` 目录(共享只读)
- `/shared/` → Store(跨会话/用户共享,如风格沉淀)
- `/drafts/` 及其他 → State(随会话隔离)

## 测试
```bash
uv run pytest
```

## 文档
- 设计:`docs/superpowers/specs/2026-06-15-xhs-content-agent-design.md`
- 计划:`docs/superpowers/plans/`
