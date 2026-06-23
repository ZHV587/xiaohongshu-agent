---
name: xhs-system
description: |
  系统工具集。存档当前诊断状态（/xhs-save）、拉取上次存档（/xhs-restore）、Agent工作台迁移审计。
  触发方式：/xhs-save、/xhs-restore、/xhs-system、「保存」「存档」「接上次」「工作台迁移」
---

# xhs-system：系统工具

系统级工具集合，三个独立功能按触发词激活。

---

## 功能 A：存档（/xhs-save 或「保存」「存档」）

把当前会话的关键诊断结论持久化。

**操作**：
1. 询问 project_name（如未提供）
2. 整理本次会话的关键结论（定位/选题/文案/决策中的任何有价值的部分）
3. 调用 `save_session_snapshot(project_name, title, content)` 存入数据库
4. 调用 `sync_diagnosis_to_feishu(project_name, title, content)` 同步飞书
5. 同时调用 `write_file` 写本地备份到 `~/.dbs/sessions/{project_name}/{YYYYMMDD-HHMMSS}-{title-slug}.md`

**返回**：数据库 resource_id + 飞书表格链接

---

## 功能 B：恢复（/xhs-restore 或「接上次」「上次在哪」）

拉取最近一份存档，恢复上下文。

**操作**：
1. 调用 `get_resource` 查询最近的 session snapshot（按 project_name 过滤）
2. 读取存档内容，注入到当前会话上下文
3. 告诉用户：「上次的结论是…，我们接着聊。」

---

## 功能 C：Agent 工作台迁移审计（/xhs-system 或「工作台迁移」）

审计当前 Agent 工作台目录结构，确保 Claude Code / Codex / Grok 三端一致。

**审计清单**：
1. 是否有 `CLAUDE.md`（Claude Code 规则文件）
2. 是否有 `AGENTS.md`（Codex 通用规则文件）
3. `.agents/skills/` 下是否有完整的 SKILL.md 清单
4. 各端触发词是否一致（`/xhs-*` 前缀规范）
5. 是否有冲突的规则配置

**输出**：审计清单 + 修复建议

调用 `write_file` 写入 `/analysis/agent-migration-audit-{日期}.md`。

---

## 说话风格

1. 存档和恢复直接执行，不废话
2. 工作台审计给具体清单，不给模糊建议
