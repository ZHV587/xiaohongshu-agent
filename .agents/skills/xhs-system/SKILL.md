---
name: xhs-system
description: |
  系统工具集。存档当前诊断状态、拉取上次存档、打包阶段报告、Agent工作台迁移审计。
  触发方式：「保存」「存档」「接上次」「接着上次」「打包报告」「阶段报告」「工作台迁移」「迁移工作台」
---

# xhs-system：系统工具

系统级工具集合，四个独立功能按触发词激活。

---

## 功能 A：存档（/xhs-save 或「保存」「存档」）

把当前会话的关键诊断结论持久化。

**操作**：
1. 询问 project_name（如未提供）
2. 整理本次会话的关键结论（定位/选题/文案/决策中的任何有价值的部分）
3. 调用 `save_session_snapshot(project_name, title, content)` 存入数据库
4. 调用 `sync_diagnosis_to_feishu(project_name, title, content)` 同步飞书

**返回**：数据库 resource_id + 飞书表格链接

---

## 功能 B：恢复（/xhs-restore 或「接上次」「上次在哪」）

拉取最近一份存档，恢复上下文。

**操作**：
1. 调用 `get_resource` 查询最近的 session snapshot（按 project_name 过滤）
2. 读取存档内容，注入到当前会话上下文
3. 告诉用户：「上次的结论是…，我们接着聊。」

---

## 功能 C：报告打包（/xhs-report、/dbs-report 或「打包报告」）

把多次诊断、选题、文案、复盘沉淀成一份可分享的阶段报告。

**使用场景**：
- 用户说「整理成报告」「打包一下」「阶段复盘」
- 用户已经多次 `/xhs-save`，想把过程合并成一份文档
- 用户要把账号定位、对标、选题和下一步行动交给团队看

**操作**：
1. 询问 project_name（如未提供）
2. 调用 `search_resources` 查找该项目最近的 session snapshot、诊断记录、选题记录
3. 按时间线整理：背景 → 已否决方向 → 已确认判断 → 当前策略 → 下一步动作
4. 调用 `save_session_snapshot(project_name, "阶段报告-{日期}", content)` 保存报告
5. 调用 `sync_diagnosis_to_feishu(project_name, "阶段报告-{日期}", content)` 同步飞书

**报告结构**：
```
## 阶段报告

**项目**：{project_name}
**时间范围**：{开始日期} - {结束日期}

### 1. 当前结论
{最重要的 3-5 条结论}

### 2. 已否决方向
{不要再重复尝试的方向}

### 3. 关键证据
{引用资源、数据或原话}

### 4. 下一步行动
{按优先级列出 3 条}
```

---

## 功能 D：Agent 工作台迁移审计（/xhs-system、/dbs-agent-migration 或「工作台迁移」）

审计当前 Agent 工作台目录结构，确保 Claude Code / Codex / Grok 三端一致。

**审计清单**：
1. 是否有 `CLAUDE.md`（Claude Code 规则文件）
2. 是否有 `AGENTS.md`（Codex 通用规则文件）
3. `.agents/skills/` 下是否有完整的 SKILL.md 清单
4. 各端触发词是否一致（`/xhs-*` 前缀规范）
5. 是否有冲突的规则配置

**输出**：审计清单 + 修复建议

调用 `save_session_snapshot(project_name, "Agent工作台迁移审计-{日期}", content)` 保存数据库版本，再调用 `sync_diagnosis_to_feishu(project_name, "Agent工作台迁移审计-{日期}", content)` 同步飞书。

---

## 说话风格

1. 存档和恢复直接执行，不废话
2. 报告打包要按时间线组织，不要写成泛总结
3. 工作台审计给具体清单，不给模糊建议
